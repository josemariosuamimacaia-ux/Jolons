"""Página do chat web (link partilhável ou iframe): /c/<slug>."""

PAGINA = """<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{{ nome }} — atendimento</title>
<link rel="stylesheet" href="/static/chat.css"></head><body>
<header><div class="dot">{{ nome[:1] }}</div><div><b>{{ nome }}</b><small>assistente com IA</small></div></header>
<main id="log" role="log" aria-live="polite"></main>
<form id="f"><input id="t" maxlength="1000" placeholder="Escreve a tua mensagem" autocomplete="off" aria-label="Mensagem"><button type="submit">Enviar</button></form>
<footer>Atendimento automático com IA · as conversas são guardadas para melhorar o serviço · MacTech</footer>
<script type="application/json" id="cfg">{{ cfg|tojson }}</script>
<script src="/static/chat.js"></script></body></html>"""
