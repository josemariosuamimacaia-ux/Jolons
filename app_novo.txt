"""MacTech — servidor Flask multi-empresa para assistentes de atendimento com IA.

Canais: chat web (/c/<slug>), WhatsApp com número próprio de cada empresa e WhatsApp com número
partilhado (o bot pergunta de que empresa o cliente quer ser atendido).
"""
import csv
import hmac
import io
import json
import logging
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from functools import wraps

from flask import Flask, Response, abort, jsonify, render_template_string, request
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

import ferramentas
import ia
import nivel4
import publico
import whatsapp
from assets import ASSETS
from chat_page import PAGINA
from config import cfg
from models import Conversa, Departamento, Empresa, Mensagem, SessionLocal, agora, init_db
from segredos import cifrar, decifrar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mactech")

app = Flask(__name__, static_folder=None)   # os ficheiros do site vêm de assets.py (não de uma pasta)
if cfg.trust_proxy:   # atrás de um proxy, lê o IP real do visitante
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
try:
    init_db()
except Exception:   # não rebenta no arranque: /saude e a página de aviso mostram o problema
    log.exception("Não foi possível preparar a base de dados (confirma DATABASE_URL)")
executor = ThreadPoolExecutor(max_workers=cfg.max_workers)   # limita o trabalho em paralelo

MSG_TRANSICAO = "Claro! Vou passar a conversa a uma pessoa da equipa. Já te respondem por aqui."
MSG_SEM_HUMANO = ("De momento a equipa não está disponível para atendimento. "
                  "Deixa aqui a tua mensagem e eu ajudo no que puder.")
MSG_INDISPONIVEL = ("Este atendimento automático está temporariamente indisponível. "
                    "Por favor, contacte a empresa diretamente.")
MSG_ERRO = "Desculpa, tive um problema técnico. Tenta novamente daqui a pouco."
MSG_LIMITE = ("Recebemos muitas mensagens hoje e o atendimento automático voltou a ficar ocupado. "
              "Tenta de novo mais tarde ou contacte a empresa diretamente.")
MSG_SO_TEXTO = "De momento só consigo ler mensagens de texto. Podes escrever a tua pergunta?"
TERMOS_HUMANO = ("reclamacao", "humano", "atendente", "falar com pessoa", "falar com uma pessoa", "falar com alguem",
                 "pessoa real", "operador", "gerente", "responsavel", "falar com a equipa", "falar com um agente")
SESSAO_RE = re.compile(r"[A-Za-z0-9\-]{16,64}")
CONTACTO_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|\+?\d[\d \-]{7,}\d")


# ---------- Utilitários ----------
def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para 'Reclamação' == 'reclamacao'."""
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def pede_humano(texto: str) -> bool:
    n = normalizar(texto)
    return any(termo in n for termo in TERMOS_HUMANO)


def achar_empresa(empresas: list, texto: str):
    """Descobre a empresa escolhida: pelo número da lista, pelo nome ou por uma palavra que só ela tem."""
    n = normalizar(texto).strip()
    palavras = [set(normalizar(e.nome).split()) for e in empresas]
    achadas = []
    for i, e in enumerate(empresas):
        unica = any(len(w) > 3 and w in n and sum(w in p for p in palavras) == 1 for w in palavras[i])
        if n == str(i + 1) or normalizar(e.nome) in n or unica:
            achadas.append(e)
    return achadas[0] if len(achadas) == 1 else None


def estado_de(e) -> str:
    """Empresas de versões antigas (sem estado) contam como ativas."""
    return e.estado or "ativo"


def empresa_ativa(e) -> bool:
    """Ativa = conta paga ('ativo') ou dentro do dia de teste."""
    estado = estado_de(e)
    if estado == "ativo":
        return True
    if estado == "teste" and e.teste_ate:
        fim = e.teste_ate if e.teste_ate.tzinfo else e.teste_ate.replace(tzinfo=timezone.utc)  # SQLite devolve sem fuso
        return agora() < fim
    return False


def iso_utc(dt):
    if not dt:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


_pedidos, _trinco = {}, threading.Lock()


def limite_excedido(chave, maximo, janela):
    """Limite simples em memória (protege a IA e a chave de admin contra abuso)."""
    t = time.time()
    with _trinco:
        if len(_pedidos) > 20000:   # limpeza: apaga só as chaves já expiradas (não perdoa quem está a abusar)
            for k in [k for k, v in _pedidos.items() if not v or t - v[-1] > 3600]:
                del _pedidos[k]
        recentes = [x for x in _pedidos.get(chave, []) if t - x < janela]
        excedeu = len(recentes) >= maximo
        if not excedeu:
            recentes.append(t)
        _pedidos[chave] = recentes
        return excedeu


def exige_admin(f):
    """Protege os endpoints /api/* com a chave X-API-Key (e trava quem tenta adivinhar)."""
    @wraps(f)
    def wrapper(*a, **kw):
        chave = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(chave.encode(), cfg.admin_key.encode()):
            if limite_excedido(("admin_falhas", request.remote_addr), 10, 600):
                return jsonify(erro="demasiadas tentativas, espera uns minutos"), 429
            return jsonify(erro="não autorizado"), 401
        return f(*a, **kw)
    return wrapper


def guardar(db, conversa, remetente, conteudo, wa_id=None):
    m = Mensagem(conversa_id=conversa.id, remetente=remetente, conteudo=conteudo, wa_id=wa_id, sem_resposta=False)
    db.add(m)
    return m


def historico_ia(db, conversa, limite=10):
    """Últimas mensagens depois da escolha da empresa, no formato da IA. Tem de começar em 'user'."""
    msgs = (db.query(Mensagem)
            .filter(Mensagem.conversa_id == conversa.id, Mensagem.id > (conversa.inicio_historico_id or 0))
            .order_by(Mensagem.id.desc()).limit(limite).all())[::-1]
    hist = [{"role": "user" if m.remetente == "user" else "assistant", "content": m.conteudo} for m in msgs]
    while hist and hist[0]["role"] != "user":
        hist.pop(0)
    return hist


def obter_conversa(db, phone_number_id, numero, empresa_id):
    filtro = {"phone_number_id": phone_number_id, "cliente_numero": numero}
    c = db.query(Conversa).filter_by(**filtro).one_or_none()
    if not c:
        # No WhatsApp o contacto é o próprio número; no chat web só se o cliente o escrever
        c = Conversa(**filtro, empresa_id=empresa_id, humano_assumiu=False,
                     contacto=None if phone_number_id == "web" else numero)
        db.add(c)
        try:
            db.flush()  # gera o id
        except IntegrityError:   # outra thread criou a mesma conversa ao mesmo tempo
            db.rollback()
            c = db.query(Conversa).filter_by(**filtro).one()
    return c


def registar_contacto(conversa, texto):
    """Guarda o primeiro telefone ou email que o cliente escrever (para a empresa o contactar)."""
    if not conversa.contacto:
        m = CONTACTO_RE.search(texto)
        if m:
            conversa.contacto = m.group(0).strip()[:120]


def limite_diario_atingido(db, empresa) -> bool:
    """Protege os custos da IA: máximo de mensagens de clientes por empresa nas últimas 24 h."""
    desde = agora() - timedelta(days=1)
    n = (db.query(func.count(Mensagem.id)).join(Conversa, Mensagem.conversa_id == Conversa.id)
         .filter(Conversa.empresa_id == empresa.id, Mensagem.remetente == "user", Mensagem.data_hora >= desde).scalar())
    return n > cfg.max_dia_empresa


def preparar(db, empresa, conversa, texto):
    """Decide o que fazer com a mensagem. Devolve ('fixo', texto) para respostas sem IA, ('humano', None)
    se uma pessoa assumiu, ou ('ia', historico). Faz commit antes de a IA ser chamada, para não manter a
    base de dados bloqueada durante os segundos que a IA demora a responder."""
    if conversa.humano_assumiu:
        return "humano", None
    if not empresa_ativa(empresa):
        log.warning("[ATENÇÃO] %s: teste terminou ou conta suspensa, bot desligado", empresa.nome)
        return "fixo", MSG_INDISPONIVEL
    if pede_humano(texto):
        if empresa.humano_ativo is not False:
            conversa.humano_assumiu = True
            log.warning("[ATENÇÃO] %s: cliente %s pediu atendimento humano", empresa.nome, conversa.cliente_numero)
            return "fixo", MSG_TRANSICAO
        return "fixo", MSG_SEM_HUMANO
    if limite_diario_atingido(db, empresa):
        log.warning("[ATENÇÃO] %s: limite diário de mensagens atingido", empresa.nome)
        return "fixo", MSG_LIMITE
    hist = historico_ia(db, conversa)
    db.commit()   # liberta a base de dados antes da chamada (lenta) à IA
    return "ia", hist


def montar_ferramentas(db, empresa, conversa, hist):
    """Nível 4: prompt com departamentos, ferramentas ativas e contexto de quem fala.
    Devolve (prompt, esquemas, executar). esquemas vazio = empresa sem ferramentas (resposta normal)."""
    deps = db.query(Departamento).filter_by(empresa_id=empresa.id).order_by(Departamento.id).all()
    esquemas = ferramentas.esquemas(empresa, deps)
    prompt = empresa.system_prompt + (ferramentas.bloco_departamentos(deps) if esquemas else "")
    if not esquemas:
        return prompt, [], None
    whats = conversa.phone_number_id != "web"
    contactos = ferramentas.contactos_em([m["content"] for m in hist if m["role"] == "user"] + [conversa.contacto or ""])
    if whats:
        contactos.add(ferramentas.norm_contacto(conversa.cliente_numero))   # número da Meta: não se falsifica
    ctx = ferramentas.Contexto(empresa.id, conversa.id, contactos, verificado=whats)
    return prompt, esquemas, lambda nome, args: ferramentas.executar(ctx, nome, args)


def decidir_resposta(db, empresa, conversa, texto, msg_user):
    """Lógica comum a todos os canais. Devolve o texto a enviar, ou None se um humano assumiu."""
    tipo, dado = preparar(db, empresa, conversa, texto)
    if tipo == "humano":
        return None
    if tipo == "fixo":
        return dado
    try:
        prompt, esq, executar = montar_ferramentas(db, empresa, conversa, dado)
        resposta, sem = ia.responder(prompt, dado, esq, executar)
        if sem:
            msg_user.sem_resposta = True   # fica na lista "perguntas sem resposta" do painel
        if esq:
            db.refresh(conversa)   # uma ferramenta pode ter passado a conversa a uma pessoa
        return resposta
    except Exception as erro:
        log.error("Erro na IA: %s | %s", erro, ia.explicar_erro(str(erro)))
        return MSG_ERRO


# ---------- WhatsApp ----------
_em_curso, _trinco_wa = set(), threading.Lock()


def processar(pnid: str, msg: dict):
    """Trata UMA mensagem recebida do WhatsApp. Corre numa thread do pool."""
    wa_id = msg.get("id")
    if wa_id:
        with _trinco_wa:   # a Meta pode reenviar o mesmo pedido enquanto o primeiro ainda está a ser tratado
            if wa_id in _em_curso:
                return
            _em_curso.add(wa_id)
    try:
        _processar(pnid, msg)
    finally:
        if wa_id:
            with _trinco_wa:
                _em_curso.discard(wa_id)


def _processar(pnid: str, msg: dict):
    try:
        numero = msg["from"]
        tipo = msg.get("type")
        texto = ((msg.get("text") or {}).get("body") or "").strip()[:2000] if tipo == "text" else ""
        wa_id = msg.get("id")
        if tipo == "text" and not texto:
            return
        hub = bool(cfg.hub_pnid) and pnid == cfg.hub_pnid   # número partilhado?
        with SessionLocal() as db:
            if wa_id and db.query(Mensagem.id).filter_by(wa_id=wa_id).first():
                return   # a Meta reenviou uma mensagem que já tratámos
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
                token = decifrar(empresa.wa_access_token)
                conversa = obter_conversa(db, pnid, numero, empresa.id)

            if tipo != "text":   # áudio, imagem, etc.: avisa o cliente em vez de o deixar sem resposta
                if tipo in ("audio", "image", "video", "document", "voice", "sticker", "location"):
                    whatsapp.enviar_texto(token, pnid, numero, MSG_SO_TEXTO)
                return

            mu = guardar(db, conversa, "user", texto, wa_id)
            registar_contacto(conversa, texto)
            db.commit()   # guarda já a mensagem (e marca-a como tratada) antes de chamar a IA

            if hub and "mudar de empresa" in normalizar(texto):   # o cliente pode trocar de empresa
                conversa.empresa_id, conversa.humano_assumiu, empresa = None, False, None

            escolheu = False
            if hub and empresa is None:
                # Triagem: perceber de que empresa o cliente quer ser atendido
                empresas = [e for e in db.query(Empresa).filter(Empresa.no_hub.isnot(False)).order_by(Empresa.id).all()
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
                        resposta = f"Olá! De que empresa quer ser atendido? Responda com o número ou o nome:\n{lista}"
            else:
                resposta = decidir_resposta(db, empresa, conversa, texto, mu)
                if resposta is None:   # um humano assumiu: a IA não responde
                    db.commit()
                    log.info("[%s] %s: humano assumiu, IA calada", empresa.nome, numero)
                    return

            m = guardar(db, conversa, "assistant", resposta)
            if escolheu:
                db.flush()
                conversa.inicio_historico_id = m.id   # a IA só vê o que vier depois da escolha
            db.commit()
            whatsapp.enviar_texto(token, pnid, numero, resposta)
    except Exception:
        log.exception("Erro ao processar mensagem do WhatsApp")


@app.get("/webhook")
def verificar_webhook():
    """A Meta chama isto uma vez para confirmar o endereço."""
    if not cfg.verify_token:
        return "WhatsApp não configurado", 503
    if (request.args.get("hub.mode") == "subscribe"
            and hmac.compare_digest(request.args.get("hub.verify_token", "").encode(), cfg.verify_token.encode())):
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


# ---------- Páginas ----------
PAGINA_INICIAL = """<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacTech</title>
<link rel="stylesheet" href="/static/style.css"></head><body><main>
<h1>Mac<span>Tech</span></h1>
<p>Assistentes de atendimento com IA para empresas.</p>
<p>O servidor está a funcionar.</p>
<p><a class="btn" href="/painel">Entrar no painel</a></p>
</main></body></html>"""

PAGINA_404 = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Não encontrado</title>
<link rel="stylesheet" href="/static/style.css"></head><body><main>
<h1>Mac<span>Tech</span></h1><p>Esta página não existe.</p><p><a class="btn" href="/">Voltar ao início</a></p>
</main></body></html>"""


@app.get("/")
def inicio():
    return publico.INICIO


def _ficheiro(nome):
    a = ASSETS.get(nome)
    if not a:
        abort(404)
    return Response(a[1], content_type=a[0], headers={"Cache-Control": "public, max-age=300"})


@app.get("/static/<nome>")
def ficheiro_estatico(nome):
    """CSS e JavaScript do site (guardados em assets.py)."""
    return _ficheiro(nome)


@app.before_request
def verificar_configuracao():
    """Se faltar configuração, em vez de um erro mudo mostra o que falta (só /saude responde normalmente)."""
    if cfg.problemas and request.path not in ("/saude", "/health"):
        itens = "".join(f"<li>{p}</li>" for p in cfg.problemas)
        return (f"<!DOCTYPE html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<body style='font-family:sans-serif;max-width:560px;margin:2rem auto;padding:0 1rem'>"
                f"<h1>MacTech: falta configurar</h1><p>No Render: serviço, Environment, adiciona:</p><ul>{itens}</ul>"
                f"<p>Guarda e espera o novo deploy.</p>", 503)


@app.get("/agente")
def agente_pagina():
    """Página dos atendentes humanos (entram com a chave pessoal)."""
    return _ficheiro("agente.html")


@app.get("/painel")
def painel():
    """A página é pública, mas todos os dados exigem a ADMIN_API_KEY."""
    return _ficheiro("painel.html")


@app.get("/saude")
@app.get("/health")
def saude():
    if cfg.problemas:
        return jsonify(status="erro", em_falta=list(cfg.problemas)), 503
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        log.exception("Base de dados indisponível")
        return jsonify(status="erro"), 503
    return jsonify(status="ok")


# ---------- API de administração ----------
def texto_valido(d, campo, maximo):
    v = str(d.get(campo) or "").strip()
    return v if 0 < len(v) <= maximo else None


def gerar_slug(db, nome):
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(nome)).strip("-")[:50] or "empresa"
    slug, i = base, 2
    while db.query(Empresa).filter_by(slug=slug).first():
        slug, i = f"{base}-{i}", i + 1
    return slug


@app.get("/api/empresas")
@exige_admin
def listar_empresas():
    with SessionLocal() as db:
        return jsonify(empresas=[{
            "id": e.id, "nome": e.nome, "slug": e.slug, "estado": estado_de(e), "ativa": empresa_ativa(e),
            "teste_ate": iso_utc(e.teste_ate), "humano_ativo": e.humano_ativo is not False,
            "chat_url": f"/c/{e.slug}" if e.slug else None, "tem_whatsapp": bool(e.wa_phone_number_id),
        } for e in db.query(Empresa).order_by(Empresa.id).all()])


@app.post("/api/empresas")
@exige_admin
def criar_empresa():
    """Regista uma empresa. Número próprio (wa_phone_number_id + wa_access_token) é opcional."""
    d = request.get_json(silent=True) or {}
    nome, prompt = texto_valido(d, "nome", 120), texto_valido(d, "system_prompt", 20000)
    erros = [c for c, v in (("nome (1 a 120 caracteres)", nome), ("system_prompt (1 a 20000 caracteres)", prompt)) if not v]
    pnid = str(d.get("wa_phone_number_id") or "").strip()[:40] or None
    token = str(d.get("wa_access_token") or "").strip() or None
    token_cifrado = cifrar(token) if token else None
    if pnid and not token:
        erros.append("wa_access_token")
    if erros:
        return jsonify(erro="campos em falta ou inválidos", campos=erros), 400
    empresa = Empresa(nome=nome, wa_phone_number_id=pnid, wa_access_token=token_cifrado, system_prompt=prompt,
                      humano_ativo=bool(d.get("humano_ativo", True)), no_hub=bool(d.get("no_hub", True)))
    with SessionLocal() as db:
        empresa.slug = gerar_slug(db, nome)
        db.add(empresa)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            log.exception("Não foi possível registar a empresa")
            return jsonify(erro="Não foi possível registar: já existe esse número de WhatsApp, "
                                "ou a base de dados é de uma versão antiga (apaga-a e deixa o servidor recriá-la)."), 409
        return jsonify(id=empresa.id, nome=empresa.nome, wa_phone_number_id=empresa.wa_phone_number_id,
                       no_hub=empresa.no_hub, estado=empresa.estado, slug=empresa.slug,
                       chat_url=f"/c/{empresa.slug}", teste_ate=iso_utc(empresa.teste_ate)), 201


@app.post("/api/empresas/<int:empresa_id>/estado")
@exige_admin
def mudar_estado(empresa_id):
    """Ativa (depois de pagar), suspende ou volta a pôr em teste. Corpo: {"estado": "ativo|suspenso|teste", "dias": 1}"""
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
                dias = max(1, min(int(d.get("dias", 1)), 30))
            except (TypeError, ValueError):
                return jsonify(erro="dias tem de ser um número"), 400
            e.teste_ate = agora() + timedelta(days=dias)
        db.commit()
        return jsonify(id=e.id, estado=e.estado, teste_ate=iso_utc(e.teste_ate))


def _dias(padrao, maximo=365):
    try:
        return max(1, min(int(request.args.get("dias", padrao)), maximo))
    except ValueError:
        return padrao


@app.get("/api/estatisticas")
@exige_admin
def estatisticas():
    """Por empresa, nos últimos N dias (?dias=7): pessoas, mensagens, passagens a humano e perguntas sem resposta."""
    dias = _dias(7)
    desde = agora() - timedelta(days=dias)
    with SessionLocal() as db:
        resultado = []
        for e in db.query(Empresa).order_by(Empresa.id).all():
            def contar(remetente=None, sem=False):
                q = (db.query(func.count(Mensagem.id)).join(Conversa, Mensagem.conversa_id == Conversa.id)
                     .filter(Conversa.empresa_id == e.id, Mensagem.data_hora >= desde))
                if remetente:
                    q = q.filter(Mensagem.remetente == remetente)
                if sem:
                    q = q.filter(Mensagem.sem_resposta.is_(True))
                return q.scalar()
            pessoas = (db.query(func.count(func.distinct(Conversa.cliente_numero)))
                       .join(Mensagem, Mensagem.conversa_id == Conversa.id)
                       .filter(Conversa.empresa_id == e.id, Mensagem.remetente == "user",
                               Mensagem.data_hora >= desde).scalar())
            resultado.append({
                "empresa": e.nome, "estado": estado_de(e), "teste_ate": iso_utc(e.teste_ate),
                "pessoas": pessoas, "mensagens_clientes": contar("user"),
                "respostas_ia": contar("assistant"), "respostas_equipa": contar("human"),
                "perguntas_sem_resposta": contar(sem=True),
                "contactos_recolhidos": db.query(func.count(Conversa.id)).filter(
                    Conversa.empresa_id == e.id, Conversa.contacto.isnot(None)).scalar(),
                "conversas_com_humano": db.query(func.count(Conversa.id)).filter(
                    Conversa.empresa_id == e.id, Conversa.humano_assumiu.is_(True)).scalar(),
            })
        return jsonify(dias=dias, empresas=resultado)


def _canal(c):
    return "chat web" if c.phone_number_id == "web" else "WhatsApp"


@app.get("/api/conversas")
@exige_admin
def listar_conversas():
    """Últimas conversas (?empresa_id=1&limite=30), para a empresa ver o que os clientes perguntam."""
    try:
        limite = max(1, min(int(request.args.get("limite", 30)), 100))
    except ValueError:
        limite = 30
    with SessionLocal() as db:
        q = db.query(Conversa).order_by(Conversa.id.desc())
        if request.args.get("empresa_id", "").isdigit():
            q = q.filter(Conversa.empresa_id == int(request.args["empresa_id"]))
        linhas = []
        for c in q.limit(limite).all():
            ult = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id.desc()).first()
            e = db.get(Empresa, c.empresa_id) if c.empresa_id else None
            linhas.append({
                "id": c.id, "empresa": e.nome if e else None, "canal": _canal(c),
                "cliente": c.cliente_numero if c.phone_number_id != "web" else c.cliente_numero[:8] + "…",
                "contacto": c.contacto, "humano_assumiu": bool(c.humano_assumiu),
                "mensagens": db.query(func.count(Mensagem.id)).filter_by(conversa_id=c.id).scalar(),
                "ultima_mensagem": ult.conteudo[:160] if ult else None,
                "quando": iso_utc(ult.data_hora) if ult else None})
        return jsonify(conversas=linhas)


@app.get("/api/conversas/<int:conversa_id>")
@exige_admin
def ver_conversa(conversa_id):
    with SessionLocal() as db:
        c = db.get(Conversa, conversa_id)
        if not c:
            return jsonify(erro="conversa não encontrada"), 404
        msgs = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id).all()
        return jsonify(id=c.id, canal=_canal(c), contacto=c.contacto, humano_assumiu=bool(c.humano_assumiu),
                       mensagens=[{"id": m.id, "remetente": m.remetente, "conteudo": m.conteudo,
                                   "quando": iso_utc(m.data_hora), "sem_resposta": bool(m.sem_resposta)} for m in msgs])


@app.get("/api/sem-resposta")
@exige_admin
def sem_resposta():
    """Perguntas que o bot não soube responder: a empresa deve acrescentá-las ao catálogo."""
    desde = agora() - timedelta(days=_dias(30))
    with SessionLocal() as db:
        linhas = (db.query(Mensagem, Conversa).join(Conversa, Mensagem.conversa_id == Conversa.id)
                  .filter(Mensagem.sem_resposta.is_(True), Mensagem.data_hora >= desde)
                  .order_by(Mensagem.id.desc()).limit(100).all())
        out = []
        for m, c in linhas:
            e = db.get(Empresa, c.empresa_id) if c.empresa_id else None
            out.append({"empresa": e.nome if e else None, "pergunta": m.conteudo, "quando": iso_utc(m.data_hora)})
        return jsonify(perguntas=out)


def _csv_seguro(v):
    """Evita que o Excel execute células que começam por = + - @."""
    v = "" if v is None else str(v).replace("\n", " ")
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@app.get("/api/exportar.csv")
@exige_admin
def exportar_csv():
    """Contactos e conversas em CSV (abre no Excel). ?empresa_id=1 para uma só empresa."""
    saida = io.StringIO()
    w = csv.writer(saida)
    w.writerow(["empresa", "canal", "contacto", "pediu_humano", "mensagens", "primeira_mensagem", "ultima_mensagem", "data"])
    with SessionLocal() as db:
        q = db.query(Conversa).order_by(Conversa.id.desc())
        if request.args.get("empresa_id", "").isdigit():
            q = q.filter(Conversa.empresa_id == int(request.args["empresa_id"]))
        for c in q.limit(1000).all():
            e = db.get(Empresa, c.empresa_id) if c.empresa_id else None
            msgs = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id).all()
            pri = next((m for m in msgs if m.remetente == "user"), None)
            w.writerow([_csv_seguro(x) for x in (
                e.nome if e else "", _canal(c), c.contacto or "", "sim" if c.humano_assumiu else "não", len(msgs),
                pri.conteudo[:200] if pri else "", msgs[-1].conteudo[:200] if msgs else "",
                iso_utc(msgs[-1].data_hora) if msgs else "")])
    return Response("\ufeff" + saida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=mactech_conversas.csv"})


@app.post("/api/diagnostico")
@exige_admin
def diagnostico():
    """Confirma base de dados, chave da IA, crédito e modelo, com mensagens claras."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        base = True
    except Exception:
        log.exception("Diagnóstico: base de dados com problemas")
        base = False
    return jsonify(base_de_dados=base, ia=ia.diagnosticar(), modelo=cfg.ai_model,
                   whatsapp_configurado=bool(cfg.app_secret and cfg.verify_token),
                   numero_partilhado=bool(cfg.hub_pnid))


@app.get("/api/conversas-humano")
@exige_admin
def conversas_humano():
    """Conversas à espera de um operador (WhatsApp e chat web)."""
    with SessionLocal() as db:
        linhas = []
        for c in db.query(Conversa).filter_by(humano_assumiu=True).all():
            ultima = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id.desc()).first()
            e = db.get(Empresa, c.empresa_id) if c.empresa_id else None
            linhas.append({"id": c.id, "empresa": e.nome if e else None, "phone_number_id": c.phone_number_id,
                           "cliente_numero": c.cliente_numero, "contacto": c.contacto,
                           "ultima_mensagem": ultima.conteudo[:200] if ultima else None,
                           "ultimo_remetente": ultima.remetente if ultima else None})
        return jsonify(conversas=linhas)


def enviar_humano(db, conversa, texto):
    """Envia a mensagem de uma pessoa ao cliente (WhatsApp ou chat web) e guarda-a. Devolve (corpo, estado HTTP)."""
    if conversa.phone_number_id == "web":   # chat web: o cliente vê a mensagem ao consultar o servidor
        guardar(db, conversa, "human", texto)
        db.commit()
        return {"enviado": True}, 200
    if cfg.hub_pnid and conversa.phone_number_id == cfg.hub_pnid:
        token = cfg.hub_token
    else:
        empresa = db.get(Empresa, conversa.empresa_id) if conversa.empresa_id else None
        token = decifrar(empresa.wa_access_token) if empresa else None
    if not token:
        return {"erro": "sem token para enviar por este número"}, 500
    try:
        whatsapp.enviar_texto(token, conversa.phone_number_id, conversa.cliente_numero, texto)
    except Exception:
        log.exception("Falha ao enviar mensagem do operador")
        return {"erro": "falha ao enviar pelo WhatsApp"}, 502
    guardar(db, conversa, "human", texto)
    db.commit()
    return {"enviado": True}, 200


@app.post("/api/responder-humano")
@exige_admin
def responder_humano():
    """O operador envia uma mensagem a um cliente cuja conversa já foi assumida por humano.
    phone_number_id = número que recebeu a conversa (da empresa, o partilhado, ou "web")."""
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
        corpo, estado = enviar_humano(db, conversa, texto)
        return jsonify(corpo), estado


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
        c.humano_assumiu, c.agente_id, c.departamento_id = False, None, None
        db.commit()
        return jsonify(ok=True), 200


# ---------- Chat web (público) ----------
@app.get("/c/<slug>")
def pagina_chat(slug):
    """Página de chat da empresa: partilha o link ou mete num site com <iframe>."""
    with SessionLocal() as db:
        e = db.query(Empresa).filter_by(slug=slug).one_or_none()
        if not e:
            return PAGINA_404, 404
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
        mu = guardar(db, conversa, "user", texto)
        registar_contacto(conversa, texto)
        resposta = decidir_resposta(db, empresa, conversa, texto, mu)
        novas = []
        if resposta:
            m = guardar(db, conversa, "assistant", resposta)
            db.flush()
            novas = [{"id": m.id, "remetente": "assistant", "conteudo": resposta}]
        db.commit()
        return jsonify(mensagens=novas, humano=bool(conversa.humano_assumiu))


def _sse(obj) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


@app.post("/chat/<slug>/stream")
def chat_stream(slug):
    """Como /mensagem, mas a resposta da IA chega aos poucos (o cliente vê o texto a aparecer).
    Se não houver IA a responder (pessoa assumiu, mensagem fixa), devolve JSON normal."""
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
        mu = guardar(db, conversa, "user", texto)
        registar_contacto(conversa, texto)
        tipo, dado = preparar(db, empresa, conversa, texto)
        if tipo != "ia":
            novas = []
            if tipo == "fixo":
                m = guardar(db, conversa, "assistant", dado)
                db.flush()
                novas = [{"id": m.id, "remetente": "assistant", "conteudo": dado}]
            db.commit()
            return jsonify(mensagens=novas, humano=bool(conversa.humano_assumiu))
        db.flush()
        prompt, esq, executar = montar_ferramentas(db, empresa, conversa, dado)
        conversa_id, mu_id = conversa.id, mu.id

    def gerar():
        parcial, final, sem, guardado = "", None, False, False
        try:
            try:
                if esq:   # nível 4: com ferramentas a resposta chega inteira (a IA consulta sistemas antes de responder)
                    final, sem = ia.responder(prompt, dado, esq, executar)
                    yield _sse({"substituir": final})
                else:
                    for ev in ia.responder_stream(prompt, dado):
                        if ev[0] == "texto":
                            parcial += ev[1]
                            yield _sse({"t": ev[1]})
                        else:
                            _, final, sem = ev
            except Exception as erro:
                log.error("Erro na IA (stream): %s | %s", erro, ia.explicar_erro(str(erro)))
                if not parcial.strip():
                    final = MSG_ERRO
                    yield _sse({"substituir": final})
                else:
                    final = parcial.strip()
            if final is not None and parcial.strip() and final != parcial.strip():
                yield _sse({"substituir": final})   # texto final limpo (ex.: resposta cortada na última frase)
        finally:
            # corre mesmo que o cliente feche a página a meio: a conversa fica sempre completa na base de dados
            texto_guardar = (final if final is not None else parcial).strip()
            m = None
            if texto_guardar and not guardado:
                try:
                    with SessionLocal() as db2:
                        m = Mensagem(conversa_id=conversa_id, remetente="assistant", conteudo=texto_guardar, sem_resposta=False)
                        db2.add(m)
                        if sem:
                            u = db2.get(Mensagem, mu_id)
                            if u:
                                u.sem_resposta = True
                        db2.commit()
                        guardado = True
                except Exception:
                    log.exception("Não foi possível guardar a resposta da IA")
        if m is not None:
            with SessionLocal() as db3:
                c3 = db3.get(Conversa, conversa_id)
                yield _sse({"fim": True, "id": m.id, "humano": bool(c3 and c3.humano_assumiu)})

    return Response(gerar(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


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
        c = db.query(Conversa).filter_by(phone_number_id="web", cliente_numero=sessao, empresa_id=empresa.id).one_or_none()
        if not c:
            return jsonify(mensagens=[], humano=False)
        msgs = (db.query(Mensagem).filter(Mensagem.conversa_id == c.id, Mensagem.id > desde,
                                          Mensagem.remetente.in_(remetentes)).order_by(Mensagem.id).all())
        return jsonify(mensagens=[{"id": m.id, "remetente": m.remetente, "conteudo": m.conteudo} for m in msgs],
                       humano=bool(c.humano_assumiu))


# ---------- Erros e segurança ----------
@app.errorhandler(404)
def nao_encontrado(_):
    if request.path.startswith(("/api/", "/chat/")):
        return jsonify(erro="não encontrado"), 404
    return PAGINA_404, 404


@app.errorhandler(Exception)
def erro_geral(e):
    if isinstance(e, HTTPException):   # 400, 405, etc.: deixa o Flask responder
        if request.path.startswith(("/api/", "/chat/")):
            return jsonify(erro=e.description), e.code
        return e
    log.exception("Erro não tratado em %s", request.path)
    if request.path.startswith(("/api/", "/chat/")):
        return jsonify(erro="erro interno do servidor"), 500
    return "Erro interno. Tenta novamente daqui a pouco.", 500


@app.after_request
def cabecalhos(r):
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.path.startswith(("/painel", "/agente")):
        r.headers["X-Frame-Options"] = "DENY"     # o painel não pode ser metido num iframe
        r.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    if request.path.startswith(("/api/", "/chat/")):
        r.headers["Cache-Control"] = "no-store"
    return r


nivel4.registar(app, exige_admin, limite_excedido, iso_utc, enviar_humano, texto_valido)
publico.registar(app, exige_admin, limite_excedido, empresa_ativa, gerar_slug)

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 3000))   # o Render define PORT
    app.run(host="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1", port=porta)
