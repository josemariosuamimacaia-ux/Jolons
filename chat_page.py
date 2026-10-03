"""Página do chat web (link partilhável ou iframe): /c/<slug>."""

PAGINA = """<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{ nome }} — atendimento</title>
<style>
:root{--bg:#e9f0ec;--card:#fff;--ink:#10201e;--mut:#506560;--out:#d4f4c6;--hum:#ffe9b8;--acc:#128c4a;--accT:#fff;--line:#c9d8d1}
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
</style></head><body>
<header><div class="dot">{{ nome[:1] }}</div><div><b>{{ nome }}</b><small>assistente com IA</small></div></header>
<main id="log" role="log" aria-live="polite"></main>
<form id="f"><input id="t" maxlength="1000" placeholder="Escreve a tua mensagem" autocomplete="off" aria-label="Mensagem"><button type="submit">Enviar</button></form>
<footer>Atendimento automático com IA · MacTech</footer>
<script type="application/json" id="cfg">{{ cfg|tojson }}</script>
<script>
var C=JSON.parse(document.getElementById('cfg').textContent),log=document.getElementById('log'),inp=document.getElementById('t');
var vistas=0,hum=false,ocupado=false,timer=null,base='/chat/'+C.slug;
function sid(){try{var k='mt_'+C.slug,s=localStorage.getItem(k);if(!s){s=(window.crypto&&crypto.randomUUID?crypto.randomUUID():String(Math.random()).slice(2)+Date.now()).replace(/[^A-Za-z0-9-]/g,'');localStorage.setItem(k,s)}return s}catch(e){return window.__s||(window.__s=String(Math.random()).slice(2)+String(Date.now()))}}
var S=sid();
function add(txt,cls){var d=document.createElement('div');d.className='m '+cls;if(cls==='human'){var s=document.createElement('small');s.textContent='equipa';d.appendChild(s)}d.appendChild(document.createTextNode(txt));log.appendChild(d);log.scrollTop=log.scrollHeight;return d}
function mostrar(ms){ms.forEach(function(m){if(m.id>vistas)vistas=m.id;add(m.conteudo,m.remetente==='user'?'me':m.remetente==='human'?'human':'assistant')})}
function parar(){if(timer){clearInterval(timer);timer=null}}
function poll(){fetch(base+'/mensagens?sessao='+S+'&desde='+vistas).then(function(r){return r.json()}).then(function(j){mostrar(j.mensagens||[]);hum=!!j.humano;if(!hum)parar()}).catch(function(){})}
function iniciar(){if(!timer)timer=setInterval(poll,4000)}
fetch(base+'/mensagens?sessao='+S+'&desde=0&tudo=1').then(function(r){return r.json()}).then(function(j){
 var ms=j.mensagens||[];if(ms.length){mostrar(ms);hum=!!j.humano;if(hum)iniciar()}else add('Olá! Sou o assistente da '+C.nome+'. Como posso ajudar?','assistant')
}).catch(function(){add('Olá! Sou o assistente da '+C.nome+'. Como posso ajudar?','assistant')});
document.getElementById('f').onsubmit=function(e){e.preventDefault();var t=inp.value.trim();if(!t||ocupado)return;inp.value='';add(t,'me');ocupado=true;var w=hum?null:add('…','assistant');
 fetch(base+'/mensagem',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessao:S,texto:t})})
 .then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}})})
 .then(function(x){if(w)w.remove();if(!x.ok){add(x.j.erro||'Não foi possível enviar.','assistant')}else{mostrar(x.j.mensagens||[]);hum=!!x.j.humano;if(hum)iniciar()}})
 .catch(function(){if(w)w.remove();add('Sem ligação. Tenta de novo.','assistant')})
 .then(function(){ocupado=false})};
</script></body></html>"""
