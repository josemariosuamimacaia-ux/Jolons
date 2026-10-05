"""
responder.py - resposta em camadas para o MacTech.

Ordem: 1) FAQ/palavras-chave da empresa  2) IA (Gemini, chave gratuita)  3) humano.
Variáveis de ambiente (Render > Environment):
  GEMINI_API_KEY  -> chave criada em aistudio.google.com
  GEMINI_MODEL    -> opcional, por omissão "gemini-2.5-flash"
Precisa de "requests" no requirements.txt.
"""
import os
import re
import logging
import unicodedata

import requests

log = logging.getLogger("mactech.responder")

MSG_HUMANO = ("Vou passar o seu pedido a um atendente humano. "
              "Entraremos em contacto o mais breve possível.")


def _norm(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", texto)


# ---------- Camada 1: FAQ ----------
def resposta_faq(pergunta, faqs):
    """faqs: lista de dicts {"pergunta": str, "resposta": str, "palavras": [str]}"""
    if not faqs:
        return None
    q = set(_norm(pergunta).split())
    melhor, melhor_score = None, 0.0
    for f in faqs:
        chaves = set(_norm(" ".join(f.get("palavras", []) or [f.get("pergunta", "")])).split())
        if not chaves:
            continue
        score = len(q & chaves) / len(chaves)
        if score > melhor_score:
            melhor, melhor_score = f, score
    return melhor["resposta"] if melhor and melhor_score >= 0.6 else None


# ---------- Camada 2: IA (Gemini) ----------
def resposta_ia(pergunta, info_empresa="", historico=None):
    chave = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
    if not chave:
        raise RuntimeError("GEMINI_API_KEY não está definida no ambiente")
    modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    instrucao = (
        "És o assistente de atendimento de uma empresa. Responde em português, "
        "de forma curta e educada, usando apenas as informações abaixo. "
        "Se não souberes, diz que vais passar a um atendente.\n\n"
        f"INFORMAÇÕES DA EMPRESA:\n{info_empresa}"
    )
    contents = []
    for turno in (historico or [])[-6:]:  # {"role": "user"|"model", "text": str}
        contents.append({"role": turno["role"], "parts": [{"text": turno["text"]}]})
    contents.append({"role": "user", "parts": [{"text": pergunta}]})

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
        headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
        json={"system_instruction": {"parts": [{"text": instrucao}]}, "contents": contents},
        timeout=25,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Resposta inesperada do Gemini: {r.text[:300]}")


# ---------- Orquestração ----------
def responder(pergunta, faqs=None, info_empresa="", historico=None):
    """Devolve {"resposta": str, "origem": "faq"|"ia"|"humano", "erro": str|None}"""
    r = resposta_faq(pergunta, faqs)
    if r:
        return {"resposta": r, "origem": "faq", "erro": None}
    try:
        return {"resposta": resposta_ia(pergunta, info_empresa, historico),
                "origem": "ia", "erro": None}
    except Exception as e:  # o erro REAL fica no log do Render
        log.error("Falha na IA: %s", e)
        return {"resposta": MSG_HUMANO, "origem": "humano", "erro": str(e)}


def diagnostico():
    """Chame numa rota /diagnostico para ver o erro real da IA."""
    try:
        return {"ok": True, "resposta": resposta_ia("Responde só: ok")}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
