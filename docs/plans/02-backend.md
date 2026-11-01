# Backend a strati — piano di implementazione

> **Per agenti:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata) oppure
> superpowers:executing-plans. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** portare `webapp/` nella struttura `backend/app/` di [ARCHITECTURE.md](../ARCHITECTURE.md), con Alembic,
`/api/v1` e Problem Details, **senza cambiare il comportamento** della logica di dominio ([adr/002](../adr/002-rifattorizzare-non-riscrivere.md)).

**Stack:** Python 3.13, uv, FastAPI, Pydantic v2, SQLAlchemy 2 (`Mapped[...]`), Alembic, pytest, httpx `TestClient`.

**Dipende da:** [01-consolidare](01-consolidare.md).

## Vincoli globali

- Ogni passo lascia l'app deployabile e i test verdi. Un passo = un commit.
- La logica di `ai.py`, `scoring.py`, `sources.py`, `personalization.py`, `images.py` si sposta, non si riscrive.
  Se un test va cambiato, il cambio è solo di import o di fixture.
- Rotte sotto `/api/v1`, `operation_id` = nome della funzione; le rotte `/api/...` di oggi restano come alias fino alla fase 4.
- Errori `application/problem+json` con `code` stabile.
- Mai modelli ORM in risposta. I router non usano la sessione.

## Passi

- [ ] **Tooling**: `backend/pyproject.toml` con uv, Python 3.13, ruff, pytest. CI: `uv sync`, `uv run pytest`, build frontend, build Docker.
- [ ] **Test portati**: `tests/test_buywatcher.py` → `backend/tests/` con pytest (test da `unittest` girano così come sono). Verde prima di toccare altro.
- [ ] **Spostamento**: `webapp/*.py` → `backend/app/services/` e `backend/app/sources/`; `app.py` → `main.py` + `routers/`. Solo import cambiati.
- [ ] **Settings**: `config.py` con pydantic-settings al posto dei `os.getenv` sparsi; stessi nomi di variabile.
- [ ] **Alembic baseline `0001`**: schema di oggi (legacy + `bw_*`). Test: DB nuovo = DB creato da `init_db` di oggi.
      Script di deploy: `alembic stamp 0001` se le tabelle esistono già, poi `upgrade head`.
- [ ] **Modelli SQLAlchemy + migrazione `0002`**: tabelle di ARCHITECTURE.md, copia da `bw_*` con JSON spacchettati,
      feedback → `topic_listing.verdict`, report → `run_source`. Test di migrazione su una copia anonimizzata del DB.
- [ ] **Repositories** per topic, listing, topic_listing, run, profile; `engine.py` e `app.py` li usano al posto di SQL grezzo.
- [ ] **Servizi**: `views.py` (logica delle viste oggi dentro l'handler `listings`), `topics.py` (archive/restore), `pipeline.py`, `worker.py`.
- [ ] **API v1** come da ARCHITECTURE.md: Problem Details, `If-Match` su topic e profilo, `Idempotency-Key` sulle POST, cursore su annunci ed esecuzioni.
- [ ] **OpenAPI**: `python -m app.export_openapi` scrive `backend/openapi.json`; test snapshot.
- [ ] **Auth**: dependency JWT (JWKS Authentik, `iss`, `aud`, scadenza), scope `buywatcher:read|write`; `AUTH_DISABLED` solo con `ENV=dev`.
- [ ] **Operatività**: `/ready`, log JSON con `run_id`/`topic_id`, limiti di frequenza su runs e topic-plans.
- [ ] **Deploy**: Dockerfile su uv e Python 3.13, `webapp/static` tolto dal repo (build solo nel Dockerfile). Redeploy con backup prima.

## Fatto quando

Produzione su `backend/`, schema in Alembic alla `0002`, `openapi.json` committato, tutti i test vecchi verdi.
