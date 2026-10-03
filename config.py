"""Configuração: lê as variáveis de ambiente e falha logo, com mensagem clara, se faltar alguma."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # lê o ficheiro .env, se existir

OBRIGATORIAS = {
    "ANTHROPIC_API_KEY": "chave da API da IA",
    "ADMIN_API_KEY": "chave que protege os endpoints /api/*",
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


def carregar() -> Config:
    em_falta = [f"  - {k}: {desc}" for k, desc in OBRIGATORIAS.items() if not os.getenv(k)]
    if em_falta:
        raise RuntimeError(
            "Faltam variáveis de ambiente obrigatórias:\n" + "\n".join(em_falta)
            + "\nCopia .env.example para .env e preenche os valores."
        )
    try:
        workers = int(os.getenv("MAX_WORKERS", "8"))
    except ValueError:
        raise RuntimeError("MAX_WORKERS tem de ser um número inteiro.")
    hub_pnid = os.getenv("HUB_PHONE_NUMBER_ID", "").strip()
    hub_token = os.getenv("HUB_ACCESS_TOKEN", "").strip()
    if bool(hub_pnid) != bool(hub_token):
        raise RuntimeError("Para usar o número partilhado, define HUB_PHONE_NUMBER_ID e HUB_ACCESS_TOKEN (os dois).")
    return Config(
        verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),   # opcional: só para o WhatsApp
        app_secret=os.getenv("WHATSAPP_APP_SECRET", ""),       # opcional: só para o WhatsApp
        ai_key=os.environ["ANTHROPIC_API_KEY"],
        admin_key=os.environ["ADMIN_API_KEY"],
        # Muitos serviços dão "postgres://", mas o SQLAlchemy precisa de "postgresql://"
        database_url=os.getenv("DATABASE_URL", "sqlite:///mactech.db").replace("postgres://", "postgresql://", 1),
        ai_model=os.getenv("AI_MODEL", "claude-haiku-4-5-20251001"),
        graph_version=os.getenv("GRAPH_API_VERSION", "v21.0"),
        max_workers=max(1, workers),
        hub_pnid=hub_pnid,
        hub_token=hub_token,
        trust_proxy=os.getenv("TRUST_PROXY", "0") == "1",
    )


cfg = carregar()
