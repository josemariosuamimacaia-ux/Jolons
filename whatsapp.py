"""Funções do WhatsApp: validar a assinatura da Meta e enviar mensagens."""
import hashlib
import hmac

import requests

from config import cfg


def assinatura_valida(corpo: bytes, cabecalho: str | None) -> bool:
    """Confirma que o pedido veio da Meta (HMAC SHA-256). Cabeçalho vazio ou mal formado = inválido."""
    if not cfg.app_secret or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = "sha256=" + hmac.new(cfg.app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado.encode(), cabecalho.strip().encode())


def enviar_texto(token: str, phone_number_id: str, numero: str, texto: str) -> None:
    """Envia texto ao cliente usando o token da empresa. Lança excepção se a Meta recusar."""
    r = requests.post(
        f"https://graph.facebook.com/{cfg.graph_version}/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"messaging_product": "whatsapp", "to": numero,
              "type": "text", "text": {"body": texto[:4000]}},
        timeout=30,
    )
    r.raise_for_status()
