# ADR 006 — Una sola API per web, mobile e MCP; l'MCP lavora sui topic

- Data: 01/11/2026
- Stato: proposta (scelta di Claude, da confermare)

## Contesto

Oggi l'MCP (`intecha-mcp/servers/subitowatch.py`) usa le vecchie rotte `/channels`: Hermes crea canali che
BuyWatcher non usa più, e non vede topic, valutazioni né preferiti. L'app non ha autenticazione propria:
il browser passa da Authentik in forward-auth, l'MCP entra dalla rete interna senza credenziali.

## Decisione

Come in todo-app (adr/005 di quel repo):

- un'unica API `/api/v1` con `openapi.json` committato; nessun client privilegiato;
- due server MCP, `buywatcher` e `buywatcher_write`, che coprono ogni operazione dell'API, controllati da un
  test di parità con `openapi.json`; `subitowatch` e `subitowatch_write` si tolgono nello stesso cambio;
- JWT di Authentik (OIDC + PKCE) per web e mobile, token di servizio con scope `buywatcher:read` e
  `buywatcher:write` per l'MCP.

## Perché

- "Tutto interrogabile da un LLM" è un principio di Ale per tutte le app (PRODUCT.md).
- Un'API con contratto evita che UI e MCP divergano di nuovo come è successo con i canali.

## Conseguenze

- Rinominare i tool rompe Hermes e n8n senza errori evidenti: vanno aggiornati nello stesso rilascio.
- Serve un provider OIDC su Authentik per BuyWatcher e un client per l'MCP.
