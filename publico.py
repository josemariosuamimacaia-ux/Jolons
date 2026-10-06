"""Páginas públicas da MacTech: início com 3 botões, lista de empresas para clientes e registo de empresas.

Só o Dono (botão "Dono" -> /painel) usa a chave de administração. Clientes e empresas nunca a veem.
Empresas que se registam sozinhas ficam 'pendentes' (invisíveis aos clientes) até o dono confirmar o
pagamento e carregar em "Ativar (pagou)" no painel."""
import logging
import os

from flask import jsonify, render_template_string, request
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, Empresa, SessionLocal, agora, engine

log = logging.getLogger("mactech.publico")


class PedidoEmpresa(Base):
    """Dados de contacto e de pagamento de uma empresa que se registou sozinha (só o dono os vê)."""
    __tablename__ = "pedidos_empresa"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresas.id"), index=True)
    contacto: Mapped[str] = mapped_column(String(120))
    ref_pagamento: Mapped[str] = mapped_column(String(120))
    aceitou_termos_em: Mapped[object] = mapped_column(DateTime(timezone=True), default=agora)


Base.metadata.create_all(engine)   # cria só a tabela nova, se ainda não existir

TERMOS = """MODELO DE TERMOS (o dono deve rever e adaptar com um advogado antes de usar com clientes reais)

1. Serviço: a MacTech fornece um assistente de atendimento com inteligência artificial, que responde a clientes da empresa por chat e/ou WhatsApp com base nas informações que a empresa fornece.
2. Informação da empresa: a empresa é responsável pela exactidão e actualização das informações (produtos, preços, horários). O assistente usa apenas essas informações, mas pode cometer erros; a empresa deve acompanhar as conversas.
3. Pagamento: o serviço é activado depois de a MacTech confirmar o pagamento inicial. Sem pagamento confirmado, a empresa não aparece aos clientes.
4. Teste: as empresas abordadas pela MacTech podem ter um período de teste gratuito de 1 dia.
5. Dados: as conversas entre clientes e o assistente são guardadas para prestar o serviço e melhorar o atendimento. A empresa deve informar os seus clientes disso.
6. Suspensão: a MacTech pode suspender o serviço por falta de pagamento, uso abusivo ou conteúdo ilegal.
7. Limites: o serviço pode ficar indisponível por falhas técnicas ou dos fornecedores de IA, sem que isso dê direito a indemnização."""

# ---------- páginas ----------
BASE_CSS = """<style>
body{margin:0;background:#e9f0ec;color:#10201e;font:16px/1.5 system-ui,sans-serif;padding:20px}
@media(prefers-color-scheme:dark){body{background:#0d1917;color:#e6f1ed}.card,input,textarea{background:#16272b!important;color:#e6f1ed!important;border-color:#27413d!important}}
main{max-width:560px;margin:0 auto}h1{font-size:40px;margin:8px 0}h1 span{color:#128c4a}p{color:#506560}
.card{background:#fff;border:1px solid #c9d8d1;border-radius:14px;padding:14px;margin:12px 0}
.btn{display:block;width:100%;box-sizing:border-box;margin:10px 0;background:#128c4a;color:#fff;border:0;border-radius:999px;padding:14px 20px;font:600 17px system-ui;text-align:center;text-decoration:none;cursor:pointer}
.btn.alt{background:transparent;color:#128c4a;border:2px solid #128c4a}
label{display:block;margin-top:10px;font-weight:600}input,textarea{width:100%;box-sizing:border-box;border:1px solid #c9d8d1;border-radius:10px;padding:10px;font:16px system-ui}
.msg{min-height:1.4em}.erro{color:#b3261e}.ok{color:#128c4a;font-weight:600}pre{white-space:pre-wrap;font:14px/1.45 system-ui;margin:0}
.item{display:block;text-decoration:none;color:inherit}.item b{font-size:18px}
.h{position:absolute;left:-9999px}
</style>"""

INICIO = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MacTech</title>""" + BASE_CSS + """</head><body><main>
<h1>Mac<span>Tech</span></h1>
<p>Assistentes de atendimento com IA para empresas.</p>
<a class="btn" href="/clientes">Sou cliente: quero fazer perguntas</a>
<a class="btn alt" href="/empresas">Sou uma empresa: quero registar-me</a>
<a class="btn alt" href="/painel">Dono</a>
</main></body></html>"""

CLIENTES = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MacTech · Empresas</title>""" + BASE_CSS + """</head><body><main>
<p><a href="/">&larr; Início</a></p>
<h1>Escolha a empresa</h1>
<p>Toque na empresa com quem quer falar.</p>
<input id="q" placeholder="Procurar empresa" aria-label="Procurar empresa">
<div id="lista"></div><p id="vazio" class="msg"></p>
<script>
var todas = [];
function mostrar() {
  var q = document.getElementById('q').value.toLowerCase(), L = document.getElementById('lista');
  L.textContent = '';
  var f = todas.filter(function (e) { return e.nome.toLowerCase().indexOf(q) >= 0; });
  f.forEach(function (e) {
    var a = document.createElement('a'); a.className = 'card item'; a.href = '/c/' + encodeURIComponent(e.slug);
    var b = document.createElement('b'); b.textContent = e.nome; a.appendChild(b); L.appendChild(a);
  });
  document.getElementById('vazio').textContent = f.length ? '' : (todas.length ? 'Nenhuma empresa encontrada.' : 'Ainda não há empresas disponíveis.');
}
fetch('/api/publico/empresas').then(function (r) { return r.json(); }).then(function (j) { todas = j.empresas || []; mostrar(); })
  .catch(function () { document.getElementById('vazio').textContent = 'Não foi possível carregar a lista. Tente de novo.'; });
document.getElementById('q').oninput = mostrar;
</script></main></body></html>"""

EMPRESAS = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MacTech · Registar empresa</title>""" + BASE_CSS + """</head><body><main>
<p><a href="/">&larr; Início</a></p>
<h1>Registar empresa</h1>
<div class="card"><b>1. Termos</b><details><summary>Ler os termos</summary><pre>{{ termos }}</pre></details></div>
<div class="card"><b>2. Pagamento inicial</b><pre>{{ pagamento }}</pre></div>
<form id="f" class="card"><b>3. Dados da empresa</b>
<label for="n">Nome da empresa</label><input id="n" maxlength="120" required>
<label for="s">Sector (ex.: loja de tecnologia, clínica)</label><input id="s" maxlength="120">
<label for="d">O que a empresa faz</label><textarea id="d" rows="2" maxlength="1000"></textarea>
<label for="p">Produtos ou serviços (um por linha, com preços e detalhes)</label><textarea id="p" rows="5" maxlength="8000" required></textarea>
<label for="h">Horário</label><input id="h" maxlength="200">
<label for="l">Contactos e localização</label><input id="l" maxlength="300">
<label for="g">Garantia, entrega e pagamento</label><textarea id="g" rows="2" maxlength="1000"></textarea>
<label for="c">O seu telefone ou email (só a MacTech vê)</label><input id="c" maxlength="120" required>
<label for="r">Referência ou comprovativo do pagamento (número da transferência)</label><input id="r" maxlength="120" required>
<input class="h" id="w" tabindex="-1" autocomplete="off" aria-hidden="true">
<label><input type="checkbox" id="t" style="width:auto"> Li e aceito os termos</label>
<button class="btn" type="submit">Enviar pedido</button>
<p id="m" class="msg"></p></form>
<script>
function v(i) { return document.getElementById(i).value.trim(); }
document.getElementById('f').onsubmit = function (ev) {
  ev.preventDefault();
  var m = document.getElementById('m'); m.className = 'msg'; m.textContent = 'A enviar...';
  fetch('/api/publico/registar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
    nome: v('n'), sector: v('s'), descricao: v('d'), produtos: v('p'), horario: v('h'), local: v('l'), politicas: v('g'),
    contacto: v('c'), ref_pagamento: v('r'), aceita_termos: document.getElementById('t').checked, website: v('w') }) })
    .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
    .then(function (x) {
      if (x.ok) { m.className = 'msg ok'; m.textContent = 'Pedido enviado. Assim que o pagamento for confirmado, a sua empresa fica disponível aos clientes.'; document.getElementById('f').reset(); }
      else { m.className = 'msg erro'; m.textContent = x.j.erro || 'Não foi possível enviar.'; }
    }).catch(function () { m.className = 'msg erro'; m.textContent = 'Sem ligação. Tente de novo.'; });
};
</script></main></body></html>"""


def _prompt(d, f):
    """Mesmo formato do formulário do painel."""
    linhas = [l.strip() for l in f["produtos"].split("\n") if l.strip()]
    return (f["nome"] + (f" ({f['sector']})" if f["sector"] else "") + ". " + f["descricao"] + "\nProdutos e serviços:\n"
            + "\n".join("- " + l for l in linhas)
            + (f"\nHorário: {f['horario']}" if f["horario"] else "")
            + (f"\nContactos e localização: {f['local']}" if f["local"] else "")
            + (f"\nGarantia, entrega e pagamento: {f['politicas']}" if f["politicas"] else ""))


def registar(app, exige_admin, limite_excedido, empresa_ativa, gerar_slug):
    @app.get("/clientes")
    def pagina_clientes():
        return CLIENTES

    @app.get("/empresas")
    def pagina_empresas():
        pagamento = os.environ.get("PAGAMENTO_INSTRUCOES", "").strip() or (
            "Os dados de pagamento serão indicados pela MacTech. Contacte-nos para os receber.")
        return render_template_string(EMPRESAS, termos=TERMOS, pagamento=pagamento)

    @app.get("/api/publico/empresas")
    def listar_publico():
        """Só empresas aprovadas (pagas ou em teste dentro do prazo). Nunca mostra pendentes nem suspensas."""
        with SessionLocal() as db:
            ativas = [e for e in db.query(Empresa).filter(Empresa.slug.isnot(None)).order_by(Empresa.nome).all()
                      if empresa_ativa(e)]
            return jsonify(empresas=[{"nome": e.nome, "slug": e.slug} for e in ativas])

    @app.post("/api/publico/registar")
    def registar_empresa():
        d = request.get_json(silent=True) or {}
        if str(d.get("website") or "").strip():       # campo-armadilha: só os robôs o preenchem
            return jsonify(ok=True), 201
        if limite_excedido(("registo", request.remote_addr), 10, 3600):
            return jsonify(erro="Demasiados pedidos. Tente daqui a uma hora."), 429

        def t(campo, maximo):
            return str(d.get(campo) or "").strip()[:maximo]
        f = {"nome": t("nome", 120), "sector": t("sector", 120), "descricao": t("descricao", 1000),
             "produtos": t("produtos", 8000), "horario": t("horario", 200), "local": t("local", 300),
             "politicas": t("politicas", 1000)}
        contacto, ref = t("contacto", 120), t("ref_pagamento", 120)
        em_falta = [n for n, v in (("nome da empresa", f["nome"]), ("produtos ou serviços", f["produtos"]),
                                   ("telefone ou email", contacto), ("referência do pagamento", ref)) if not v]
        if em_falta:
            return jsonify(erro="Preencha: " + ", ".join(em_falta) + "."), 400
        if d.get("aceita_termos") is not True:
            return jsonify(erro="Tem de aceitar os termos."), 400
        empresa = Empresa(nome=f["nome"], system_prompt=_prompt(d, f), humano_ativo=True, no_hub=True,
                          estado="pendente", teste_ate=None)
        with SessionLocal() as db:
            empresa.slug = gerar_slug(db, f["nome"])
            db.add(empresa)
            try:
                db.flush()
                db.add(PedidoEmpresa(empresa_id=empresa.id, contacto=contacto, ref_pagamento=ref))
                db.commit()
            except IntegrityError:
                db.rollback()
                log.exception("Não foi possível registar a empresa")
                return jsonify(erro="Não foi possível registar. Tente de novo."), 409
        log.warning("[ATENÇÃO] Novo pedido de empresa: %s (confirmar pagamento no painel)", f["nome"])
        return jsonify(ok=True), 201

    @app.get("/api/pedidos")
    @exige_admin
    def listar_pedidos():
        """Contacto e referência de pagamento por empresa (só o dono)."""
        with SessionLocal() as db:
            return jsonify(pedidos={p.empresa_id: {"contacto": p.contacto, "ref_pagamento": p.ref_pagamento}
                                    for p in db.query(PedidoEmpresa).all()})
