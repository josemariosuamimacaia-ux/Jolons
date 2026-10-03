"""MacTech — servidor Flask multi-empresa para assistentes de WhatsApp com IA.

Dois modos de funcionamento:
 1) Número próprio: cada empresa tem o seu número de WhatsApp (descoberta pelo phone_number_id).
 2) Número partilhado (hub): um número da MacTech serve várias empresas. O bot pergunta de que
    empresa o cliente quer ser atendido e depois responde com os dados dessa empresa.
"""
import hmac
import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from functools import wraps

from flask import Flask, jsonify, render_template_string, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

import ia
import whatsapp
from chat_page import PAGINA
from config import cfg
from models import Conversa, Empresa, Mensagem, SessionLocal, agora, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mactech")

app = Flask(__name__)
if cfg.trust_proxy:   # atrás de um proxy, lê o IP real do visitante
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
init_db()
# Número limitado de threads: evita esgotar recursos com muitos clientes ao mesmo tempo
executor = ThreadPoolExecutor(max_workers=cfg.max_workers)

MSG_TRANSICAO = "Claro! Vou passar a conversa a uma pessoa da equipa. Já te respondem por aqui."
MSG_SEM_HUMANO = ("De momento a equipa não está disponível para atendimento. "
                  "Deixa aqui a tua mensagem e eu ajudo no que puder.")
MSG_INDISPONIVEL = ("Este atendimento automático está temporariamente indisponível. "
                   "Por favor, contacte a empresa diretamente.")
MSG_ERRO = "Desculpa, tive um problema técnico. Tenta novamente daqui a pouco."
TERMOS_HUMANO = ("reclamacao", "humano", "atendente", "falar com pessoa", "falar com uma pessoa")


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para 'Reclamação' == 'reclamacao'."""
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def pede_humano(texto: str) -> bool:
    n = normalizar(texto)
    return any(termo in n for termo in TERMOS_HUMANO)


def achar_empresa(empresas: list, texto: str):
    """Descobre a empresa escolhida: pelo número da lista, pelo nome ou por uma palavra que só ela tem.
    Devolve None se não houver exactamente uma correspondência."""
    n = normalizar(texto).strip()
    palavras = [set(normalizar(e.nome).split()) for e in empresas]
    achadas = []
    for i, e in enumerate(empresas):
        unica = any(len(w) > 3 and w in n and sum(w in p for p in palavras) == 1 for w in palavras[i])
        if n == str(i + 1) or normalizar(e.nome) in n or unica:
            achadas.append(e)
    return achadas[0] if len(achadas) == 1 else None


def empresa_ativa(e) -> bool:
    """Ativa = conta paga ('ativo') ou dentro dos 2 dias de teste."""
    if e.estado == "ativo":
        return True
    if e.estado == "teste" and e.teste_ate:
        fim = e.teste_ate if e.teste_ate.tzinfo else e.teste_ate.replace(tzinfo=timezone.utc)  # SQLite devolve sem fuso
        return agora() < fim
    return False


# ---------- Chat web: limites e lógica de resposta ----------
SESSAO_RE = re.compile(r"[A-Za-z0-9\-]{16,64}")
_pedidos, _trinco = {}, threading.Lock()


def limite_excedido(chave, maximo, janela):
    """Limite simples em memória (protege a IA contra abuso num endpoint público)."""
    t = time.time()
    with _trinco:
        if len(_pedidos) > 20000:
            _pedidos.clear()
        recentes = [x for x in _pedidos.get(chave, []) if t - x < janela]
        excedeu = len(recentes) >= maximo
        if not excedeu:
            recentes.append(t)
        _pedidos[chave] = recentes
        return excedeu


def decidir_resposta(db, empresa, conversa, texto):
    """Mesma lógica do WhatsApp, para o chat web. Devolve o texto, ou None se um humano assumiu."""
    if conversa.humano_assumiu:
        return None
    if not empresa_ativa(empresa):
        return MSG_INDISPONIVEL
    if pede_humano(texto):
        if empresa.humano_ativo:
            conversa.humano_assumiu = True
            log.warning("[ATENÇÃO] %s: cliente web %s pediu atendimento humano", empresa.nome, conversa.cliente_numero)
            return MSG_TRANSICAO
        return MSG_SEM_HUMANO
    try:
        return ia.responder(empresa.system_prompt, historico_ia(db, conversa))
    except Exception:
        log.exception("Erro na IA (chat web)")
        return MSG_ERRO


def gerar_slug(db, nome):
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(nome)).strip("-")[:50] or "empresa"
    slug, i = base, 2
    while db.query(Empresa).filter_by(slug=slug).first():
        slug, i = f"{base}-{i}", i + 1
    return slug


def exige_admin(f):
    """Protege os endpoints /api/* com a chave X-API-Key."""
    @wraps(f)
    def wrapper(*a, **kw):
        chave = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(chave.encode(), cfg.admin_key.encode()):
            return jsonify(erro="não autorizado"), 401
        return f(*a, **kw)
    return wrapper


def guardar(db, conversa, remetente, conteudo):
    m = Mensagem(conversa_id=conversa.id, remetente=remetente, conteudo=conteudo)
    db.add(m)
    return m


def historico_ia(db, conversa, limite=10):
    """Últimas mensagens depois da escolha da empresa, no formato da IA. Tem de começar em 'user'."""
    msgs = (db.query(Mensagem)
            .filter(Mensagem.conversa_id == conversa.id, Mensagem.id > conversa.inicio_historico_id)
            .order_by(Mensagem.id.desc()).limit(limite).all())[::-1]
    hist = [{"role": "user" if m.remetente == "user" else "assistant", "content": m.conteudo} for m in msgs]
    while hist and hist[0]["role"] != "user":
        hist.pop(0)
    return hist


def obter_conversa(db, phone_number_id, numero, empresa_id):
    filtro = {"phone_number_id": phone_number_id, "cliente_numero": numero}
    c = db.query(Conversa).filter_by(**filtro).one_or_none()
    if not c:
        c = Conversa(**filtro, empresa_id=empresa_id, humano_assumiu=False)
        db.add(c)
        try:
            db.flush()  # gera o id
        except IntegrityError:   # outra thread criou a mesma conversa ao mesmo tempo
            db.rollback()
            c = db.query(Conversa).filter_by(**filtro).one()
    return c


def processar(pnid: str, msg: dict):
    """Trata UMA mensagem recebida. Corre numa thread do pool."""
    try:
        if msg.get("type") != "text":
            return
        numero = msg["from"]
        texto = (msg["text"]["body"] or "").strip()
        if not texto:
            return
        hub = bool(cfg.hub_pnid) and pnid == cfg.hub_pnid   # número partilhado?
        with SessionLocal() as db:
            if hub:
                token, empresa = cfg.hub_token, None
                conversa = obter_conversa(db, pnid, numero, None)
                if conversa.empresa_id:
                    empresa = db.get(Empresa, conversa.empresa_id)
            else:
                empresa = db.query(Empresa).filter_by(wa_phone_number_id=pnid).one_or_none()
                if not empresa:
                    log.warning("Webhook para número desconhecido: %s", pnid)
                    return
                token = empresa.wa_access_token
                conversa = obter_conversa(db, pnid, numero, empresa.id)

            guardar(db, conversa, "user", texto)

            # No número partilhado, o cliente pode trocar de empresa
            if hub and "mudar de empresa" in normalizar(texto):
                conversa.empresa_id, conversa.humano_assumiu, empresa = None, False, None

            if conversa.humano_assumiu:          # a IA não responde
                db.commit()
                log.info("[%s] %s: humano assumiu, IA calada", empresa.nome, numero)
                return

            if empresa is not None and not empresa_ativa(empresa):   # teste terminou ou conta suspensa
                log.warning("[ATENÇÃO] %s: teste terminou ou conta suspensa, bot desligado", empresa.nome)
                guardar(db, conversa, "assistant", MSG_INDISPONIVEL)
                db.commit()
                whatsapp.enviar_texto(token, pnid, numero, MSG_INDISPONIVEL)
                return

            escolheu = False
            if hub and empresa is None:
                # Triagem: perguntar (ou perceber) de que empresa o cliente quer ser atendido
                empresas = [e for e in db.query(Empresa).filter_by(no_hub=True).order_by(Empresa.id).all()
                            if empresa_ativa(e)]
                if not empresas:
                    resposta = "De momento não há empresas disponíveis neste número."
                else:
                    escolhida = achar_empresa(empresas, texto)
                    if escolhida:
                        conversa.empresa_id, escolheu = escolhida.id, True
                        resposta = f"Perfeito! Está a falar com {escolhida.nome}. Como posso ajudar?"
                        log.info("Conversa %s ligada a %s", numero, escolhida.nome)
                    else:
                        lista = "\n".join(f"{i + 1} {e.nome}" for i, e in enumerate(empresas))
                        resposta = ("Olá! De que empresa quer ser atendido? "
                                    f"Responda com o número ou o nome:\n{lista}")
            elif pede_humano(texto):
                if empresa.humano_ativo:
                    conversa.humano_assumiu = True
                    resposta = MSG_TRANSICAO
                    log.warning("[ATENÇÃO] %s: cliente %s pediu atendimento humano", empresa.nome, numero)
                else:
                    resposta = MSG_SEM_HUMANO
            else:
                try:
                    resposta = ia.responder(empresa.system_prompt, historico_ia(db, conversa))
                except Exception:
                    log.exception("Erro na IA")
                    resposta = MSG_ERRO

            m = guardar(db, conversa, "assistant", resposta)
            if escolheu:
                db.flush()
                conversa.inicio_historico_id = m.id   # a IA só vê o que vier depois da escolha
            db.commit()
            whatsapp.enviar_texto(token, pnid, numero, resposta)
    except Exception:
        log.exception("Erro ao processar mensagem")


# ---------- Webhook da Meta ----------
@app.get("/webhook")
def verificar_webhook():
    """A Meta chama isto uma vez para confirmar o endereço."""
    if not cfg.verify_token:
        return "WhatsApp não configurado", 503
    if (request.args.get("hub.mode") == "subscribe"
            and hmac.compare_digest(request.args.get("hub.verify_token", "").encode(),
                                    cfg.verify_token.encode())):
        return request.args.get("hub.challenge", ""), 200
    return "token inválido", 403


@app.post("/webhook")
def receber_webhook():
    if not cfg.app_secret:
        return "WhatsApp não configurado", 503
    if not whatsapp.assinatura_valida(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        return "assinatura inválida", 403
    dados = request.get_json(silent=True) or {}
    for entrada in dados.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            pnid = valor.get("metadata", {}).get("phone_number_id")  # número que recebeu a mensagem
            if not pnid:
                continue
            for msg in valor.get("messages", []):
                executor.submit(processar, pnid, msg)
    return jsonify(received=True), 200   # responder rápido à Meta


# ---------- Endpoints extra ----------
@app.get("/saude")
@app.get("/health")
def saude():
    return jsonify(status="ok")


@app.post("/api/empresas")
@exige_admin
def criar_empresa():
    """Regista uma empresa. Número próprio (wa_phone_number_id + wa_access_token) é opcional:
    sem ele, a empresa só é atendida pelo número partilhado."""
    d = request.get_json(silent=True) or {}
    em_falta = [c for c in ("nome", "system_prompt") if not str(d.get(c, "")).strip()]
    pnid = str(d.get("wa_phone_number_id") or "").strip() or None
    token = str(d.get("wa_access_token") or "").strip() or None
    if pnid and not token:
        em_falta.append("wa_access_token")
    if em_falta:
        return jsonify(erro="campos em falta", campos=em_falta), 400
    empresa = Empresa(nome=d["nome"].strip(), wa_phone_number_id=pnid, wa_access_token=token,
                      system_prompt=d["system_prompt"], humano_ativo=bool(d.get("humano_ativo", True)),
                      no_hub=bool(d.get("no_hub", True)))
    with SessionLocal() as db:
        empresa.slug = gerar_slug(db, empresa.nome)
        db.add(empresa)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return jsonify(erro="já existe uma empresa com esse wa_phone_number_id"), 409
        return jsonify(id=empresa.id, nome=empresa.nome, wa_phone_number_id=empresa.wa_phone_number_id,
                       no_hub=empresa.no_hub, estado=empresa.estado, slug=empresa.slug,
                       chat_url=f"/c/{empresa.slug}",
                       teste_ate=empresa.teste_ate.isoformat()), 201   # o token nunca é devolvido


@app.post("/api/responder-humano")
@exige_admin
def responder_humano():
    """O operador envia uma mensagem a um cliente cuja conversa já foi assumida por humano.
    phone_number_id = número que recebeu a conversa (da empresa, ou o partilhado)."""
    d = request.get_json(silent=True) or {}
    pnid, numero, texto = (str(d.get(k, "")).strip() for k in ("phone_number_id", "cliente_numero", "texto"))
    if not (pnid and numero and texto):
        return jsonify(erro="phone_number_id, cliente_numero e texto são obrigatórios"), 400
    with SessionLocal() as db:
        conversa = db.query(Conversa).filter_by(phone_number_id=pnid, cliente_numero=numero).one_or_none()
        if not conversa:
            return jsonify(erro="conversa não encontrada"), 404
        if not conversa.humano_assumiu:
            return jsonify(erro="esta conversa não foi assumida por humano"), 409
        if pnid == "web":   # chat web: não há envio; o cliente vê a mensagem ao consultar o servidor
            guardar(db, conversa, "human", texto)
            db.commit()
            return jsonify(enviado=True), 200
        if cfg.hub_pnid and pnid == cfg.hub_pnid:
            token = cfg.hub_token
        else:
            empresa = db.get(Empresa, conversa.empresa_id)
            token = empresa.wa_access_token if empresa else None
        if not token:
            return jsonify(erro="sem token para enviar por este número"), 500
        try:
            whatsapp.enviar_texto(token, pnid, numero, texto)
        except Exception:
            log.exception("Falha ao enviar mensagem do operador")
            return jsonify(erro="falha ao enviar pelo WhatsApp"), 502
        guardar(db, conversa, "human", texto)
        db.commit()
        return jsonify(enviado=True), 200


@app.get("/api/conversas-humano")
@exige_admin
def conversas_humano():
    """Conversas à espera de um operador (WhatsApp e chat web)."""
    with SessionLocal() as db:
        linhas = []
        for c in db.query(Conversa).filter_by(humano_assumiu=True).all():
            ultima = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id.desc()).first()
            e = db.get(Empresa, c.empresa_id) if c.empresa_id else None
            linhas.append({"empresa": e.nome if e else None, "phone_number_id": c.phone_number_id,
                           "cliente_numero": c.cliente_numero,
                           "ultima_mensagem": ultima.conteudo[:200] if ultima else None,
                           "ultimo_remetente": ultima.remetente if ultima else None})
        return jsonify(conversas=linhas)


@app.post("/api/devolver-ia")
@exige_admin
def devolver_ia():
    """O operador devolve a conversa ao bot."""
    d = request.get_json(silent=True) or {}
    pnid, numero = str(d.get("phone_number_id", "")).strip(), str(d.get("cliente_numero", "")).strip()
    with SessionLocal() as db:
        c = db.query(Conversa).filter_by(phone_number_id=pnid, cliente_numero=numero).one_or_none()
        if not c:
            return jsonify(erro="conversa não encontrada"), 404
        c.humano_assumiu = False
        db.commit()
        return jsonify(ok=True), 200


@app.post("/api/empresas/<int:empresa_id>/estado")
@exige_admin
def mudar_estado(empresa_id):
    """Ativa (depois de pagar), suspende ou volta a pôr em teste. Corpo: {"estado": "ativo|suspenso|teste", "dias": 2}"""
    d = request.get_json(silent=True) or {}
    estado = d.get("estado")
    if estado not in ("ativo", "suspenso", "teste"):
        return jsonify(erro="estado tem de ser ativo, suspenso ou teste"), 400
    with SessionLocal() as db:
        e = db.get(Empresa, empresa_id)
        if not e:
            return jsonify(erro="empresa não encontrada"), 404
        e.estado = estado
        if estado == "teste":
            try:
                dias = max(1, min(int(d.get("dias", 2)), 30))
            except (TypeError, ValueError):
                return jsonify(erro="dias tem de ser um número"), 400
            e.teste_ate = agora() + timedelta(days=dias)
        db.commit()
        return jsonify(id=e.id, estado=e.estado, teste_ate=e.teste_ate.isoformat() if e.teste_ate else None)


@app.get("/api/estatisticas")
@exige_admin
def estatisticas():
    """Por empresa, nos últimos N dias (?dias=7): pessoas diferentes, mensagens e passagens a humano."""
    try:
        dias = max(1, min(int(request.args.get("dias", 7)), 365))
    except ValueError:
        dias = 7
    desde = agora() - timedelta(days=dias)
    with SessionLocal() as db:
        resultado = []
        for e in db.query(Empresa).order_by(Empresa.id).all():
            def contar(remetente):
                return (db.query(func.count(Mensagem.id)).join(Conversa, Mensagem.conversa_id == Conversa.id)
                        .filter(Conversa.empresa_id == e.id, Mensagem.remetente == remetente,
                                Mensagem.data_hora >= desde).scalar())
            pessoas = (db.query(func.count(func.distinct(Conversa.cliente_numero)))
                       .join(Mensagem, Mensagem.conversa_id == Conversa.id)
                       .filter(Conversa.empresa_id == e.id, Mensagem.remetente == "user",
                               Mensagem.data_hora >= desde).scalar())
            resultado.append({
                "empresa": e.nome, "estado": e.estado,
                "teste_ate": e.teste_ate.isoformat() if e.teste_ate else None,
                "pessoas": pessoas, "mensagens_clientes": contar("user"),
                "respostas_ia": contar("assistant"), "respostas_equipa": contar("human"),
                "conversas_com_humano": db.query(func.count(Conversa.id)).filter(
                    Conversa.empresa_id == e.id, Conversa.humano_assumiu.is_(True)).scalar(),
            })
        return jsonify(dias=dias, empresas=resultado)


# ---------- Chat web (público) ----------
@app.get("/c/<slug>")
def pagina_chat(slug):
    """Página de chat da empresa: partilha o link ou mete num site com <iframe>."""
    with SessionLocal() as db:
        e = db.query(Empresa).filter_by(slug=slug).one_or_none()
        if not e:
            return "Empresa não encontrada", 404
        return render_template_string(PAGINA, nome=e.nome, cfg={"slug": e.slug, "nome": e.nome})


@app.post("/chat/<slug>/mensagem")
def chat_mensagem(slug):
    d = request.get_json(silent=True) or {}
    sessao, texto = str(d.get("sessao", "")), str(d.get("texto", "")).strip()
    if not SESSAO_RE.fullmatch(sessao) or not texto:
        return jsonify(erro="pedido inválido"), 400
    if len(texto) > 1000:
        return jsonify(erro="Mensagem demasiado longa (máximo 1000 caracteres)."), 400
    if limite_excedido(("ip", request.remote_addr), 60, 600) or limite_excedido(("sessao", sessao), 20, 600):
        return jsonify(erro="Muitas mensagens seguidas. Espera um pouco e tenta de novo."), 429
    with SessionLocal() as db:
        empresa = db.query(Empresa).filter_by(slug=slug).one_or_none()
        if not empresa:
            return jsonify(erro="empresa não encontrada"), 404
        conversa = obter_conversa(db, "web", sessao, empresa.id)
        if conversa.empresa_id != empresa.id:
            return jsonify(erro="sessão inválida"), 400
        guardar(db, conversa, "user", texto)
        resposta = decidir_resposta(db, empresa, conversa, texto)
        novas = []
        if resposta:
            m = guardar(db, conversa, "assistant", resposta)
            db.flush()
            novas = [{"id": m.id, "remetente": "assistant", "conteudo": resposta}]
        db.commit()
        return jsonify(mensagens=novas, humano=conversa.humano_assumiu)


@app.get("/chat/<slug>/mensagens")
def chat_mensagens(slug):
    """O chat consulta aqui as respostas novas (por exemplo, de um operador humano)."""
    sessao = request.args.get("sessao", "")
    if not SESSAO_RE.fullmatch(sessao):
        return jsonify(erro="pedido inválido"), 400
    if limite_excedido(("poll", sessao), 300, 600):
        return jsonify(erro="demasiados pedidos"), 429
    try:
        desde = int(request.args.get("desde", 0))
    except ValueError:
        desde = 0
    remetentes = ("user", "assistant", "human") if request.args.get("tudo") == "1" else ("assistant", "human")
    with SessionLocal() as db:
        empresa = db.query(Empresa).filter_by(slug=slug).one_or_none()
        if not empresa:
            return jsonify(erro="empresa não encontrada"), 404
        c = db.query(Conversa).filter_by(phone_number_id="web", cliente_numero=sessao,
                                         empresa_id=empresa.id).one_or_none()
        if not c:
            return jsonify(mensagens=[], humano=False)
        msgs = (db.query(Mensagem).filter(Mensagem.conversa_id == c.id, Mensagem.id > desde,
                                          Mensagem.remetente.in_(remetentes)).order_by(Mensagem.id).all())
        return jsonify(mensagens=[{"id": m.id, "remetente": m.remetente, "conteudo": m.conteudo} for m in msgs],
                       humano=c.humano_assumiu)


if __name__ == "__main__":
    app.run(port=3000)
