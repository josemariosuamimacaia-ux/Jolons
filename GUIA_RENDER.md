# Publicar no Render sem erros

## Porque falhava (as causas mais comuns, por ordem)
| O que vês | Causa | Solução |
|---|---|---|
| **404 Not Found** na página inicial, `/painel` ou `/static/...` | O GitHub tem a versão ANTIGA (`Jolons-main`: sem rota `/`, sem painel, sem `assets.py`) | Apaga os ficheiros antigos e carrega os desta versão (ver abaixo) |
| **No open ports detected** / deploy fica a "carregar" | O arranque não usa a porta do Render (`$PORT`) | Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120` (o `render.yaml` já traz isto) |
| **ModuleNotFoundError: No module named 'assets'** (ou `config`, `models`...) | Os ficheiros foram para uma subpasta ou falta um no GitHub | `app.py`, `assets.py` e todos os `.py` têm de estar **na raiz** do repositório, ao lado do `requirements.txt` |
| **ModuleNotFoundError: ... 'chat_page'** com o ficheiro lá | Maiúsculas: no Render `Chat_page.py` ≠ `chat_page.py` | Nomes exatamente em minúsculas, como no código |
| Página **"MacTech: falta configurar"** (503) | Faltam variáveis no Render | Environment: `ANTHROPIC_API_KEY` e `ADMIN_API_KEY` |
| Cria **Static Site** em vez de **Web Service** | Static Site não corre Python | Cria um **Web Service** (Runtime: Python 3) |
| Deploy falha ao instalar (`psycopg2`, `cryptography`) | Python demasiado novo/antigo | Variável `PYTHON_VERSION=3.12.7` (ou o ficheiro `.python-version`) |
| Perdes empresas e conversas a cada deploy | No plano grátis o disco apaga-se (SQLite) | Cria uma base **PostgreSQL** no Render e cola o "Internal Database URL" em `DATABASE_URL` |
| A primeira visita demora ~50 s | Plano grátis adormece | Normal. Opcional: um monitor (UptimeRobot) a abrir `/saude` de 10 em 10 min |

## Sobre os conselhos do Gemini (as fotos)
- **"Regra Redirect/Rewrite `/*` → `/index.html`"**: serve só para *Static Sites* (React/Vue). Este projeto é um servidor Flask: **não adiciones essa regra**, ela quebra as rotas `/api`, `/c/...` e `/painel`.
- **"Usa caminhos relativos (`login.html`)"**: também é para sites estáticos. Aqui os caminhos começam por `/` (`/static/chat.js`) e estão certos, porque o Flask responde a eles.
- **Maiúsculas e minúsculas**: esse conselho está certo e vale aqui (nomes dos `.py`).

## Passo a passo (3 minutos)
1. No GitHub, apaga o conteúdo antigo do repositório e carrega **todos os ficheiros deste zip na raiz** (arrasta os ficheiros, não uma pasta). Não carregues `.env`.
2. No Render: **New > Blueprint** > escolhe o repositório (usa o `render.yaml`). Preenche `ANTHROPIC_API_KEY`.
3. Espera o deploy ficar "Live". Abre `https://O-TEU-SITE.onrender.com/saude` → `{"status":"ok"}`.
4. Abre `/painel`, entra com a `ADMIN_API_KEY` (Render > Environment) e clica **Testar sistema**.
5. Se der erro: Render > **Logs**. A última linha vermelha diz a causa; compara com a tabela acima e, se não achares, manda-ma.

Teste completo: `python verificar.py https://O-TEU-SITE.onrender.com A_TUA_ADMIN_API_KEY`
