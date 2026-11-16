Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Configurazione

Le variabili si leggono con `os.getenv`. Il server **non carica `.env` da solo**: in Docker lo passa Compose (`env_file`), in Coolify le variabili dell'app. Modello: `.env.example` nel repo. Segreti solo sul server (Coolify), mai nel repo né nel frontend.

## Variabili

| Variabile | Default | A cosa serve |
|---|---|---|
| `BUYWATCHER_DB` | — | override del percorso DB |
| `SUBITO_DB` | `/data/subito.db` (Dockerfile) | percorso DB storico, usato se manca il precedente |
| `BUYWATCHER_AI_BASE_URL` | — | URL base del provider compatibile OpenAI, fino a `/v1` |
| `BUYWATCHER_AI_MODEL` | — | modello testuale (plan, triage, valutazione) |
| `BUYWATCHER_AI_API_KEY` | — | chiave del provider, vuota per Ollama locale. Segreto: Vaultwarden → DA VERIFICARE |
| `BUYWATCHER_AI_TIMEOUT` | 120 | timeout inferenza in secondi (30–600) |
| `BUYWATCHER_AI_REASONING_EFFORT` | — | `none` spegne il ragionamento esteso sui modelli compatibili |
| `BUYWATCHER_VISION_MODEL` | — | modello multimodale. Vuoto = niente analisi foto |
| `BUYWATCHER_MAX_AI_PER_RUN` | 40 | valutazioni massime per run di giorno |
| `BUYWATCHER_MAX_DETAILS_PER_SOURCE` | 30 | annunci arricchiti per fonte e run |
| `BUYWATCHER_NIGHT_START`, `BUYWATCHER_NIGHT_END` | 2, 7 | finestra notturna dello scheduler |
| `BUYWATCHER_TIMEZONE` | Europe/Rome | fuso della finestra notturna |
| `BUYWATCHER_ENABLE_SUBITO` | false | accende il connettore Subito |
| `BUYWATCHER_ENABLE_VINTED` | false | accende il connettore Vinted |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | — | keyset Production eBay. Con entrambi la fonte è attiva. Segreto: Vaultwarden → DA VERIFICARE |
| `EBAY_ANALYSIS_ALLOWED` | false | permette di mandare gli annunci eBay all'LLM |
| `EBAY_VERIFICATION_TOKEN` | — | token per Marketplace Account Deletion (32–80 caratteri). Segreto |
| `EBAY_DELETION_ENDPOINT` | — | URL pubblico esatto registrato su eBay. Entrambe vuote → endpoint 404 |

Valori effettivi in produzione: DA VERIFICARE in Coolify.

## Servizi esterni

| Servizio | Uso | Note |
|---|---|---|
| LLM compatibile OpenAI | plan, triage, valutazione | richiede `POST /chat/completions`, `json_schema`, `json_object`, immagini base64. Oggi Ollama sul server, `buywatcher-vision-8b` |
| Subito | HTML pubblico | provincia di Verona, una pagina per parola chiave |
| Vinted | catalogo anonimo (`access_token_web`, `X-Anon-Id`) | una foto, spedizione ignota, 403/429 ferma la fonte. Vietato dai termini: uso a rischio di Ale |
| eBay | Browse API `EBAY_IT`, OAuth client credentials | annunci isolati in UI, niente confronti di prezzo |
| Facebook Marketplace | solo link | nessuna raccolta |
| Wallapop, Astrosell | catalogo, non attivi | branch `feat/wallapop` non mergiato |
| Authentik | forward-auth | |
| intecha-mcp / MCPJungle | client MCP | |

## Dipendenze principali

Backend (`backend/pyproject.toml`, lock `uv.lock`): fastapi 0.115.6, uvicorn 0.34.0, pydantic 2.12.5, httpx 0.28.1, curl_cffi 0.7.4, Pillow 13.0.0, alembic 1.16.5. Dev: pytest.

Frontend (`frontend/package.json`): react 18.3, vite 8, typescript 7.

## Politica per fonte

Ogni fonte dichiara `enabled`, `automatic`, `analysis`, `pricing` (`sources/__init__.py`, `catalog()`). Solo `manual` e `subito` hanno `pricing=true`, quindi solo loro entrano nei confronti di convenienza.
