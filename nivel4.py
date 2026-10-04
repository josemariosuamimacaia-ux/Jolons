"""Nível 4 (bot corporativo): departamentos, vários atendentes humanos, catálogo/encomendas, tickets e
ligação ao CRM/ERP da empresa. As rotas de administração usam a ADMIN_API_KEY; as dos atendentes usam a
chave pessoal de cada um (X-Agent-Key)."""
import hashlib
import logging
import secrets
from functools import wraps

from flask import g, jsonify, request
from sqlalchemy.exc import IntegrityError

import ferramentas
from models import (Agente, Conversa, Departamento, Empresa, Encomenda, Mensagem, Produto, SessionLocal, Ticket)
from segredos import cifrar

log = logging.getLogger("mactech.nivel4")


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode()).hexdigest()


def _num(v, padrao=None):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return padrao


def registar(app, exige_admin, limite_excedido, iso_utc, enviar_humano, texto_valido):

    # ===================== Administração =====================
    @app.route("/api/empresas/<int:eid>/departamentos", methods=["GET", "POST"])
    @exige_admin
    def departamentos(eid):
        with SessionLocal() as db:
            if not db.get(Empresa, eid):
                return jsonify(erro="empresa não encontrada"), 404
            if request.method == "POST":
                d = request.get_json(silent=True) or {}
                nome = texto_valido(d, "nome", 60)
                if not nome:
                    return jsonify(erro="nome (1 a 60 caracteres) é obrigatório"), 400
                db.add(Departamento(empresa_id=eid, nome=nome, descricao=(str(d.get("descricao") or "").strip()[:200] or None)))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    return jsonify(erro="já existe um departamento com esse nome"), 409
            return jsonify(departamentos=[{"id": x.id, "nome": x.nome, "descricao": x.descricao}
                                          for x in db.query(Departamento).filter_by(empresa_id=eid).order_by(Departamento.id)])

    @app.route("/api/empresas/<int:eid>/agentes", methods=["GET", "POST"])
    @exige_admin
    def agentes(eid):
        with SessionLocal() as db:
            if not db.get(Empresa, eid):
                return jsonify(erro="empresa não encontrada"), 404
            deps = {x.id: x.nome for x in db.query(Departamento).filter_by(empresa_id=eid)}
            extra = {}
            if request.method == "POST":
                d = request.get_json(silent=True) or {}
                nome = texto_valido(d, "nome", 80)
                if not nome:
                    return jsonify(erro="nome é obrigatório"), 400
                dep_id = None
                if str(d.get("departamento") or "").strip():
                    dep_id = next((i for i, n in deps.items() if n.lower() == str(d["departamento"]).strip().lower()), None)
                    if dep_id is None:
                        return jsonify(erro="departamento inexistente"), 400
                chave = secrets.token_urlsafe(24)
                db.add(Agente(empresa_id=eid, nome=nome, chave_hash=_hash(chave), departamento_id=dep_id, ativo=True))
                db.commit()
                extra = {"chave": chave, "aviso": "Guarda esta chave agora: não volta a ser mostrada. O atendente entra em /agente."}
            lista = [{"id": a.id, "nome": a.nome, "departamento": deps.get(a.departamento_id), "ativo": bool(a.ativo)}
                     for a in db.query(Agente).filter_by(empresa_id=eid).order_by(Agente.id)]
            return jsonify(agentes=lista, **extra), (201 if extra else 200)

    @app.post("/api/agentes/<int:aid>/ativo")
    @exige_admin
    def agente_ativo(aid):
        d = request.get_json(silent=True) or {}
        with SessionLocal() as db:
            a = db.get(Agente, aid)
            if not a:
                return jsonify(erro="atendente não encontrado"), 404
            a.ativo = bool(d.get("ativo", True))
            db.commit()
            return jsonify(id=a.id, ativo=a.ativo)

    @app.post("/api/empresas/<int:eid>/integracao")
    @exige_admin
    def integracao(eid):
        """Ferramentas ativas e ligação opcional ao sistema da empresa. Corpo:
        {"ferramentas":["stock","encomendas","fatura","departamentos"], "url":"https://...", "segredo":"..."}"""
        d = request.get_json(silent=True) or {}
        with SessionLocal() as db:
            e = db.get(Empresa, eid)
            if not e:
                return jsonify(erro="empresa não encontrada"), 404
            if "ferramentas" in d:
                lista = d["ferramentas"] if isinstance(d["ferramentas"], list) else []
                invalidas = [x for x in lista if x not in ferramentas.TODAS]
                if invalidas:
                    return jsonify(erro="ferramentas inválidas", validas=list(ferramentas.TODAS), invalidas=invalidas), 400
                e.ferramentas = ",".join(x for x in ferramentas.TODAS if x in lista)
            if "url" in d:
                url = str(d.get("url") or "").strip()
                if url and not ferramentas.url_segura(url):
                    return jsonify(erro="a url tem de ser https e pública (não aceitamos endereços internos)"), 400
                e.integracao_url = url or None
            if d.get("segredo"):
                e.integracao_segredo = cifrar(str(d["segredo"]).strip()[:200])
            if e.integracao_url and not e.integracao_segredo:
                return jsonify(erro="define também o segredo (usado para assinar os pedidos)"), 400
            db.commit()
            return jsonify(ferramentas=sorted(ferramentas.ativas(e)), url=e.integracao_url, tem_segredo=bool(e.integracao_segredo))

    @app.post("/api/empresas/<int:eid>/produtos")
    @exige_admin
    def importar_produtos(eid):
        """Cria ou atualiza produtos: {"produtos":[{"sku":"A1","nome":"...","preco":1000,"stock":5}]} (até 500)."""
        itens = (request.get_json(silent=True) or {}).get("produtos")
        if not isinstance(itens, list) or not itens or len(itens) > 500:
            return jsonify(erro="envia 1 a 500 produtos em 'produtos'"), 400
        with SessionLocal() as db:
            if not db.get(Empresa, eid):
                return jsonify(erro="empresa não encontrada"), 404
            n = 0
            for it in itens:
                if not isinstance(it, dict):
                    continue
                sku, nome = str(it.get("sku") or "").strip().upper()[:40], str(it.get("nome") or "").strip()[:160]
                if not sku or not nome:
                    continue
                p = db.query(Produto).filter_by(empresa_id=eid, sku=sku).one_or_none() or Produto(empresa_id=eid, sku=sku)
                p.nome, p.preco = nome, _num(it.get("preco"))
                p.stock = max(0, int(_num(it.get("stock"), 0) or 0))
                db.add(p)
                n += 1
            db.commit()
            return jsonify(importados=n)

    @app.post("/api/empresas/<int:eid>/encomendas")
    @exige_admin
    def importar_encomendas(eid):
        """{"encomendas":[{"codigo":"E100","contacto":"+244923000000","estado":"Enviada","itens":"...","total":5000}]}"""
        itens = (request.get_json(silent=True) or {}).get("encomendas")
        if not isinstance(itens, list) or not itens or len(itens) > 500:
            return jsonify(erro="envia 1 a 500 encomendas em 'encomendas'"), 400
        with SessionLocal() as db:
            if not db.get(Empresa, eid):
                return jsonify(erro="empresa não encontrada"), 404
            n = 0
            for it in itens:
                if not isinstance(it, dict):
                    continue
                cod = str(it.get("codigo") or "").strip().upper()[:40]
                contacto, estado = str(it.get("contacto") or "").strip()[:120], str(it.get("estado") or "").strip()[:60]
                if not (cod and contacto and estado):
                    continue
                e = db.query(Encomenda).filter_by(empresa_id=eid, codigo=cod).one_or_none() or Encomenda(empresa_id=eid, codigo=cod)
                e.contacto, e.estado = contacto, estado
                e.itens, e.total = (str(it.get("itens") or "")[:1000] or None), _num(it.get("total"))
                db.add(e)
                n += 1
            db.commit()
            return jsonify(importadas=n)

    def _ticket_json(t, db):
        return {"id": t.id, "empresa_id": t.empresa_id, "departamento": t.departamento, "tipo": t.tipo,
                "assunto": t.assunto, "estado": t.estado, "conversa_id": t.conversa_id, "criado": iso_utc(t.criado)}

    @app.get("/api/tickets")
    @exige_admin
    def tickets_admin():
        with SessionLocal() as db:
            q = db.query(Ticket).order_by(Ticket.id.desc())
            if request.args.get("empresa_id", "").isdigit():
                q = q.filter(Ticket.empresa_id == int(request.args["empresa_id"]))
            q = q.filter(Ticket.estado == ("fechado" if request.args.get("estado") == "fechado" else "aberto"))
            return jsonify(tickets=[_ticket_json(t, db) for t in q.limit(100)])

    @app.post("/api/tickets/<int:tid>/fechar")
    @exige_admin
    def fechar_ticket_admin(tid):
        with SessionLocal() as db:
            t = db.get(Ticket, tid)
            if not t:
                return jsonify(erro="ticket não encontrado"), 404
            t.estado = "fechado"
            db.commit()
            return jsonify(id=t.id, estado=t.estado)

    # ===================== Atendentes humanos =====================
    def exige_agente(f):
        @wraps(f)
        def wrapper(*a, **kw):
            chave = request.headers.get("X-Agent-Key", "")
            if limite_excedido(("agente_tent", request.remote_addr), 40, 600):
                return jsonify(erro="demasiadas tentativas, espera uns minutos"), 429
            with SessionLocal() as db:
                ag = db.query(Agente).filter_by(chave_hash=_hash(chave)).one_or_none() if chave else None
                if not ag or not ag.ativo:
                    return jsonify(erro="não autorizado"), 401
                g.ag = {"id": ag.id, "empresa_id": ag.empresa_id, "dep": ag.departamento_id, "nome": ag.nome}
            return f(*a, **kw)
        return wrapper

    def _visivel(ag, c):
        """Um atendente só vê conversas da sua empresa, à espera de pessoa, do seu departamento e não tomadas por outro."""
        return (c.empresa_id == ag["empresa_id"] and bool(c.humano_assumiu)
                and (c.departamento_id is None or ag["dep"] is None or c.departamento_id == ag["dep"])
                and c.agente_id in (None, ag["id"]))

    @app.get("/api/agente/eu")
    @exige_agente
    def agente_eu():
        with SessionLocal() as db:
            e = db.get(Empresa, g.ag["empresa_id"])
            dep = db.get(Departamento, g.ag["dep"]) if g.ag["dep"] else None
            return jsonify(nome=g.ag["nome"], empresa=e.nome if e else None, departamento=dep.nome if dep else "todos")

    @app.get("/api/agente/fila")
    @exige_agente
    def agente_fila():
        ag = g.ag
        with SessionLocal() as db:
            deps = {x.id: x.nome for x in db.query(Departamento).filter_by(empresa_id=ag["empresa_id"])}
            linhas = []
            for c in db.query(Conversa).filter_by(empresa_id=ag["empresa_id"], humano_assumiu=True).order_by(Conversa.id).limit(200):
                if not _visivel(ag, c):
                    continue
                ult = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id.desc()).first()
                linhas.append({"id": c.id, "canal": "chat web" if c.phone_number_id == "web" else "WhatsApp",
                               "cliente": c.cliente_numero if c.phone_number_id != "web" else c.cliente_numero[:8] + "…",
                               "contacto": c.contacto, "departamento": deps.get(c.departamento_id),
                               "minha": c.agente_id == ag["id"], "livre": c.agente_id is None,
                               "ultima_mensagem": ult.conteudo[:160] if ult else None,
                               "ultimo_remetente": ult.remetente if ult else None})
            return jsonify(conversas=linhas)

    @app.get("/api/agente/conversa/<int:cid>")
    @exige_agente
    def agente_conversa(cid):
        with SessionLocal() as db:
            c = db.get(Conversa, cid)
            if not c or not _visivel(g.ag, c):
                return jsonify(erro="conversa não encontrada"), 404
            msgs = db.query(Mensagem).filter_by(conversa_id=c.id).order_by(Mensagem.id).limit(300).all()
            return jsonify(id=c.id, contacto=c.contacto, minha=c.agente_id == g.ag["id"],
                           mensagens=[{"remetente": m.remetente, "conteudo": m.conteudo, "quando": iso_utc(m.data_hora)} for m in msgs])

    @app.post("/api/agente/assumir")
    @exige_agente
    def agente_assumir():
        cid = (request.get_json(silent=True) or {}).get("conversa_id")
        if not isinstance(cid, int):
            return jsonify(erro="conversa_id inválido"), 400
        with SessionLocal() as db:
            c = db.get(Conversa, cid)
            if not c or not _visivel(g.ag, c):
                return jsonify(erro="conversa não encontrada"), 404
            # Atómico: se dois atendentes clicam ao mesmo tempo, só um fica com a conversa
            tomou = db.query(Conversa).filter(Conversa.id == cid, Conversa.agente_id.is_(None)).update({"agente_id": g.ag["id"]})
            db.commit()
            if not tomou and c.agente_id != g.ag["id"]:
                return jsonify(erro="outro atendente já assumiu esta conversa"), 409
            return jsonify(ok=True)

    @app.post("/api/agente/responder")
    @exige_agente
    def agente_responder():
        d = request.get_json(silent=True) or {}
        cid, texto = d.get("conversa_id"), str(d.get("texto") or "").strip()[:2000]
        if not isinstance(cid, int) or not texto:
            return jsonify(erro="conversa_id e texto são obrigatórios"), 400
        with SessionLocal() as db:
            c = db.get(Conversa, cid)
            if not c or not _visivel(g.ag, c):
                return jsonify(erro="conversa não encontrada"), 404
            if c.agente_id != g.ag["id"]:
                return jsonify(erro="assume a conversa primeiro"), 409
            corpo, estado = enviar_humano(db, c, texto)
            return jsonify(corpo), estado

    @app.post("/api/agente/devolver")
    @exige_agente
    def agente_devolver():
        cid = (request.get_json(silent=True) or {}).get("conversa_id")
        if not isinstance(cid, int):
            return jsonify(erro="conversa_id inválido"), 400
        with SessionLocal() as db:
            c = db.get(Conversa, cid)
            if not c or not _visivel(g.ag, c):
                return jsonify(erro="conversa não encontrada"), 404
            c.humano_assumiu, c.agente_id, c.departamento_id = False, None, None
            db.commit()
            return jsonify(ok=True)

    @app.get("/api/agente/tickets")
    @exige_agente
    def agente_tickets():
        with SessionLocal() as db:
            deps = {x.id: x.nome for x in db.query(Departamento).filter_by(empresa_id=g.ag["empresa_id"])}
            q = db.query(Ticket).filter_by(empresa_id=g.ag["empresa_id"], estado="aberto")
            if g.ag["dep"]:   # só os do seu departamento (ou sem departamento)
                q = q.filter((Ticket.departamento == deps.get(g.ag["dep"])) | (Ticket.departamento.is_(None)))
            return jsonify(tickets=[_ticket_json(t, db) for t in q.order_by(Ticket.id.desc()).limit(100)])

    @app.post("/api/agente/tickets/<int:tid>/fechar")
    @exige_agente
    def agente_fechar_ticket(tid):
        with SessionLocal() as db:
            t = db.get(Ticket, tid)
            if not t or t.empresa_id != g.ag["empresa_id"]:
                return jsonify(erro="ticket não encontrado"), 404
            t.estado = "fechado"
            db.commit()
            return jsonify(id=t.id, estado=t.estado)
