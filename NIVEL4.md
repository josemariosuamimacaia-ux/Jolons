# Nível 4: Bot Corporativo Personalizado (Multi-Atendente + Integração Total)

## O que o Gemini descreveu (fotos)
- **O que faz:** integra o WhatsApp com o sistema de gestão da empresa (CRM, base de stock, ERP). A IA consulta o estado de uma encomenda, emite faturas, faz triagem por departamentos (Vendas, Suporte, Financeiro) e gere vários atendentes humanos no mesmo número.
- **Para quem serve:** bancos, seguradoras, grandes colégios/universidades, distribuidoras, concessionárias de automóveis.
- **Vantagem para a empresa:** substitui uma equipa inteira de call-center e automatiza processos complexos.
- **Preço sugerido:** configuração 500.000 a 1.200.000+ AOA (cerca de 600 a 1.500+ USD); mensalidade/manutenção 150.000 a 300.000 AOA (cerca de 180 a 360 USD).
- **Estratégia:** se o cliente achar o Nível 3 caro, não perdes a venda (descer de nível em vez de perder o cliente).
- (Os valores são sugestões do Gemini: confirma-os com o teu mercado.)

## O que esta versão já faz
| Promessa do Nível 4 | Como está feito |
|---|---|
| Consultar stock | Ferramenta `consultar_stock`: lê o catálogo (`/api/empresas/ID/produtos`) ou pergunta ao ERP |
| Estado da encomenda | `consultar_encomenda`: só responde se o telefone/email do cliente coincidir com o da encomenda (verificado no código, não pela IA) |
| Faturas | `pedir_fatura`: regista o pedido para o Financeiro, ou pede ao ERP da empresa. **Não emite faturas**: em Angola a emissão exige software certificado, por isso quem emite é o ERP da empresa |
| Triagem por departamento | A IA conhece os departamentos e usa `transferir_para_departamento` / `abrir_ticket` |
| Vários atendentes no mesmo número | Cada atendente tem chave própria e entra em `/agente`: vê a fila do seu departamento, assume (só um consegue), responde e devolve à IA |
| Ligação ao CRM/ERP | Um endereço https da empresa recebe pedidos assinados (ver INTEGRACAO.md) |
| Relatórios | Painel: conversas, perguntas sem resposta, tickets abertos, CSV |

## Como ativar numa empresa (painel > "Nível 4")
1. Escolhe a empresa. Adiciona os departamentos (Vendas, Suporte, Financeiro).
2. Cria os atendentes (a chave aparece uma vez: entrega-a ao atendente, que entra em `/agente`).
3. Marca as ferramentas. Sem ERP: importa produtos e encomendas (uma linha cada, separadas por `;`). Com ERP: põe o endereço e o segredo.
4. Testa no chat da empresa: "tem portáteis?", "onde está a encomenda E100? o meu número é 923000000", "quero falar com o financeiro".

## Limites a conhecer
- No **chat web** o telefone/email é o que o cliente escreve (não se pode provar). No **WhatsApp** o número vem da Meta e é fiável. Para dados sensíveis (saldos, contratos) usa só o WhatsApp.
- Empresas com ferramentas recebem a resposta inteira (sem o texto a aparecer aos poucos), porque a IA consulta sistemas antes de responder.
- O limitador de pedidos fica em memória: com vários workers cada um conta à parte.
