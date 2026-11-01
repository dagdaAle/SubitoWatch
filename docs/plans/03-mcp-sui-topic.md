# MCP sui topic — piano di implementazione

> **Per agenti:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata) oppure
> superpowers:executing-plans. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** server `buywatcher` e `buywatcher_write` in `intecha-mcp` al posto di `subitowatch`, poi via il legacy
([adr/006](../adr/006-api-unica-e-mcp-sui-topic.md), [adr/007](../adr/007-via-i-canali-legacy.md)).

**Dipende da:** [02-backend](02-backend.md) (API v1, auth, `openapi.json`). Lavoro su due repo: un branch e una PR per repo.

## intecha-mcp

- [ ] `servers/buywatcher.py`: tool di ARCHITECTURE.md (sezione MCP), convenzioni del README (inglese, `verb_object`, lista chiusa dei verbi, errori `isError`).
- [ ] Token di servizio (client credentials Authentik) in `.env` di mcp-backend; `BUYWATCHER_URL` al posto di `SUBITOWATCH_URL`.
- [ ] Test di parità: `operation_id` di `openapi.json` di BuyWatcher contro i tool esposti, con elenco di esclusioni motivate.
- [ ] Descrizioni che insegnano a Hermes: `analyze_need` prima di `create_topic`, cercare topic esistenti, seguire `run_id` con `get_run`.
- [ ] Togliere `servers/subitowatch.py`; aggiornare `app.py` (percorsi `/buywatcher/read/mcp`, `/buywatcher/write/mcp`) e `tests/tool_names.txt`.
- [ ] Ri-registrare i server in MCPJungle; redeploy mcp-backend.

## Client

- [ ] Hermes: cercare in `~/.hermes` (skill `buywatcher-source-connector` compresa) i nomi `subitowatch` e aggiornarli.
- [ ] n8n: cercare workflow che chiamano `subitowatch`.
- [ ] Prova reale: Hermes crea un topic da una frase, avvia la ricerca, riassume i consigliati.

## Legacy

- [ ] BuyWatcher: togliere rotte `/channels`, `/feedback`, `/favorites`, `/deals` e moduli `legacy.py`, `storage.py`, `scraper.py`
      (lo scraper Subito vive in `sources/subito.py`).
- [ ] Dopo almeno una settimana senza chiamate legacy nei log: backup + migrazione `0003` che elimina le tabelle legacy e le `bw_*`.

## Fatto quando

Hermes lavora solo sui topic, nessun tool `subitowatch` registrato, tabelle legacy eliminate con backup conservato.
