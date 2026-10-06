"""Ficheiros do site (CSS, JavaScript e HTML) dentro do próprio código.

Assim o site não depende de nenhuma pasta no GitHub: basta o app.py e este ficheiro."""

ASSETS = {
    "chat.css": (
        "text/css; charset=utf-8",
        r''':root{--bg:#e9f0ec;--card:#fff;--ink:#10201e;--mut:#506560;--out:#d4f4c6;--hum:#ffe9b8;--acc:#128c4a;--accT:#fff;--line:#c9d8d1}
@media(prefers-color-scheme:dark){:root{--bg:#0d1917;--card:#16272b;--ink:#e6f1ed;--mut:#93aaa3;--out:#1d5a3a;--hum:#6b5316;--acc:#2fcf7a;--accT:#06251a;--line:#27413d}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top)}
header{background:var(--acc);color:var(--accT);padding:12px 16px;display:flex;gap:10px;align-items:center}
header small{display:block;opacity:.85;font-size:12px}
.dot{width:36px;height:36px;border-radius:50%;background:var(--accT);color:var(--acc);display:grid;place-items:center;font-weight:800}
#log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.m{max-width:86%;padding:8px 12px;border-radius:14px;white-space:pre-wrap}
.m.assistant{background:var(--card);align-self:flex-start;border-top-left-radius:4px}
.m.me{background:var(--out);align-self:flex-end;border-top-right-radius:4px}
.m.human{background:var(--hum);align-self:flex-start;border-top-left-radius:4px}
.m small{display:block;color:var(--mut);font-size:11px}
form{display:flex;gap:8px;padding:10px 12px;background:var(--card);border-top:1px solid var(--line)}
input{flex:1;min-width:0;border:1px solid var(--line);border-radius:999px;padding:10px 14px;font:16px system-ui;background:var(--bg);color:var(--ink)}
button{background:var(--acc);color:var(--accT);border:0;border-radius:999px;padding:10px 18px;font:600 15px system-ui;cursor:pointer}
button:focus-visible,input:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
footer{text-align:center;font-size:12px;color:var(--mut);padding:4px 0 calc(6px + env(safe-area-inset-bottom));background:var(--card)}
.sug{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start;max-width:92%}
.chip{background:transparent;color:var(--ink);border:1px solid var(--acc);border-radius:999px;padding:6px 12px;font:600 13px system-ui,sans-serif;cursor:pointer}
.chip:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
''',
    ),
    "chat.js": (
        "application/javascript; charset=utf-8",
        r'''var C = JSON.parse(document.getElementById('cfg').textContent), log = document.getElementById('log'), inp = document.getElementById('t');
var vistas = 0, hum = false, ocupado = false, timer = null, base = '/chat/' + C.slug, sug = null;

function novoId() {
  try {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16); crypto.getRandomValues(b);
    return Array.prototype.map.call(b, function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  } catch (e) { return (String(Math.random()).slice(2) + String(Date.now()) + '0000000000000000').replace(/[^0-9]/g, '').slice(0, 32); }
}
function sid() {
  try {
    var k = 'mt_' + C.slug, s = localStorage.getItem(k);
    if (!s) {
      s = novoId();
      localStorage.setItem(k, s);
    }
    return s;
  } catch (e) { return window.__s || (window.__s = String(Math.random()).slice(2) + String(Date.now())); }
}
var S = sid();

function add(txt, cls) {
  var d = document.createElement('div'); d.className = 'm ' + cls;
  if (cls === 'human') { var s = document.createElement('small'); s.textContent = 'equipa'; d.appendChild(s); }
  d.appendChild(document.createTextNode(txt)); log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
}
function mostrar(ms) {
  ms.forEach(function (m) {
    if (m.id > vistas) vistas = m.id;
    add(m.conteudo, m.remetente === 'user' ? 'me' : m.remetente === 'human' ? 'human' : 'assistant');
  });
}
function parar() { if (timer) { clearInterval(timer); timer = null; } }
function poll() {
  fetch(base + '/mensagens?sessao=' + S + '&desde=' + vistas).then(function (r) { return r.json(); })
    .then(function (j) { mostrar(j.mensagens || []); hum = !!j.humano; if (!hum) parar(); }).catch(function () {});
}
function iniciar() { if (!timer) timer = setInterval(poll, 4000); }

// Perguntas sugeridas para o cliente começar a conversa
function sugestoes() {
  sug = document.createElement('div'); sug.className = 'sug';
  ['Que produtos ou serviços têm?', 'Qual é o horário?', 'Quero falar com uma pessoa'].forEach(function (t) {
    var b = document.createElement('button'); b.type = 'button'; b.className = 'chip'; b.textContent = t;
    b.onclick = function () { enviar(t); }; sug.appendChild(b);
  });
  log.appendChild(sug);
}
function saudacao() { add('Olá! Sou o assistente da ' + C.nome + '. Como posso ajudar?', 'assistant'); sugestoes(); }

function falha(w, msg) { if (w) w.remove(); add(msg, 'assistant'); }

// Resposta normal (sem tempo real): usada se o navegador não suportar streaming ou se este falhar
function enviarNormal(t, w) {
  return fetch(base + '/mensagem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessao: S, texto: t }) })
    .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
    .then(function (x) {
      if (w) w.remove();
      if (!x.ok) add(x.j.erro || 'Não foi possível enviar. Tenta de novo.', 'assistant');
      else { mostrar(x.j.mensagens || []); hum = !!x.j.humano; if (hum) iniciar(); }
    });
}

function enviar(t) {
  t = t.trim(); if (!t || ocupado) return;
  if (sug) { sug.remove(); sug = null; }
  add(t, 'me'); ocupado = true; inp.focus();
  var w = hum ? null : add('…', 'assistant');
  var fim = function () { ocupado = false; };
  if (!(window.fetch && window.ReadableStream && window.TextDecoder)) {
    return enviarNormal(t, w).catch(function () { falha(w, 'Sem ligação. Tenta de novo.'); }).then(fim);
  }
  fetch(base + '/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessao: S, texto: t }) })
    .then(function (r) {
      var tipo = r.headers.get('content-type') || '';
      if (tipo.indexOf('text/event-stream') < 0) {   // resposta fixa, erro ou pessoa assumiu: vem em JSON
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (w) w.remove();
          if (!r.ok) add(j.erro || 'Não foi possível enviar. Tenta de novo.', 'assistant');
          else { mostrar(j.mensagens || []); hum = !!j.humano; if (hum) iniciar(); }
        });
      }
      var rd = r.body.getReader(), dec = new TextDecoder(), buf = '', bolha = w, texto = '';
      function linha(l) {
        if (l.indexOf('data:') !== 0) return;
        var ev; try { ev = JSON.parse(l.slice(5)); } catch (e) { return; }
        if (ev.t) { texto += ev.t; if (bolha) bolha.textContent = texto; log.scrollTop = log.scrollHeight; }
        if (ev.substituir && bolha) { texto = ev.substituir; bolha.textContent = texto; }
        if (ev.fim && ev.id > vistas) vistas = ev.id;
      }
      function ler() {
        return rd.read().then(function (x) {
          if (x.done) { if (buf) linha(buf.trim()); if (!texto && bolha) { bolha.remove(); add('Não consegui responder. Tenta de novo.', 'assistant'); } return; }
          buf += dec.decode(x.value, { stream: true });
          var partes = buf.split('\n\n'); buf = partes.pop();
          partes.forEach(function (p) { linha(p.trim()); });
          return ler();
        });
      }
      return ler();
    })
    .catch(function () { falha(w, 'Sem ligação. Tenta de novo.'); })
    .then(fim);
}

fetch(base + '/mensagens?sessao=' + S + '&desde=0&tudo=1').then(function (r) { return r.json(); }).then(function (j) {
  var ms = j.mensagens || [];
  if (ms.length) { mostrar(ms); hum = !!j.humano; if (hum) iniciar(); } else saudacao();
}).catch(saudacao);

document.getElementById('f').onsubmit = function (e) { e.preventDefault(); var t = inp.value; inp.value = ''; enviar(t); };
''',
    ),
    "painel.css": (
        "text/css; charset=utf-8",
        r''':root{--bg:#e9f0ec;--card:#fff;--ink:#10201e;--mut:#506560;--acc:#128c4a;--accT:#fff;--line:#c9d8d1;--off:#ffd9d4}
@media(prefers-color-scheme:dark){:root{--bg:#0d1917;--card:#16272b;--ink:#e6f1ed;--mut:#93aaa3;--acc:#2fcf7a;--accT:#06251a;--line:#27413d;--off:#5a2a25}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,sans-serif}
header{padding:14px 16px;font-size:20px;display:flex;gap:10px;align-items:center}
header span{color:var(--acc)}header button{margin-left:auto}
main{max-width:720px;margin:0 auto;padding:0 14px 40px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;margin-bottom:14px}
h2{margin:0 0 8px;font-size:19px}
label{display:block;font-size:13px;color:var(--mut);margin:10px 0 3px}
.chk{display:flex;gap:8px;align-items:center;color:var(--ink);font-size:15px}
input,textarea{width:100%;border:1px solid var(--line);border-radius:10px;padding:9px 11px;font:16px system-ui,sans-serif;background:var(--bg);color:var(--ink)}
input[type=checkbox]{width:auto}
.row{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}.row input{flex:1;min-width:0}
.btn{background:var(--acc);color:var(--accT);border:0;border-radius:999px;padding:9px 16px;font:600 14px system-ui,sans-serif;cursor:pointer}
.btn.alt{background:transparent;color:var(--ink);border:1px solid var(--line)}
.btn:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
.msg{color:var(--mut);font-size:14px;margin:6px 0;word-break:break-word}
.item{border-top:1px solid var(--line);padding:10px 0}
.badge{display:inline-block;border-radius:999px;padding:1px 10px;font-size:12px;font-weight:600;background:var(--acc);color:var(--accT)}
.badge.off{background:var(--off);color:var(--ink)}
a{color:var(--acc)}
''',
    ),
    "painel.html": (
        "text/html; charset=utf-8",
        r'''<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacTech · Painel</title>
<link rel="stylesheet" href="/static/painel.css">
</head><body>
<header><b>Mac<span>Tech</span></b> · Painel <button id="sair" class="btn alt" type="button" hidden>Sair</button></header>
<main>
<section id="entrar" class="card">
<h2>Entrar</h2>
<p class="msg">Escreve a chave de administração (a tua ADMIN_API_KEY).</p>
<form id="fl" class="row"><input id="k" type="password" autocomplete="current-password" aria-label="Chave de administração" required><button class="btn" type="submit">Entrar</button></form>
<p id="ml" class="msg"></p>
</section>
<div id="painel" hidden>
<section class="card">
<h2>Registar empresa</h2>
<form id="fe">
<div class="row"><button class="btn alt" id="ex" type="button">Preencher com um exemplo</button></div>
<label for="en">Nome da empresa</label><input id="en" required>
<label for="es">Sector (ex.: loja de tecnologia, clínica)</label><input id="es">
<label for="ed">O que a empresa faz</label><textarea id="ed" rows="2"></textarea>
<label for="epd">Produtos ou serviços (um por linha, com detalhes)</label><textarea id="epd" rows="4" required></textarea>
<label for="eho">Horário</label><input id="eho">
<label for="elo">Contactos e localização</label><input id="elo">
<label for="epo">Garantia, entrega e pagamento</label><textarea id="epo" rows="2"></textarea>
<label for="eex">Regras extra para o bot</label><textarea id="eex" rows="2"></textarea>
<label class="chk"><input type="checkbox" id="eh" checked> A empresa tem equipa para atender pessoas</label>
<div class="row"><button class="btn" type="submit">Registar empresa</button></div>
<p id="me" class="msg"></p>
</form>
</section>
<section class="card"><h2>Estado do sistema</h2>
<div class="row"><button class="btn" id="dg" type="button">Testar sistema</button></div><div id="dgr"></div></section>
<section class="card"><h2>Nível 4: departamentos, atendentes e ligações</h2>
<label for="n4e">Empresa</label><select id="n4e"></select>
<label for="n4d">Novo departamento (ex.: Vendas, Suporte, Financeiro)</label>
<div class="row"><input id="n4d"><button class="btn" id="n4db" type="button">Adicionar</button></div>
<label for="n4an">Novo atendente (nome) e departamento (opcional)</label>
<div class="row"><input id="n4an" placeholder="Nome"><input id="n4ad" placeholder="Departamento"><button class="btn" id="n4ab" type="button">Criar</button></div>
<label>Ferramentas da IA</label>
<div class="row"><label class="chk"><input type="checkbox" class="n4f" value="stock"> Stock</label>
<label class="chk"><input type="checkbox" class="n4f" value="encomendas"> Encomendas</label>
<label class="chk"><input type="checkbox" class="n4f" value="fatura"> Pedir fatura</label>
<label class="chk"><input type="checkbox" class="n4f" value="departamentos" checked> Departamentos</label></div>
<label for="n4u">Endereço do CRM/ERP da empresa (https, opcional)</label><input id="n4u" placeholder="https://erp.empresa.ao/mactech">
<label for="n4s">Segredo para assinar os pedidos (só se usares o endereço)</label><input id="n4s" type="password" autocomplete="off">
<div class="row"><button class="btn" id="n4ib" type="button">Guardar ferramentas</button></div>
<label for="n4p">Produtos (uma linha cada: referência;nome;preço;stock)</label><textarea id="n4p" rows="3"></textarea>
<div class="row"><button class="btn alt" id="n4pb" type="button">Importar produtos</button></div>
<label for="n4o">Encomendas (uma linha cada: código;telefone ou email;estado;itens;total)</label><textarea id="n4o" rows="3"></textarea>
<div class="row"><button class="btn alt" id="n4ob" type="button">Importar encomendas</button></div>
<p id="n4m" class="msg"></p></section>
<section class="card"><h2>Tickets abertos</h2><div id="tkadm"></div></section>
<section class="card"><h2>Empresas</h2><div id="lista"></div></section>
<section class="card"><h2>Conversas à espera de uma pessoa</h2><div id="humanos"></div></section>
<section class="card"><h2>Conversas recentes</h2><div id="conversas"></div><div id="transc"></div></section>
<section class="card"><h2>Perguntas que o bot não soube responder</h2>
<p class="msg">Acrescenta estas respostas ao catálogo da empresa para o bot melhorar.</p><div id="semresp"></div></section>
<section class="card"><h2>Exportar</h2>
<div class="row"><button class="btn alt" id="csv" type="button">Descarregar contactos e conversas (CSV)</button></div></section>
</div>
</main>
<script src="/static/painel.js"></script>
</body></html>
''',
    ),
    "painel.js": (
        "application/javascript; charset=utf-8",
        r'''(function () {
  var K = sessionStorage.getItem('mt_admin') || '', tm = null;
  function $(i) { return document.getElementById(i); }
  function h(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function erro(x) { alert(x.message); }

  // Pedido à API com a chave de administração
  function api(m, u, b) {
    return fetch(u, { method: m, headers: { 'X-API-Key': K, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 401) { sair(); throw new Error('Chave errada'); }
          if (!r.ok) throw new Error(j.erro || ('Erro ' + r.status));
          return j;
        });
      });
  }
  function mostrar(logado) { $('entrar').hidden = logado; $('painel').hidden = !logado; $('sair').hidden = !logado; }
  function sair() { sessionStorage.removeItem('mt_admin'); K = ''; clearInterval(tm); mostrar(false); }
  // ---- Nível 4 ----
  function n4id() { return $('n4e').value; }
  function n4msg(x) { $('n4m').textContent = x; }
  function preencherN4(emps) {
    var s = $('n4e'), at = s.value; s.textContent = '';
    emps.forEach(function (e) { var o = h('option', null, e.nome); o.value = e.id; s.appendChild(o); });
    if (at) s.value = at;
  }
  function linhas(id) { return $(id).value.split('\n').map(function (l) { return l.trim(); }).filter(Boolean).map(function (l) { return l.split(';').map(function (x) { return x.trim(); }); }); }
  function n4pedir(m, u, b, ok) { if (!n4id()) { n4msg('Escolhe uma empresa.'); return; } api(m, u, b).then(function (j) { n4msg(ok(j)); }).catch(function (x) { n4msg(x.message); }); }
  $('n4db').onclick = function () { n4pedir('POST', '/api/empresas/' + n4id() + '/departamentos', { nome: $('n4d').value }, function (j) { $('n4d').value = ''; return 'Departamentos: ' + j.departamentos.map(function (d) { return d.nome; }).join(', '); }); };
  $('n4ab').onclick = function () { n4pedir('POST', '/api/empresas/' + n4id() + '/agentes', { nome: $('n4an').value, departamento: $('n4ad').value }, function (j) { $('n4an').value = ''; $('n4ad').value = ''; return 'Atendente criado. CHAVE (copia agora, não volta a aparecer): ' + j.chave; }); };
  $('n4ib').onclick = function () {
    var f = Array.prototype.filter.call(document.querySelectorAll('.n4f'), function (c) { return c.checked; }).map(function (c) { return c.value; });
    var b = { ferramentas: f }; if ($('n4u').value.trim()) b.url = $('n4u').value.trim(); if ($('n4s').value) b.segredo = $('n4s').value;
    n4pedir('POST', '/api/empresas/' + n4id() + '/integracao', b, function (j) { $('n4s').value = ''; return 'Ferramentas ativas: ' + (j.ferramentas.join(', ') || 'nenhuma') + (j.url ? ' · ligado a ' + j.url : ''); });
  };
  $('n4pb').onclick = function () {
    var p = linhas('n4p').map(function (c) { return { sku: c[0], nome: c[1], preco: c[2], stock: c[3] }; });
    n4pedir('POST', '/api/empresas/' + n4id() + '/produtos', { produtos: p }, function (j) { return j.importados + ' produtos importados.'; });
  };
  $('n4ob').onclick = function () {
    var o = linhas('n4o').map(function (c) { return { codigo: c[0], contacto: c[1], estado: c[2], itens: c[3], total: c[4] }; });
    n4pedir('POST', '/api/empresas/' + n4id() + '/encomendas', { encomendas: o }, function (j) { return j.importadas + ' encomendas importadas.'; });
  };
  function carregarTickets() {
    api('GET', '/api/tickets').then(function (j) {
      var L = $('tkadm'); L.textContent = '';
      if (!j.tickets.length) { L.appendChild(h('p', 'msg', 'Nenhum ticket aberto.')); return; }
      j.tickets.forEach(function (t) {
        var d = h('div', 'item'); d.appendChild(h('b', null, (t.departamento || 'Geral') + ' · ' + t.tipo)); d.appendChild(h('p', 'msg', t.assunto));
        var b = h('button', 'btn alt', 'Fechar'); b.type = 'button';
        b.onclick = function () { api('POST', '/api/tickets/' + t.id + '/fechar').then(carregarTickets).catch(erro); };
        d.appendChild(b); L.appendChild(d);
      });
    }).catch(function () {});
  }

  function iniciar() { mostrar(true); carregarTickets(); carregarEmpresas(); carregarHumanos(); carregarConversas(); carregarSemResposta(); clearInterval(tm); tm = setInterval(function () { carregarHumanos(); carregarTickets(); }, 15000); }

  $('fl').onsubmit = function (e) {
    e.preventDefault(); K = $('k').value.trim();
    api('GET', '/api/empresas').then(function () {
      sessionStorage.setItem('mt_admin', K); $('k').value = ''; $('ml').textContent = ''; iniciar();
    }).catch(function (x) { $('ml').textContent = x.message; });
  };
  $('sair').onclick = sair;

  function carregarEmpresas() {
    Promise.all([api('GET', '/api/empresas'), api('GET', '/api/estatisticas?dias=7'), api('GET', '/api/pedidos')]).then(function (r) {
      preencherN4(r[0].empresas); var st = {}; r[1].empresas.forEach(function (s) { st[s.empresa] = s; });
      var L = $('lista'); L.textContent = '';
      if (!r[0].empresas.length) { L.appendChild(h('p', 'msg', 'Ainda não há empresas. Regista a primeira acima.')); return; }
      r[0].empresas.forEach(function (e) {
        var c = h('div', 'item');
        c.appendChild(h('b', null, e.nome + ' '));
        var fim = e.estado === 'teste' && e.teste_ate ? ' até ' + new Date(e.teste_ate).toLocaleString('pt-PT') : '';
        c.appendChild(h('span', 'badge' + (e.ativa ? '' : ' off'), e.estado + fim));
        var ped = r[2].pedidos[e.id];
        if (ped) c.appendChild(h('p', 'msg', 'Contacto: ' + ped.contacto + ' · Ref. pagamento: ' + ped.ref_pagamento));
        var s = st[e.nome];
        if (s) c.appendChild(h('p', 'msg', 'Últimos 7 dias: ' + s.pessoas + ' pessoas · ' + s.mensagens_clientes + ' mensagens · ' + s.contactos_recolhidos + ' contactos · ' + s.perguntas_sem_resposta + ' sem resposta'));
        var b = h('div', 'row');
        if (e.chat_url) {
          var url = location.origin + e.chat_url, p = h('p', 'msg'), a = h('a', null, url);
          a.href = url; a.target = '_blank'; a.rel = 'noopener'; p.appendChild(a); c.appendChild(p);
          var cp = h('button', 'btn', 'Abrir chat'); cp.type = 'button';
          cp.onclick = function () { window.open(url, '_blank'); }; b.appendChild(cp);
          var cc = h('button', 'btn alt', 'Copiar link'); cc.type = 'button';
          cc.onclick = function () { try { navigator.clipboard.writeText(url); cc.textContent = 'Copiado'; } catch (x) { prompt('Copia o link:', url); } };
          b.appendChild(cc);
        }
        [['Ativar (pagou)', 'ativo'], ['Suspender', 'suspenso'], ['+1 dia de teste', 'teste']].forEach(function (x) {
          var bt = h('button', 'btn alt', x[0]); bt.type = 'button';
          bt.onclick = function () { api('POST', '/api/empresas/' + e.id + '/estado', { estado: x[1], dias: 1 }).then(carregarEmpresas).catch(erro); };
          b.appendChild(bt);
        });
        c.appendChild(b); L.appendChild(c);
      });
    }).catch(function (x) { $('lista').textContent = x.message; });
  }

  function carregarHumanos() {
    api('GET', '/api/conversas-humano').then(function (j) {
      var L = $('humanos');
      if (L.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') return; // não interromper quem está a escrever
      L.textContent = '';
      if (!j.conversas.length) { L.appendChild(h('p', 'msg', 'Nenhuma conversa à espera.')); return; }
      j.conversas.forEach(function (c) {
        var d = h('div', 'item'), num = c.cliente_numero.length > 14 ? c.cliente_numero.slice(0, 8) + '…' : c.cliente_numero;
        d.appendChild(h('b', null, (c.empresa || '?') + ' · ' + num + ' · ' + (c.phone_number_id === 'web' ? 'chat web' : 'WhatsApp')));
        d.appendChild(h('p', 'msg', 'Última mensagem (' + c.ultimo_remetente + '): ' + (c.ultima_mensagem || '')));
        var f = h('form', 'row'), i = h('input'), s = h('button', 'btn', 'Enviar');
        i.placeholder = 'Resposta para o cliente'; i.setAttribute('aria-label', 'Resposta'); s.type = 'submit';
        f.appendChild(i); f.appendChild(s);
        f.onsubmit = function (ev) {
          ev.preventDefault(); var t = i.value.trim(); if (!t) return;
          api('POST', '/api/responder-humano', { phone_number_id: c.phone_number_id, cliente_numero: c.cliente_numero, texto: t })
            .then(function () { i.value = ''; alert('Enviado.'); }).catch(erro);
        };
        var dv = h('button', 'btn alt', 'Devolver à IA'); dv.type = 'button';
        dv.onclick = function () { api('POST', '/api/devolver-ia', { phone_number_id: c.phone_number_id, cliente_numero: c.cliente_numero }).then(carregarHumanos).catch(erro); };
        d.appendChild(f); d.appendChild(dv); L.appendChild(d);
      });
    }).catch(function () {});
  }

  // Formulário: monta o texto que a IA vai usar e regista a empresa
  function v(i) { return $(i).value.trim(); }
  $('ex').onclick = function () {
    $('en').value = 'Loja Demo'; $('es').value = 'loja de tecnologia';
    $('ed').value = 'Vende telemóveis, portáteis e acessórios.';
    $('epd').value = 'Portátil Pro 14: 16 GB de RAM, SSD de 512 GB, bateria até 12 h\nTelemóvel Lite 5G: 128 GB, câmara de 50 MP, dual SIM\nAuscultadores Air: Bluetooth, cancelamento de ruído, 30 h de autonomia';
    $('eho').value = 'Segunda a sábado, 8h às 18h'; $('elo').value = 'Luanda';
    $('epo').value = 'Garantia de 1 ano nos equipamentos.'; $('eex').value = '';
  };
  $('fe').onsubmit = function (ev) {
    ev.preventDefault();
    var pr = v('en') + (v('es') ? ' (' + v('es') + ')' : '') + '. ' + v('ed') + '\nProdutos e serviços:\n' +
      v('epd').split('\n').filter(Boolean).map(function (l) { return '- ' + l; }).join('\n') +
      (v('eho') ? '\nHorário: ' + v('eho') : '') + (v('elo') ? '\nContactos e localização: ' + v('elo') : '') +
      (v('epo') ? '\nGarantia, entrega e pagamento: ' + v('epo') : '') + (v('eex') ? '\nRegras extra: ' + v('eex') : '');
    api('POST', '/api/empresas', { nome: v('en'), system_prompt: pr, humano_ativo: $('eh').checked }).then(function (j) {
      $('me').textContent = 'Empresa registada. Chat: ' + location.origin + j.chat_url + ' (tem 1 dia de teste).';
      $('fe').reset(); $('eh').checked = true; carregarEmpresas();
    }).catch(function (x) { $('me').textContent = x.message; });
  };

  // Testar o sistema (base de dados, chave e crédito da IA, modelo)
  $('dg').onclick = function () {
    var R = $('dgr'); R.textContent = 'A testar…';
    api('POST', '/api/diagnostico').then(function (j) {
      R.textContent = '';
      [['Base de dados', j.base_de_dados ? 'OK' : 'PROBLEMA'],
       ['IA (' + j.modelo + ')', (j.ia.ok ? 'OK. ' : 'PROBLEMA: ') + j.ia.mensagem],
       ['WhatsApp', j.whatsapp_configurado ? 'configurado' : 'não configurado (normal se só usas o chat web)']
      ].forEach(function (l) { R.appendChild(h('p', 'msg', l[0] + ': ' + l[1])); });
    }).catch(function (x) { R.textContent = x.message; });
  };

  // Conversas recentes e leitura de uma conversa
  function carregarConversas() {
    api('GET', '/api/conversas?limite=20').then(function (j) {
      var L = $('conversas'); L.textContent = '';
      if (!j.conversas.length) { L.appendChild(h('p', 'msg', 'Ainda não há conversas.')); return; }
      j.conversas.forEach(function (c) {
        var d = h('div', 'item');
        d.appendChild(h('b', null, (c.empresa || '?') + ' · ' + c.canal + ' · ' + c.mensagens + ' mensagens' + (c.humano_assumiu ? ' · à espera de pessoa' : '')));
        if (c.contacto) d.appendChild(h('p', 'msg', 'Contacto: ' + c.contacto));
        d.appendChild(h('p', 'msg', c.ultima_mensagem || ''));
        var b = h('button', 'btn alt', 'Ver conversa'); b.type = 'button'; b.onclick = function () { verConversa(c.id); };
        d.appendChild(b); L.appendChild(d);
      });
    }).catch(function () {});
  }
  function verConversa(id) {
    api('GET', '/api/conversas/' + id).then(function (j) {
      var T = $('transc'); T.textContent = ''; T.appendChild(h('h2', null, 'Conversa'));
      j.mensagens.forEach(function (m) {
        var quem = m.remetente === 'user' ? 'Cliente' : m.remetente === 'human' ? 'Equipa' : 'Bot';
        T.appendChild(h('p', 'msg', quem + ': ' + m.conteudo + (m.sem_resposta ? '  (o bot não soube responder)' : '')));
      });
      T.scrollIntoView();
    }).catch(erro);
  }
  function carregarSemResposta() {
    api('GET', '/api/sem-resposta?dias=30').then(function (j) {
      var L = $('semresp'); L.textContent = '';
      if (!j.perguntas.length) { L.appendChild(h('p', 'msg', 'Nenhuma pergunta sem resposta. Bom sinal.')); return; }
      j.perguntas.forEach(function (p) { L.appendChild(h('p', 'msg', (p.empresa || '?') + ': ' + p.pergunta)); });
    }).catch(function () {});
  }
  $('csv').onclick = function () {
    fetch('/api/exportar.csv', { headers: { 'X-API-Key': K } })
      .then(function (r) { if (!r.ok) throw new Error('Erro ' + r.status); return r.blob(); })
      .then(function (b) {
        var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'mactech_conversas.csv';
        document.body.appendChild(a); a.click(); a.remove();
      }).catch(erro);
  };

  if (K) { api('GET', '/api/empresas').then(iniciar).catch(function () { mostrar(false); }); } else { mostrar(false); }
})();
''',
    ),
    "style.css": (
        "text/css; charset=utf-8",
        r'''body{margin:0;min-height:100vh;display:grid;place-items:center;background:#e9f0ec;color:#10201e;font:16px/1.5 system-ui,sans-serif;text-align:center;padding:20px}
@media(prefers-color-scheme:dark){body{background:#0d1917;color:#e6f1ed}}
h1{font-size:44px;margin:0 0 8px}h1 span{color:#128c4a}p{margin:6px 0;color:#506560}
.btn{display:inline-block;margin-top:10px;background:#128c4a;color:#fff;border-radius:999px;padding:10px 20px;font-weight:600;text-decoration:none}
''',
    ),
    "agente.html": (
        "text/html; charset=utf-8",
        r'''<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MacTech · Atendimento</title>
<link rel="stylesheet" href="/static/painel.css">
</head><body>
<header><b>Mac<span>Tech</span></b> · Atendimento <span id="quem" class="msg"></span> <button id="sair" class="btn alt" type="button" hidden>Sair</button></header>
<main>
<section id="entrar" class="card">
<h2>Entrar</h2>
<p class="msg">Escreve a tua chave de atendente (dada pelo administrador).</p>
<form id="fl" class="row"><input id="k" type="password" autocomplete="current-password" aria-label="Chave de atendente" required><button class="btn" type="submit">Entrar</button></form>
<p id="ml" class="msg"></p>
</section>
<div id="app" hidden>
<section class="card"><h2>Conversas à espera de uma pessoa</h2><div id="fila"></div></section>
<section class="card" id="cv" hidden><h2 id="cvt">Conversa</h2><div id="msgs"></div>
<form id="fr" class="row"><input id="tx" maxlength="2000" placeholder="Escreve a resposta" aria-label="Resposta"><button class="btn" type="submit">Enviar</button></form>
<div class="row"><button class="btn alt" id="dev" type="button">Devolver à IA</button></div></section>
<section class="card"><h2>Tickets abertos</h2><div id="tk"></div></section>
</div>
</main>
<script src="/static/agente.js"></script>
</body></html>
''',
    ),
    "agente.js": (
        "application/javascript; charset=utf-8",
        r'''(function () {
  var K = sessionStorage.getItem('mt_agente') || '', tm = null, atual = null;
  function $(i) { return document.getElementById(i); }
  function h(t, c, x) { var e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; }
  function api(m, u, b) {
    return fetch(u, { method: m, headers: { 'X-Agent-Key': K, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 401) { sair(); throw new Error('Chave errada'); }
          if (!r.ok) throw new Error(j.erro || ('Erro ' + r.status));
          return j;
        });
      });
  }
  function erro(x) { alert(x.message); }
  function mostrar(on) { $('entrar').hidden = on; $('app').hidden = !on; $('sair').hidden = !on; }
  function sair() { sessionStorage.removeItem('mt_agente'); K = ''; clearInterval(tm); atual = null; $('cv').hidden = true; mostrar(false); }
  function iniciar() {
    mostrar(true);
    api('GET', '/api/agente/eu').then(function (j) { $('quem').textContent = j.nome + ' · ' + j.empresa + ' · ' + j.departamento; });
    carregar(); clearInterval(tm); tm = setInterval(carregar, 8000);
  }
  function carregar() { fila(); tickets(); if (atual) conversa(atual, true); }

  function fila() {
    api('GET', '/api/agente/fila').then(function (j) {
      var L = $('fila'); L.textContent = '';
      if (!j.conversas.length) { L.appendChild(h('p', 'msg', 'Nenhuma conversa à espera.')); return; }
      j.conversas.forEach(function (c) {
        var d = h('div', 'item');
        d.appendChild(h('b', null, (c.departamento || 'Geral') + ' · ' + c.canal + ' · ' + c.cliente + (c.minha ? ' · tua' : '')));
        if (c.contacto) d.appendChild(h('p', 'msg', 'Contacto: ' + c.contacto));
        d.appendChild(h('p', 'msg', (c.ultimo_remetente === 'user' ? 'Cliente: ' : '') + (c.ultima_mensagem || '')));
        var b = h('button', 'btn', c.livre ? 'Assumir' : 'Abrir'); b.type = 'button';
        b.onclick = function () {
          if (!c.livre) { abrir(c.id); return; }
          api('POST', '/api/agente/assumir', { conversa_id: c.id }).then(function () { abrir(c.id); fila(); }).catch(erro);
        };
        d.appendChild(b); L.appendChild(d);
      });
    }).catch(function () {});
  }
  function abrir(id) { atual = id; $('cv').hidden = false; conversa(id, false); }
  function conversa(id, silencio) {
    api('GET', '/api/agente/conversa/' + id).then(function (j) {
      var T = $('msgs'); T.textContent = ''; $('cvt').textContent = 'Conversa' + (j.contacto ? ' · ' + j.contacto : '');
      j.mensagens.forEach(function (m) {
        var q = m.remetente === 'user' ? 'Cliente' : m.remetente === 'human' ? 'Equipa' : 'Bot';
        T.appendChild(h('p', 'msg', q + ': ' + m.conteudo));
      });
      $('fr').hidden = !j.minha;
      if (!silencio) $('cv').scrollIntoView();
    }).catch(function (x) { if (silencio) { atual = null; $('cv').hidden = true; } else erro(x); });
  }
  $('fr').onsubmit = function (e) {
    e.preventDefault(); var t = $('tx').value.trim(); if (!t || !atual) return;
    api('POST', '/api/agente/responder', { conversa_id: atual, texto: t }).then(function () { $('tx').value = ''; conversa(atual, true); }).catch(erro);
  };
  $('dev').onclick = function () {
    if (!atual) return;
    api('POST', '/api/agente/devolver', { conversa_id: atual }).then(function () { atual = null; $('cv').hidden = true; fila(); }).catch(erro);
  };
  function tickets() {
    api('GET', '/api/agente/tickets').then(function (j) {
      var L = $('tk'); L.textContent = '';
      if (!j.tickets.length) { L.appendChild(h('p', 'msg', 'Nenhum ticket aberto.')); return; }
      j.tickets.forEach(function (t) {
        var d = h('div', 'item');
        d.appendChild(h('b', null, (t.departamento || 'Geral') + ' · ' + t.tipo));
        d.appendChild(h('p', 'msg', t.assunto));
        var b = h('button', 'btn alt', 'Fechar'); b.type = 'button';
        b.onclick = function () { api('POST', '/api/agente/tickets/' + t.id + '/fechar').then(tickets).catch(erro); };
        d.appendChild(b); L.appendChild(d);
      });
    }).catch(function () {});
  }
  $('fl').onsubmit = function (e) {
    e.preventDefault(); K = $('k').value.trim();
    api('GET', '/api/agente/eu').then(function () { sessionStorage.setItem('mt_agente', K); $('k').value = ''; $('ml').textContent = ''; iniciar(); })
      .catch(function (x) { $('ml').textContent = x.message; });
  };
  $('sair').onclick = sair;
  if (K) { api('GET', '/api/agente/eu').then(iniciar).catch(function () { mostrar(false); }); } else { mostrar(false); }
})();
''',
    ),
}
