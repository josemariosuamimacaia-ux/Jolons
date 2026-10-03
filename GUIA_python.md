# MacTech — guia para criar o assistente de WhatsApp com IA em Python

Documento para estudar ao teu ritmo. Cada parte tem uma explicação curta e o código. Faz uma parte de cada vez.

## 1. Como funciona (a ideia toda)

```
Cliente --WhatsApp--> Meta (WhatsApp Business) --webhook--> O TEU SERVIDOR --> IA
Cliente <--WhatsApp-- Meta <------ resposta ------------- O TEU SERVIDOR <-- IA
```

Um servidor é um programa Python sempre ligado. Faz quatro coisas:

1. **Recebe** a mensagem (a Meta chama o teu endereço, o "webhook").
2. **Lembra** o que aquele número já disse (memória da conversa).
3. **Pergunta à IA**, enviando o catálogo e as regras do negócio mais a conversa.
4. **Envia** a resposta ao cliente.

O "conhecimento" do bot é só texto: o catálogo e as regras. Mudar de negócio é mudar esse texto.

## 2. Preparar o computador

1. Instalar Python 3.11 ou superior.
2. Criar uma pasta `mactech` e, dentro dela:

```bash
python -m venv venv
# Windows: venv\Scripts\activate     Linux/Mac: source venv/bin/activate
pip install flask requests
```

- `flask` cria o servidor.
- `requests` faz chamadas a outros serviços (IA e WhatsApp).

## 3. Segredos (nunca no código)

Crias estas variáveis de ambiente (no teu computador, ou nos "Secrets" do serviço onde publicares):

| Nome | Para quê |
| --- | --- |
| `WHATSAPP_VERIFY_TOKEN` | Uma palavra-passe que inventas, para a Meta confirmar o webhook |
| `WHATSAPP_ACCESS_TOKEN` | Token da Meta para enviar mensagens |
| `WHATSAPP_PHONE_NUMBER_ID` | ID do número empresarial na Meta |
| `WHATSAPP_APP_SECRET` | Segredo da app Meta, para validar que o pedido é mesmo da Meta |
| `ANTHROPIC_API_KEY` | Chave da IA |

Regra de ouro: estes valores nunca vão para o GitHub, para o HTML ou para mensagens.

## 4. O código completo (`app.py`)

```python
import os, hmac, hashlib, threading
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ["WHATSAPP_VERIFY_TOKEN"]
WA_TOKEN     = os.environ["WHATSAPP_ACCESS_TOKEN"]
PHONE_ID     = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
APP_SECRET   = os.environ["WHATSAPP_APP_SECRET"]
AI_KEY       = os.environ["ANTHROPIC_API_KEY"]

GRAPH_URL = "https://graph.facebook.com/v21.0"  # confirma a versão actual na documentação da Meta
AI_MODEL  = "claude-haiku-4-5-20251001"      # modelo rápido e barato; confirma o nome atual na documentação

# ---- O conhecimento do negócio: edita isto ----
NEGOCIO = "Loja MacTech: vende computadores, telemóveis e acessórios."
CATALOGO = """
- Portátil Pro 14: ecrã 14", 16 GB RAM, SSD 512 GB, bateria até 12 h, garantia 1 ano.
- Telemóvel Lite 5G: ecrã 6,5", 128 GB, câmara dupla 50 MP, dual SIM, garantia 1 ano.
- Auscultadores Air: Bluetooth, cancelamento de ruído, 30 h de autonomia, USB-C.
"""
REGRAS = (
    "Responde em português, com mensagens curtas e simpáticas. "
    "Usa só o catálogo. Preços, stock e prazos de entrega não estão no catálogo: "
    "diz que uma pessoa da equipa confirma e pede o nome do cliente. "
    "Nunca inventes características. Se a pergunta não for sobre o negócio, diz que só ajudas com os produtos."
)
SYSTEM = f"{NEGOCIO}\nCatálogo:\n{CATALOGO}\n{REGRAS}"

# ---- Memória das conversas (em RAM: perde-se ao reiniciar) ----
conversas = {}   # {"244900000000": [{"role": "user", "content": "..."}, ...]}

def perguntar_ia(numero, texto):
    historico = conversas.setdefault(numero, [])
    historico.append({"role": "user", "content": texto})
    del historico[:-10]                      # guarda só as últimas 10 mensagens
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": AI_KEY, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": AI_MODEL, "max_tokens": 400,
              "system": SYSTEM, "messages": historico},
        timeout=30,
    )
    r.raise_for_status()
    resposta = r.json()["content"][0]["text"]
    historico.append({"role": "assistant", "content": resposta})
    return resposta

def enviar_whatsapp(numero, texto):
    requests.post(
        f"{GRAPH_URL}/{PHONE_ID}/messages",
        headers={"Authorization": f"Bearer {WA_TOKEN}"},
        json={"messaging_product": "whatsapp", "to": numero,
              "type": "text", "text": {"body": texto}},
        timeout=30,
    )

def assinatura_valida(corpo, cabecalho):
    esperado = "sha256=" + hmac.new(APP_SECRET.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho or "")

def tratar(numero, texto):
    try:
        enviar_whatsapp(numero, perguntar_ia(numero, texto))
    except Exception as erro:
        print("Erro:", erro)
        enviar_whatsapp(numero, "Desculpa, tive um problema. Uma pessoa da equipa vai ajudar-te.")

@app.get("/webhook")                          # a Meta confirma o endereço aqui
def verificar():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge", ""), 200
    return "token inválido", 403

@app.post("/webhook")                         # as mensagens chegam aqui
def receber():
    if not assinatura_valida(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        return "assinatura inválida", 403
    dados = request.get_json(silent=True) or {}
    try:
        msg = dados["entry"][0]["changes"][0]["value"]["messages"][0]
        if msg["type"] == "text":
            threading.Thread(target=tratar, args=(msg["from"], msg["text"]["body"])).start()
    except (KeyError, IndexError):
        pass                                   # eventos sem mensagem (ex.: estado de entrega)
    return {"received": True}, 200            # responder rápido à Meta

if __name__ == "__main__":
    app.run(port=3000)
```

## 5. Explicação por blocos

- **Segredos:** `os.environ[...]` lê as variáveis da secção 3. Se faltar uma, o programa pára logo e avisa.
- **`SYSTEM`:** é o texto que diz à IA quem ela é e o que sabe. É a parte mais importante do produto.
- **`conversas`:** um dicionário com o histórico de cada número. Sem isto, a IA esqueceria a pergunta anterior.
- **`perguntar_ia`:** junta a mensagem ao histórico e envia tudo à IA. A resposta volta em `content[0].text`.
- **`enviar_whatsapp`:** faz um pedido à API da Meta para mandar texto ao cliente.
- **`assinatura_valida`:** confirma que o pedido veio mesmo da Meta e não de um impostor.
- **`@app.get("/webhook")`:** a Meta usa-o uma vez para confirmar que o endereço é teu.
- **`@app.post("/webhook")`:** recebe cada mensagem, responde logo `received: true` e trata da IA em segundo plano (a Meta repete o pedido se demorares).

## 6. Testar

Como o servidor exige assinatura, para testar em local o mais simples é:

1. Arrancar: `python app.py`
2. Expor à internet com uma ferramenta como ngrok (`ngrok http 3000`), que dá um endereço público.
3. No painel da Meta, registar `https://O-TEU-ENDERECO/webhook` e o mesmo `WHATSAPP_VERIFY_TOKEN`.
4. Enviar uma mensagem ao número de teste e ver o terminal.

Para testar só a IA, sem WhatsApp, chama `perguntar_ia("teste", "O portátil tem quanta memória?")` num ficheiro à parte e imprime o resultado.

## 7. Limites desta versão (o que falta para vender)

1. **Base de dados:** a memória perde-se quando reinicia. Passar para SQLite ou PostgreSQL (contactos, conversas, mensagens).
2. **Passagem a humano:** marcar a conversa como "precisa de pessoa" e avisar a equipa (e o bot deixar de responder).
3. **Painel:** página onde a equipa vê as conversas e edita o catálogo sem mexer no código.
4. **Consentimento e privacidade:** avisar o cliente de que fala com uma IA e guardar só o necessário.
5. **Limites e custos:** limitar mensagens por número por minuto e acompanhar o custo da IA por cliente.
6. **Publicação:** pôr o servidor num serviço sempre ligado (ex.: Render, Railway, VPS) em vez do teu computador.
7. **Várias empresas:** um catálogo por cliente, para vender o mesmo produto a muitos negócios.

## 8. Exercícios (por esta ordem)

1. Muda o `CATALOGO` para o teu próprio negócio e testa 10 perguntas difíceis.
2. Faz o bot dizer "uma pessoa vai ajudar" sempre que o cliente escrever "reclamação".
3. Guarda as mensagens num ficheiro SQLite em vez do dicionário.
4. Cria um endereço `/saude` que devolve `{"ok": true}`.
5. Põe o catálogo num ficheiro `catalogo.txt` e lê-o ao arrancar.

## 9. Para levar ao Gemini (briefing)

Copia esta secção, junto com o ficheiro `mactech.html` e a secção 4.

> **Contexto:** a MacTech é uma empresa em Angola que quer vender assistentes de atendimento no WhatsApp com IA para negócios, porque há poucas soluções assim no mercado. O fundador está a aprender a programar em Python.
>
> **O que existe:** (1) uma página de demonstração em HTML (`mactech.html`) onde a IA responde livremente a perguntas sobre um catálogo de exemplo; (2) um servidor Python em Flask (secção 4) que recebe mensagens do WhatsApp Business, valida a assinatura, consulta a IA com o catálogo e responde. A memória das conversas está em RAM.
>
> **Peço-te:**
> 1. Rever o código e apontar erros, riscos de segurança e melhorias.
> 2. Propor a arquitectura para vários clientes (multi-empresa), com base de dados.
> 3. Sugerir como fazer a passagem para humano e um painel simples.
> 4. Estimar custos por cliente (IA e WhatsApp) e propor um modelo de preços adequado ao mercado angolano.
> 5. Sugerir os primeiros 5 sectores a vender (lojas, clínicas, restaurantes…) e um guião de venda.
> 6. Ajudar a montar a apresentação para investidores.

## 10. Aviso importante

As versões da API da Meta e os nomes dos modelos de IA mudam. Antes de publicar, confirma sempre a documentação oficial actual da WhatsApp Business Platform e da API da IA. Nunca partilhes os tokens em conversas, nem no Gemini.
