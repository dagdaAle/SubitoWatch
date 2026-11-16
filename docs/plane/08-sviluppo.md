Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Sviluppo locale

## Requisiti

Python 3.13 con **uv** (mai pip globale), Node 22, Docker.

## Setup

```bash
git clone https://github.com/dagdaAle/SubitoWatch.git BuyWatcher
cd BuyWatcher
cp .env.example .env              # provider AI e fonti; mai committare valori reali
cd backend && uv sync
cd ../frontend && npm ci
```

## Comandi

```bash
cd backend && uv run pytest -q                                    # test, senza rete
cd backend && uv run uvicorn app.main:app --port 8081 --reload    # le variabili di .env vanno caricate a mano
cd backend && uv run python -m app.export_openapi                 # rigenera openapi.json
cd frontend && npm run build                                      # tsc + vite, output in backend/app/static (non committato)
cd frontend && npm run dev                                        # Vite con proxy /api e /health verso :8081
docker compose up -d --build                                      # dalla radice; apri http://localhost:8081
```

Mai `docker compose down -v`.

## Test

- `backend/tests/test_buywatcher.py`: 74 test pytest. Coprono migrazioni, contratti, pertinenza, cache, errori, evidenze, confronti, concorrenza, API.
- Dati sintetici e provider AI finto. **Mai** chiamare i marketplace veri nei test o in CI.
- Connettori nuovi: test su risposte registrate (`tests/fixtures/sources/`, previsto).
- CI: GitHub Actions `.github/workflows/checks.yml` su push e PR: `uv sync --frozen`, `pytest`, `npm ci` + build, `docker build`. C'è anche uno snapshot test di `openapi.json`.

## Convenzioni del repo

- Leggere prima `AGENTS.md`, poi `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/adr/`, `docs/plans/`.
- Branch per feature e PR, mai commit diretti su `main`.
- Lingua: UI, documenti e commit in italiano. Codice, API e tool MCP in inglese.
- Le regole di dominio (valutazione, cache, scoring, fonti, taglie, foto) cambiano solo in una PR dedicata.
- L'LLM non produce prezzi né punteggi di convenienza. Dato mancante = `None`, mai 0.
- Foto solo tramite `services/images.py`. Nessun altro fetch di URL forniti dall'utente.
- Errori pubblici senza chiavi, corpi di risposta del provider o dati grezzi.
- Schema DB solo via Alembic. Backup coerente prima di ogni migrazione.
- Ogni nuova operazione API ha il suo tool MCP in `intecha-mcp`, o un'esclusione motivata.
- Segreti solo in `.env`.

## Piani di lavoro

| Piano | Tema | Stato |
|---|---|---|
| 01 | consolidare repo, fonti, dati | checklist aperta nel piano; avanzamento DA VERIFICARE |
| 02 | backend a strati | prima parte fatta (PR #13: `backend/app`, uv, Alembic, `/api/v1`) |
| 03 | MCP sui topic | da fare |
| 04 | frontend (Mantine, TanStack Query) | da fare |
| 05 | qualità AI (`scripts/eval_ai`) | da fare; possibile cambio con PR #19 |
