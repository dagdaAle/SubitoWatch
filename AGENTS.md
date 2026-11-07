# AGENTS.md — BuyWatcher

Radar personale dell'usato di Ale, organizzato per bisogni d'acquisto (topic) con valutazione AI degli annunci.
FastAPI + SQLite + React, un solo container sul server di casa dietro Authentik (`subitowatch.intecha.dev`).
Hermes lo usa via MCP (`intecha-mcp`).

Prima di toccare il codice leggi:
- [docs/PRODUCT.md](docs/PRODUCT.md): perché esiste, obiettivi, non obiettivi, anti-obiettivi, decisioni aperte
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): architettura di arrivo, pipeline, modello dati, API, MCP, migrazione
- [docs/DESIGN.md](docs/DESIGN.md): UI, pagine, stati, accessibilità
- [docs/adr/](docs/adr/): decisioni già prese, da non rimettere in discussione senza motivo nuovo
- [docs/plans/](docs/plans/): piani di implementazione per fase (01 consolidare → 05 qualità AI)
- [SETUP.md](SETUP.md): variabili, fonti e limiti operativi

## Stato

Il codice è in `backend/app/` (package `app`, avviato con `app.main:app`) e il frontend in `frontend/`.
La divisione completa `routers → services → repositories` è in corso: vedi [02-backend](docs/plans/02-backend.md).

## Comandi

```bash
cd backend && uv sync                      # dipendenze (Python 3.13)
cd backend && uv run pytest -q             # test, senza rete
cd backend && uv run uvicorn app.main:app --port 8081 --reload   # variabili da .env caricate a mano
cd frontend && npm ci && npm run build     # build in backend/app/static (non committata)
cd frontend && npm run dev                 # Vite con proxy verso :8081
docker compose up -d --build               # dalla radice; mai `down -v`
```

## Regole

- **Comportamento di dominio**: valutazione, cache, scoring, fonti, taglie e foto non cambiano durante il refactor
  ([adr/002](docs/adr/002-rifattorizzare-non-riscrivere.md)). Un cambio di regola va in una PR sua.
- **Una scheda AI per annuncio** ([adr/010](docs/adr/010-scheda-ai-per-annuncio.md)): il modello compila la `Card`
  (taglia, condizioni, provenienza, stima del nuovo, verdetto). La stima del nuovo si mostra sempre come stima; il
  filtro taglie è deterministico sui campi della scheda. Ciò che non si sa resta `None`/"non noto": mai 0.
- **Fonti** ([adr/005](docs/adr/005-politica-per-fonte.md)): niente login automatizzati, CAPTCHA o proxy a rotazione;
  una pagina per ricerca; 403/429 fermano la fonte. Ogni connettore ha la sua riga di politica e test su risposte registrate.
  **Mai** chiamare i marketplace veri nei test o in CI.
- **Foto**: solo tramite `images.py` (IP pubblico fissato, redirect ricontrollati, limiti di dimensione). Nessun altro fetch
  di URL forniti dall'utente.
- **Errori**: nei messaggi pubblici mai chiavi, corpi di risposta del provider o dati dell'annuncio grezzi.
- **Un solo processo, un solo worker** ([adr/003](docs/adr/003-sqlite-un-processo.md)): niente thread o processi in più
  che scrivono sul DB.
- **Database**: volume `subito-data` e percorso `/data/subito.db` non cambiano. Backup coerente prima di ogni migrazione.
  Dopo il piano 02 lo schema si cambia solo con Alembic.
- **API e MCP**: ogni nuova operazione ha il suo tool in `intecha-mcp` (server `buywatcher` / `buywatcher_write`),
  o un'esclusione motivata ([adr/006](docs/adr/006-api-unica-e-mcp-sui-topic.md)).
- **Topic**: non si cancellano, si archiviano ([adr/009](docs/adr/009-topic-archiviati.md), da quando è implementata).
- **AI**: ogni PR che tocca prompt, schema `Analysis` o soglie allega il report di `scripts/eval_ai` (dal piano 05).
- **Python** con venv/uv, mai pip globale. **Segreti** solo in `.env`, mai nel repo.
- **Git**: branch per feature e PR, mai commit diretti su `main`.
- **Lingua**: UI, documenti e commit in italiano. Codice, nomi di API e tool MCP in inglese.
