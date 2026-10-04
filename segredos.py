"""Cifra os tokens guardados na base de dados (token do WhatsApp, segredo das integrações).

Define ENCRYPTION_KEY (qualquer texto longo e secreto). Sem ela, os valores ficam em texto simples
(como na versão 1) e o servidor avisa no log. Se mudares a chave, os tokens antigos deixam de abrir."""
import base64
import hashlib
import logging
import os

log = logging.getLogger("mactech.segredos")
_PREFIXO = "enc:"
_fernet = None
_avisou = False


def _f():
    global _fernet
    chave = os.getenv("ENCRYPTION_KEY", "").strip()
    if not chave:
        return None
    if _fernet is None:
        from cryptography.fernet import Fernet
        _fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(chave.encode()).digest()))
    return _fernet


def cifrar(valor):
    global _avisou
    if not valor:
        return valor
    f = _f()
    if f is None:
        if not _avisou:
            log.warning("ENCRYPTION_KEY não definida: tokens guardados em texto simples")
            _avisou = True
        return valor
    return _PREFIXO + f.encrypt(valor.encode()).decode()


def decifrar(valor):
    if not valor or not valor.startswith(_PREFIXO):
        return valor or ""   # valor antigo, sem cifra
    f = _f()
    if f is None:
        log.error("Há tokens cifrados mas falta ENCRYPTION_KEY")
        return ""
    try:
        return f.decrypt(valor[len(_PREFIXO):].encode()).decode()
    except Exception:
        log.error("Não foi possível decifrar um token (ENCRYPTION_KEY mudou?)")
        return ""
