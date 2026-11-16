Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# API e tool MCP

## Contratto

- API sotto `/api/v1`. Alias `/api` non versionato per il frontend di oggi, fuori dallo schema, da togliere col piano 04.
- OpenAPI committato in `backend/openapi.json` (rigenerato da `app/export_openapi.py`). Docs FastAPI su `/docs`.
- `operation_id` = nome della funzione: nomi stabili per client generati e parità con l'MCP.
- Errori **Problem Details** (RFC 9457) con `code` stabile: `topic_not_found`, `run_in_progress`, `run_not_found`, `version_mismatch`, `source_not_manual`, `listing_source_conflict`, `listing_not_in_topic`, `ai_unavailable`.
- `If-Match` facoltativo su `PUT /topics/{id}` e `PUT /profile`: se non coincide con `revision` → 412.

## Endpoint (`/api/v1`)

| Metodo | Percorso | Cosa fa |
|---|---|---|
| GET | `/config` | AI e visione configurate, catalogo fonti con politica |
| GET | `/topics` | topic con contatori per vista e ultimo run |
| POST | `/topics` | crea topic (201) |
| PUT | `/topics/{id}` | modifica topic |
| DELETE | `/topics/{id}` | cancella topic e a cascata valutazioni, preferiti, run |
| POST | `/topic-plan` | proposta di topic da un bisogno in frase. Non salva. 503 se l'AI manca |
| POST | `/topics/{id}/refresh` | run raccolta + valutazione (202). Corpo facoltativo `{"max_evaluations": n}` |
| POST | `/topics/{id}/evaluate` | run di sola valutazione dei pending (202) |
| GET | `/topics/{id}/runs` | run del topic |
| GET | `/runs/{id}` | stato e report di un run |
| POST | `/topics/{id}/listings` | inserimento manuale, solo `source=manual` |
| GET | `/topics/{id}/listings` | annunci del topic con analisi e vista |
| GET | `/listings/{id}/history` | storico prezzi dagli snapshot |
| POST | `/topics/{id}/listings/{listing_id}/feedback` | preferito / scarto |
| GET | `/topics/{id}/marketplaces` | link di ricerca Vinted, eBay, Facebook. Nessuna richiesta esterna |
| GET / PUT | `/profile` | profilo taglie |

## Fuori da `/api`

| Metodo | Percorso | Note |
|---|---|---|
| GET | `/health` | `SELECT` su `bw_topics`, restituisce `ok`, `app`, `ai_configured` |
| GET | `/ebay/account-deletion?challenge_code=` | risposta SHA-256 per eBay. **Pubblico**, escluso da Authentik |
| POST | `/ebay/account-deletion` | svuota il venditore negli annunci eBay. Firma `X-EBAY-SIGNATURE` **non verificata** |
| — | `/channels`, `/channels/{id}` (GET/POST/PUT/DELETE), `/channels/{id}/refresh`, `/channels/{id}/listings`, `/feedback`, `/favorites`, `/deals` | rotte legacy SubitoWatch, solo per l'MCP |

## Auth

- Nessun login interno. Il browser passa da **Authentik forward-auth** (gruppo `utenti-app`).
- L'MCP chiama il container dalla rete Docker interna **senza credenziali**. Da chiudere (ADR-006: JWT OIDC + token di servizio).
- Unica eccezione pubblica: `^/ebay/account-deletion$`.

## Tool MCP (gateway `mcp.intecha.dev`, backend `intecha-mcp`)

Oggi lavorano **solo sui canali legacy**, non sui topic.

| Server | Tool |
|---|---|
| `subitowatch` (lettura) | `list_channels`, `list_channel_listings`, `list_favorites` |
| `subitowatch_write` | `create_channel`, `delete_channel`, `refresh_channel`, `discard_listing`, `set_favorite` |

Conseguenza: un canale creato da Hermes non compare in BuyWatcher. `get_deals`/`set_deals` sono stati tolti il 13/10 (`/deals` dava 404).

Previsti (piano 03, ADR-006): server `buywatcher` / `buywatcher_write` sui topic, con test di parità contro `openapi.json`. Il rename rompe Hermes e n8n: vanno aggiornati nello stesso rilascio.
