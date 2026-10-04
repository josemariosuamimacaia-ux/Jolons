# MacTech — servidor multi-empresa (Flask)

> **Versão 2.** Para publicar no Render lê `GUIA_RENDER.md`. Nível 4 (departamentos, atendentes, ERP): `NIVEL4.md` e `INTEGRACAO.md`.

## Ficheiros
- `app.py` rotas, multi-tenant e passagem a humano
- `models.py` base de dados (empresas, conversas, mensagens)
- `whatsapp.py` assinatura HMAC e envio de mensagens
- `ia.py` chamada à IA
- `assets.py` CSS, JavaScript e HTML do site embutidos (já não precisa de pasta static)
- `ferramentas.py`, `nivel4.py`, `segredos.py` nível 4 e cifra de tokens
- `static/` (versão antiga, já não é usada) ficheiros do site (CSS e JavaScript): `chat.css` e `chat.js` (chat web), `style.css` (página inicial). Têm de ir para o GitHub junto com o resto.
- `config.py` variáveis de ambiente (falha com mensagem clara se faltar alguma)

## 1. Instalar
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env  (depois preenche)
```

**Erro "Faltam variáveis de ambiente obrigatórias"?** É normal quando falta o ficheiro `.env`. Corre os comandos dentro da pasta `servidor`, copia o `.env.example` para `.env` e preenche `ANTHROPIC_API_KEY` e `ADMIN_API_KEY`. Para criar uma chave de admin forte: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. As variáveis do WhatsApp podem ficar em branco enquanto só usares o chat web.

## Painel de administração (sem comandos)
Abre `https://O-TEU-SITE/painel` (ou `http://localhost:3000/painel`), entra com a tua `ADMIN_API_KEY` e podes: registar empresas com um formulário, copiar o link do chat de cada uma, ver quantas pessoas entraram, ativar, suspender ou prolongar o teste, e responder a clientes que pediram uma pessoa. Tudo isto usa os mesmos endpoints `/api/*` descritos abaixo.

## 2. Criar a base de dados
É criada sozinha ao arrancar (`mactech.db`). Para criar sem arrancar o servidor:
```bash
python -c "from models import init_db; init_db()"
```

## 3. Executar
```bash
python app.py                                  # desenvolvimento (porta 3000)
gunicorn -w 2 --threads 4 -b 0.0.0.0:3000 app:app   # produção
```
Teste: `curl http://localhost:3000/saude` → `{"status":"ok"}`
Abre `http://localhost:3000/` no browser: deve aparecer a página inicial da MacTech (antes dava erro 404 "Not Found").

## 4. Registar uma empresa
```bash
curl -X POST http://localhost:3000/api/empresas \
  -H "X-API-Key: A_TUA_ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"nome":"Loja Exemplo","wa_phone_number_id":"123456789","wa_access_token":"TOKEN_DA_META",
       "system_prompt":"Loja Exemplo vende telemóveis. Catálogo:\n- Telemóvel X: 128 GB, garantia 1 ano."}'
```

## 5. Operador humano responde
Depois de o cliente pedir "humano", "atendente", "reclamação" ou "falar com pessoa":
```bash
curl -X POST http://localhost:3000/api/responder-humano \
  -H "X-API-Key: A_TUA_ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"phone_number_id":"123456789","cliente_numero":"244900000000","texto":"Olá, sou o João da equipa."}'
```

## 6. Ligar ao WhatsApp
1. Publica o servidor num endereço HTTPS (ou usa ngrok em testes).
2. No painel da Meta, regista `https://O-TEU-ENDERECO/webhook` e o mesmo `WHATSAPP_VERIFY_TOKEN`; subscreve o evento de mensagens.
3. Cada empresa regista o seu `wa_phone_number_id` e token em `/api/empresas`.

## Número partilhado (a MacTech serve várias empresas)
Define no `.env` o `HUB_PHONE_NUMBER_ID` e o `HUB_ACCESS_TOKEN` do número da MacTech. Quando um cliente escreve para esse número:
1. O bot pergunta "De que empresa quer ser atendido?" e lista as empresas registadas.
2. O cliente responde com o número ou o nome; o bot passa a usar os dados dessa empresa. Para trocar, o cliente escreve "mudar de empresa".
3. A passagem a humano funciona igual. Para o operador, `phone_number_id` é o do número partilhado.

Registar uma empresa **sem número próprio** (só `nome` e `system_prompt`):
```bash
curl -X POST http://localhost:3000/api/empresas \
  -H "X-API-Key: A_TUA_ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"nome":"Clínica Exemplo","system_prompt":"Clínica Exemplo. Serviços: consulta geral, análises. Horário: seg-sex 8h-17h."}'
```
Para tirar uma empresa da lista, envia `"no_hub": false`. Devolver uma conversa ao bot: `POST /api/devolver-ia` com `phone_number_id` e `cliente_numero`.

**Se já criaste o `mactech.db` com a versão anterior, apaga-o** (as tabelas mudaram) e arranca de novo.

## Teste grátis de 2 dias e estatísticas
- Cada empresa nova começa em `teste` e tem 2 dias. Passado esse tempo, se não estiver `ativo`, o bot deixa de responder (o cliente recebe um aviso de indisponibilidade) e aparece `[ATENÇÃO]` no log.
- Quando a empresa pagar, ativa-a:
```bash
curl -X POST http://localhost:3000/api/empresas/1/estado \
  -H "X-API-Key: A_TUA_ADMIN_API_KEY" -H "Content-Type: application/json" -d '{"estado":"ativo"}'
```
Estados: `ativo`, `suspenso`, ou `teste` (com `"dias": 2` para dar mais tempo).
- Ver quantas pessoas entraram (últimos 7 dias, ou muda `dias`):
```bash
curl -H "X-API-Key: A_TUA_ADMIN_API_KEY" "http://localhost:3000/api/estatisticas?dias=7"
```
Devolve, por empresa: `pessoas` (números diferentes), `mensagens_clientes`, `respostas_ia`, `respostas_equipa` e `conversas_com_humano`.
- **Se já criaste o `mactech.db`, apaga-o outra vez** (há colunas novas).

## Chat web (sem WhatsApp, sem Meta)
Cada empresa registada recebe um endereço de chat: `https://O-TEU-SITE/c/<slug>` (o `slug` aparece na resposta de `POST /api/empresas`, por exemplo `loja-exemplo`).
- **Partilhar:** envia o link ou faz um QR code.
- **Meter num site:** `<iframe src="https://O-TEU-SITE/c/loja-exemplo" style="width:380px;height:560px;border:0"></iframe>`
- Funciona com tudo o que já existe: catálogo, IA, passagem a humano, teste de 2 dias e estatísticas.
- **Operador:** `GET /api/conversas-humano` mostra quem espera. Responde com `POST /api/responder-humano`, usando `"phone_number_id": "web"` e o `cliente_numero` que aparecer (é o id da sessão). O cliente vê a resposta em poucos segundos.
- **Proteções:** máximo de 1000 caracteres por mensagem e limites por visitante e por sessão, porque o endereço é público e cada resposta tem custo de IA. Atrás de um proxy (Render, Railway), define `TRUST_PROXY=1`.
- **Se já criaste o `mactech.db`, apaga-o outra vez** (há colunas novas).

## Pôr online (alojamento)
1. Põe a pasta `servidor` num repositório do GitHub (sem o ficheiro `.env`).
2. Num serviço de alojamento (por exemplo Render ou Railway), cria um **Web Service** ligado a esse repositório.
3. Comando de instalação: `pip install -r requirements.txt`. Comando de arranque: `gunicorn -w 2 --threads 4 -b 0.0.0.0:$PORT app:app`
4. Nas variáveis de ambiente do serviço (Secrets), define: `ANTHROPIC_API_KEY`, `ADMIN_API_KEY`, `TRUST_PROXY=1`, (as variáveis do WhatsApp só são precisas se usares o WhatsApp).
5. **Base de dados:** o ficheiro SQLite pode ser apagado quando o serviço reinicia. Cria uma base PostgreSQL no mesmo serviço e põe o endereço dela em `DATABASE_URL`.
6. Quando estiver online, regista a empresa com o `curl` da secção 4, trocando `localhost:3000` pelo endereço do teu serviço. O chat fica em `https://O-TEU-SERVICO/c/<slug>`.
Os planos grátis costumam adormecer o servidor quando ninguém o usa. Confirma as regras atuais de cada serviço.

## Novidades desta versão
- **Respostas mais fiáveis:** a IA tenta até 3 vezes em erros temporários, sabe a data e a hora de Luanda e ignora pedidos para mudar as suas regras.
- **Perguntas sem resposta:** quando o bot não sabe, regista a pergunta. Vê-as no painel e acrescenta-as ao catálogo.
- **Contactos:** o telefone ou email que o cliente escreve no chat web fica guardado. Exporta tudo em CSV no painel.
- **Conversas:** vê as conversas completas no painel.
- **Estado do sistema:** o botão "Testar sistema" no painel diz, em português, se a base de dados, a chave da IA, o crédito e o modelo estão certos.
- **Segurança:** a chave de administração trava depois de 10 tentativas erradas; o painel não pode ser metido num iframe; mensagens duplicadas da Meta são ignoradas.
- **Erros amigáveis:** páginas inexistentes mostram um aviso em vez de um ecrã vazio.
- **Base de dados antiga:** as colunas novas são acrescentadas sozinhas ao arrancar.

## Verificar tudo depois de publicar
No teu computador, dentro da pasta `servidor`:
```bash
pip install -r requirements.txt
python verificar.py https://O-TEU-SITE.onrender.com A_TUA_ADMIN_API_KEY
```
Faz 15 verificações (página, saúde, ficheiros, chave, IA, empresa de teste, chat, passagem a humano, estatísticas) e diz o que falhou. A empresa de teste fica suspensa no fim.

## Avisos antes de vender
- **Modelo de IA:** o `claude-3-haiku-20240307` foi desativado pela Anthropic em abril de 2026 e já não responde. O padrão agora é `claude-haiku-4-5-20251001`. Se um dia der erro de modelo, confirma o nome atual na documentação e muda `AI_MODEL` no `.env`.
- **Tokens na base de dados:** estão em texto simples. Cifra-os antes de produção e protege o ficheiro `.db` (ou passa a PostgreSQL via `DATABASE_URL`).
- **Chave de admin:** os endpoints `/api/*` exigem `X-API-Key`. Sem isto, qualquer pessoa poderia criar empresas ou enviar mensagens.
- **Privacidade:** informa os clientes de que falam com uma IA e define quanto tempo guardas as mensagens.
