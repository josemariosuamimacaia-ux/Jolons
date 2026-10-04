# Ligar o CRM/ERP de uma empresa

A MacTech faz `POST` ao endereço https da empresa (público; endereços internos são recusados) e a empresa responde com JSON (máx. 20 KB, até 8 s).

## Pedido
Cabeçalhos: `Content-Type: application/json` e `X-MacTech-Assinatura: sha256=<HMAC-SHA256 do corpo com o segredo>`.
```json
{"acao": "consultar_encomenda", "dados": {"codigo": "E100"}, "empresa": "loja-demo",
 "cliente": ["923000000"], "identidade_verificada": true, "ts": 1790000000}
```
Ações: `consultar_stock` (`termo`), `consultar_encomenda` (`codigo`), `pedir_fatura` (`codigo`).
`identidade_verificada` é `true` no WhatsApp e `false` no chat web. **O sistema da empresa tem de confirmar que a encomenda pertence a um dos contactos em `cliente`.**

## Exemplo de receção (Flask)
```python
import hmac, hashlib, json, time
from flask import Flask, request, jsonify
app = Flask(__name__)
SEGREDO = b"o-mesmo-segredo-do-painel"

@app.post("/mactech")
def mactech():
    corpo = request.get_data()
    esperado = "sha256=" + hmac.new(SEGREDO, corpo, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperado, request.headers.get("X-MacTech-Assinatura", "")):
        return "assinatura inválida", 403
    d = json.loads(corpo)
    if abs(time.time() - d["ts"]) > 300:           # rejeita pedidos repetidos
        return "expirado", 400
    if d["acao"] == "consultar_encomenda":
        # procura no teu ERP; só devolve se o contacto bater certo com d["cliente"]
        return jsonify(estado="Enviada", previsao="2 dias")
    if d["acao"] == "consultar_stock":
        return jsonify(produtos=[{"nome": "Portátil Pro 14", "preco": 450000, "quantidade": 3}])
    if d["acao"] == "pedir_fatura":
        return jsonify(ok=True, mensagem="Fatura FT 2026/123 emitida e enviada por email.")
    return jsonify(erro="ação desconhecida"), 400
```
