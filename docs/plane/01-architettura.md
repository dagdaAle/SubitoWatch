Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Architettura

Questa pagina descrive il codice **di oggi**. L'architettura di arrivo (strati completi, SQLAlchemy, JWT, MCP sui topic) è in `docs/ARCHITECTURE.md` e nei piani `docs/plans/01..05`.

## C4 livello 1 — contesto

```
   Ale (browser / telefono)            Hermes (Telegram, voce)
            │                                   │ tool MCP subitowatch__*
            │ HTTPS                             ▼
            ▼                          MCPJungle mcp.intecha.dev
   Authentik (forward-auth)                     │ rete Docker interna, senza token
            │                                   ▼
            └────────────▶  BuyWatcher  ◀── mcp-backend (intecha-mcp)
                               │
           ┌───────────────────┼─────────────────────┬──────────────┐
           ▼                   ▼                     ▼              ▼
     Subito (HTML)    Vinted (catalogo anonimo)  eBay Browse API   LLM compatibile OpenAI
                                                                    (Ollama sul server)
```

eBay chiama anche BuyWatcher: `/ebay/account-deletion` è pubblico, escluso dal forward-auth.

## C4 livello 2 — container

```
 container subitowatch (immagine buywatcher:latest), 1 processo uvicorn, 1 worker
 ┌────────────────────────────────────────────────────────────────────┐
 │ FastAPI app.main                                                   │
 │  ├─ /api/v1/*  (e alias /api/*)      API topic, annunci, run       │
 │  ├─ /channels /feedback /favorites /deals   rotte legacy per l'MCP │
 │  ├─ /health  /ebay/account-deletion                                │
 │  └─ /        build statica React (app/static)                      │
 │                                                                    │
 │ services/engine.Worker                                             │
 │  ├─ ThreadPoolExecutor(max_workers=1)   coda dei run               │
 │  └─ scheduler (ogni 60 s, solo nella finestra notturna)            │
 │                                                                    │
 │ services: ai · scoring · images · personalization                  │
 │ sources:  manual · subito · vinted · ebay (+ link esterni)         │
 │ repositories: topics (bw_*) · legacy_storage (tabelle SubitoWatch) │
 └───────────────┬────────────────────────────────────────────────────┘
                 ▼
         SQLite /data/subito.db  (volume subito-data, WAL)
```

## Componenti

| Modulo | Ruolo |
|---|---|
| `app/main.py` | router, lifespan (DB + worker), monta API, legacy e statici |
| `app/legacy.py` | rotte SubitoWatch tenute per l'MCP. Nessuno scheduler legacy |
| `services/engine.py` | run, coda, scheduler notturno, chiave di cache |
| `services/ai.py` | client LLM: `plan` (proposta topic), `triage`, `evaluate` |
| `services/scoring.py` | convenienza deterministica |
| `services/images.py` | download sicuro e normalizzazione delle foto |
| `services/personalization.py` | controllo taglie dal profilo |
| `sources/` | catalogo fonti con politica, connettori, link di ricerca esterni |
| `repositories/topics.py` | accesso a `bw_*`, migrazione dei canali legacy, recupero al riavvio |

La divisione `routers → services → repositories` è a metà: router ancora in `main.py` (piano 02).

## Flusso principale: un run

1. Parte da `refresh` (raccolta + valutazione), da `evaluate` (solo valutazione) o dallo scheduler.
2. **Raccolta**: per ogni fonte attiva del topic e ogni parola chiave, una pagina. Massimo `BUYWATCHER_MAX_DETAILS_PER_SOURCE` annunci per fonte. Un 403/429 ferma la fonte.
3. **Dedup**: un annuncio è unico per URL. Se il contenuto cambia si salva uno snapshot (storico prezzi).
4. **Controllo taglie** deterministico: taglia incompatibile dichiarata nel testo → escluso senza LLM.
5. **Triage** LLM sul testo: `exclude` o `inspect`.
6. **Valutazione** LLM con foto (fino a 6). Output validato contro lo schema. Di giorno al massimo `BUYWATCHER_MAX_AI_PER_RUN`, prima i più recenti.
7. **Report** per fonte salvato sul run: `success`, `partial`, `failed`.

Le viste (consigliati, da verificare, esclusi) si calcolano a ogni lettura, non si salvano.

## Scheduler

Lavora solo nella finestra notturna (default 2–7, Europe/Rome). Ogni 60 s accoda una ricerca per i topic attivi non ancora cercati quella notte, poi run di sola valutazione finché la coda scende. Di notte il limite per run è 1000. Salvare un topic non avvia ricerche.

## Cache delle valutazioni

Chiave = hash del contenuto dell'annuncio + hash di topic effettivo, firma del modello, politica della fonte e profilo taglie se usato. Se la chiave cambia la valutazione torna `pending`. Non si ricalcola nulla senza un run esplicito.
