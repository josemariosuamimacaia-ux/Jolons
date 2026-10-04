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

function sid() {
  try {
    var k = 'mt_' + C.slug, s = localStorage.getItem(k);
    if (!s) {
      s = (window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Math.random()).slice(2) + Date.now()).replace(/[^A-Za-z0-9-]/g, '');
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

function enviar(t) {
  t = t.trim(); if (!t || ocupado) return;
  if (sug) { sug.remove(); sug = null; }
  add(t, 'me'); ocupado = true;
  var w = hum ? null : add('…', 'assistant');
  fetch(base + '/mensagem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessao: S, texto: t }) })
    .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
    .then(function (x) {
      if (w) w.remove();
      if (!x.ok) { add(x.j.erro || 'Não foi possível enviar. Tenta de novo.', 'assistant'); }
      else { mostrar(x.j.mensagens || []); hum = !!x.j.humano; if (hum) iniciar(); }
    })
    .catch(function () { if (w) w.remove(); add('Sem ligação. Tenta de novo.', 'assistant'); })
    .then(function () { ocupado = false; });
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
  function iniciar() { mostrar(true); carregarEmpresas(); carregarHumanos(); carregarConversas(); carregarSemResposta(); clearInterval(tm); tm = setInterval(carregarHumanos, 15000); }

  $('fl').onsubmit = function (e) {
    e.preventDefault(); K = $('k').value.trim();
    api('GET', '/api/empresas').then(function () {
      sessionStorage.setItem('mt_admin', K); $('k').value = ''; $('ml').textContent = ''; iniciar();
    }).catch(function (x) { $('ml').textContent = x.message; });
  };
  $('sair').onclick = sair;

  function carregarEmpresas() {
    Promise.all([api('GET', '/api/empresas'), api('GET', '/api/estatisticas?dias=7')]).then(function (r) {
      var st = {}; r[1].empresas.forEach(function (s) { st[s.empresa] = s; });
      var L = $('lista'); L.textContent = '';
      if (!r[0].empresas.length) { L.appendChild(h('p', 'msg', 'Ainda não há empresas. Regista a primeira acima.')); return; }
      r[0].empresas.forEach(function (e) {
        var c = h('div', 'item');
        c.appendChild(h('b', null, e.nome + ' '));
        var fim = e.estado === 'teste' && e.teste_ate ? ' até ' + new Date(e.teste_ate).toLocaleString('pt-PT') : '';
        c.appendChild(h('span', 'badge' + (e.ativa ? '' : ' off'), e.estado + fim));
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
        [['Ativar (pagou)', 'ativo'], ['Suspender', 'suspenso'], ['+2 dias de teste', 'teste']].forEach(function (x) {
          var bt = h('button', 'btn alt', x[0]); bt.type = 'button';
          bt.onclick = function () { api('POST', '/api/empresas/' + e.id + '/estado', { estado: x[1], dias: 2 }).then(carregarEmpresas).catch(erro); };
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
      $('me').textContent = 'Empresa registada. Chat: ' + location.origin + j.chat_url + ' (tem 2 dias de teste).';
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
}
