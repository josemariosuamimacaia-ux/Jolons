"""Teste rápido do servidor que já está online.
Uso:  python verificar.py https://O-TEU-SITE.onrender.com A_TUA_ADMIN_API_KEY
Cria uma empresa de teste ("ZZ Teste automático"), conversa com ela e suspende-a no fim."""
import sys
import uuid

import requests

T = 90  # segundos (o Render pode demorar a acordar)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    base, chave = sys.argv[1].rstrip("/"), sys.argv[2]
    H = {"X-API-Key": chave}
    falhas = []

    def passo(nome, ok, detalhe=""):
        print(("OK      " if ok else "FALHOU  ") + nome + (f"  ->  {detalhe}" if detalhe else ""))
        if not ok:
            falhas.append(nome)

    def pedir(metodo, caminho, **kw):
        try:
            return requests.request(metodo, base + caminho, timeout=T, **kw)
        except Exception as e:
            print(f"        (erro de ligação em {caminho}: {e})")
            return None

    r = pedir("GET", "/")
    passo("Página inicial", bool(r) and r.status_code == 200 and "MacTech" in r.text, r and str(r.status_code))
    r = pedir("GET", "/saude")
    passo("Saúde do servidor e da base de dados", bool(r) and r.status_code == 200, r and r.text[:80])
    r = pedir("GET", "/painel")
    passo("Painel abre", bool(r) and r.status_code == 200, r and str(r.status_code))
    r = pedir("GET", "/static/chat.js")
    passo("Ficheiros da pasta static", bool(r) and r.status_code == 200, "falta a pasta static no GitHub?")
    r = pedir("GET", "/agente")
    passo("Página dos atendentes (nível 4)", bool(r) and r.status_code == 200, r and str(r.status_code))
    r = pedir("GET", "/api/tickets", headers=H)
    passo("Tickets (nível 4)", bool(r) and r.status_code == 200, r and str(r.status_code))
    r = pedir("GET", "/api/empresas")
    passo("API recusa pedidos sem chave", bool(r) and r.status_code == 401, r and str(r.status_code))
    r = pedir("GET", "/api/empresas", headers=H)
    passo("A tua chave de administração funciona", bool(r) and r.status_code == 200, r and str(r.status_code))
    if not r or r.status_code != 200:
        print("\nSem chave válida não dá para continuar.")
        return 1

    r = pedir("POST", "/api/diagnostico", headers=H)
    if r is not None and r.status_code == 200:
        d = r.json()
        passo("Base de dados", d["base_de_dados"])
        passo("IA (chave, crédito e modelo)", d["ia"]["ok"], d["ia"]["mensagem"])
    else:
        passo("Diagnóstico", False, r and r.text[:100])

    r = pedir("POST", "/api/empresas", headers=H, json={
        "nome": "ZZ Teste automático", "humano_ativo": True,
        "system_prompt": "ZZ Teste vende telemóveis. Produtos:\n- Telemóvel Lite 5G: 128 GB, câmara de 50 MP, garantia de 1 ano.\nHorário: segunda a sábado, 8h às 18h."})
    ok = bool(r) and r.status_code == 201
    passo("Registar empresa de teste", ok, r and r.text[:140])
    if not ok:
        return 1
    emp = r.json()
    r = pedir("GET", emp["chat_url"])
    passo("Página do chat abre", bool(r) and r.status_code == 200, r and str(r.status_code))

    sessao, url = uuid.uuid4().hex, f"/chat/{emp['slug']}/mensagem"
    r = pedir("POST", url, json={"sessao": sessao, "texto": "Olá, o telemóvel tem quantos GB?"})
    resp = (r.json().get("mensagens") if r is not None and r.status_code == 200 else None) or []
    passo("O bot responde a uma pergunta", bool(resp), resp[0]["conteudo"][:100] if resp else (r and r.text[:100]))
    r = pedir("POST", url, json={"sessao": sessao, "texto": "Quero falar com uma pessoa"})
    passo("Pedido de pessoa passa a conversa a humano", bool(r) and r.status_code == 200 and r.json().get("humano") is True)
    r = pedir("POST", url, json={"sessao": sessao, "texto": "Estás aí?"})
    passo("Com humano ativo, a IA fica calada", bool(r) and r.status_code == 200 and r.json().get("mensagens") == [])
    r = pedir("GET", "/api/estatisticas", headers=H)
    passo("Estatísticas", bool(r) and r.status_code == 200 and any(e["empresa"] == emp["nome"] for e in r.json()["empresas"]))
    r = pedir("GET", "/nao-existe")
    passo("Páginas inexistentes mostram aviso (não ecrã vazio)", bool(r) and r.status_code == 404 and "MacTech" in r.text)
    pedir("POST", f"/api/empresas/{emp['id']}/estado", headers=H, json={"estado": "suspenso"})
    print("\nA empresa 'ZZ Teste automático' ficou suspensa; podes ignorá-la.")
    print("TUDO OK" if not falhas else "PROBLEMAS EM: " + "; ".join(falhas))
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
