"""Configuração: lê as variáveis de ambiente. Se faltar algo, o servidor ARRANCA na mesma e mostra no
browser (e em /saude) exatamente o que falta, em vez de rebentar sem explicação no Render."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # lê o ficheiro .env, se existir

OBRIGATORIAS = {
    "GEMINI_API_KEY": "chave da API da IA (Google AI Studio)",
    "ADMIN_API_KEY": "chave que protege o painel e os endpoints /api/*",
}


@dataclass(frozen=True)
class Config:
    verify_token: str
    app_secret: str
    ai_key: str
    admin_key: str
    database_url: str
    ai_model: str
    graph_version: str
    max_workers: int
    hub_pnid: str   # número partilhado da MacTech (opcional)
    hub_token: str
    trust_proxy: bool   # True atrás de um proxy (Render, Railway...) para ler o IP real
    max_dia_empresa: int   # mensagens de clientes por empresa em 24 h (controla custos)
    problemas: tuple   # o que está mal configurado (vazio = tudo bem)


def _inteiro(nome: str, padrao: int, problemas: list) -> int:
    try:
        return max(1, int(os.getenv(nome, str(padrao))))
    except ValueError:
        problemas.append(f"{nome}: tem de ser um número inteiro")
        return padrao


def _proxy_auto() -> bool:
    """No Render/Railway/Fly/Heroku há sempre um proxy: sem isto todos os visitantes parecem ter o
    mesmo IP e o limite de mensagens bloquearia o site inteiro."""
    explicito = os.getenv("TRUST_PROXY")
    if explicito is not None:
        return explicito == "1"
    return any(os.getenv(v) for v in ("RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "DYNO"))


def _chave_ia() -> str:
    """Aceita GEMINI_API_KEY (certo), GOOGLE_API_KEY, ou a antiga ANTHROPIC_API_KEY se lá estiver uma chave do Google.
    Uma chave da Anthropic (começa por sk-ant) é ignorada: não funciona no Gemini."""
    for nome in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        v = os.getenv(nome, "").strip().strip('"').strip("'")
        if v and not v.startswith("sk-ant"):
            return v
    return ""


def _modelo_ia() -> str:
    """Se o AI_MODEL antigo (claude-...) ficou no Render, ignora-o e usa o modelo do Gemini."""
    m = os.getenv("AI_MODEL", "").strip()
    return m if m and not m.lower().startswith("claude") else "gemini-3.1-flash-lite"


def carregar() -> Config:
    problemas = [f"{k}: {desc}" for k, desc in OBRIGATORIAS.items()
                 if k != "GEMINI_API_KEY" and not os.getenv(k, "").strip()]
    if not _chave_ia():
        problemas.append(f"GEMINI_API_KEY: {OBRIGATORIAS['GEMINI_API_KEY']}")
    hub_pnid = os.getenv("HUB_PHONE_NUMBER_ID", "").strip()
    hub_token = os.getenv("HUB_ACCESS_TOKEN", "").strip()
    if bool(hub_pnid) != bool(hub_token):
        problemas.append("HUB_PHONE_NUMBER_ID e HUB_ACCESS_TOKEN: define os dois ou nenhum")
    return Config(
        verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),   # opcional: só para o WhatsApp
        app_secret=os.getenv("WHATSAPP_APP_SECRET", ""),       # opcional: só para o WhatsApp
        ai_key=_chave_ia(),
        admin_key=os.getenv("ADMIN_API_KEY", "").strip(),
        # Muitos serviços dão "postgres://", mas o SQLAlchemy precisa de "postgresql://"
        database_url=os.getenv("DATABASE_URL", "sqlite:///mactech.db").replace("postgres://", "postgresql://", 1),
        ai_model=_modelo_ia(),
        graph_version=os.getenv("GRAPH_API_VERSION", "v21.0"),
        max_workers=_inteiro("MAX_WORKERS", 8, problemas),
        hub_pnid=hub_pnid,
        hub_token=hub_token,
        trust_proxy=_proxy_auto(),
        max_dia_empresa=_inteiro("MAX_MSG_DIA_EMPRESA", 3000, problemas),
        problemas=tuple(problemas),
    )


cfg = carregar()
