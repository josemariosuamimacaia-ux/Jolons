"""Funções do WhatsApp: validar a assinatura da Meta e enviar mensagens."""
import hashlib
import hmac
import time

import requests

from config import cfg


def assinatura_valida(corpo: bytes, cabecalho: str | None) -> bool:
    """Confirma que o pedido veio da Meta (HMAC SHA-256). Cabeçalho vazio ou mal formado = inválido."""
    if not cfg.app_secret or not cabecalho or not cabecalho.startswith("sha256="):
        return False
    esperado = "sha256=" + hmac.new(cfg.app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado.encode(), cabecalho.strip().encode())


def enviar_texto(token: str, phone_number_id: str, numero: str, texto: str) -> None:
    """Envia texto ao cliente. Tenta até 3 vezes em erros temporários (429/5xx/ligação). Lança excepção se falhar."""
    ultimo = None
    for tentativa in range(3):
        try:
            r = requests.post(
                f"https://graph.facebook.com/{cfg.graph_version}/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": numero,
                      "type": "text", "text": {"body": texto[:4000]}},
                timeout=30,
            )
            if r.status_code < 400:
                return
            if r.status_code not in (429, 500, 502, 503, 504):
                r.raise_for_status()   # erro definitivo (token errado, número inválido): não vale repetir
            ultimo = requests.HTTPError(f"Meta respondeu {r.status_code}: {r.text[:200]}")
        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo = e
        if tentativa < 2:
            time.sleep(1.5 * (tentativa + 1))
    raise ultimo
