"""Chamada à IA (Anthropic) com as regras da empresa."""
import requests

from config import cfg

REGRAS_BASE = (
    "\n\nRegras gerais: responde em português, com mensagens curtas e simpáticas, como no WhatsApp. "
    "Usa apenas a informação acima. Nunca inventes preços, stock, prazos nem características: "
    "se não souberes, diz que uma pessoa da equipa confirma. "
    "Se a pergunta não tiver a ver com o negócio, diz com simpatia que só ajudas com os produtos e serviços."
)


def responder(system_prompt: str, historico: list[dict]) -> str:
    """historico: lista [{'role': 'user'|'assistant', 'content': str}], a começar e a acabar em 'user'."""
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": cfg.ai_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": cfg.ai_model, "max_tokens": 400,
              "system": system_prompt + REGRAS_BASE, "messages": historico},
        timeout=30,
    )
    if r.status_code >= 400:   # mostra o motivo real do erro no log (ex.: modelo inválido, chave errada)
        raise RuntimeError(f"A API da IA respondeu {r.status_code}: {r.text[:300]}")
    texto = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    if not texto.strip():
        raise ValueError("A IA devolveu uma resposta vazia")
    return texto.strip()
