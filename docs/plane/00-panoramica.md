Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# BuyWatcher — Panoramica

## Scopo

Radar personale dell'usato organizzato per **bisogni d'acquisto** (topic). Un topic dice cosa serve e perché: uso previsto, requisiti, preferenze, esclusioni, difetti accettati, budget, località, fonti. Le parole chiave servono solo a raccogliere i candidati.

L'app raccoglie annunci da più marketplace, li normalizza, conserva storico e prezzi. Un LLM valuta ogni annuncio contro il topic. La convenienza la calcola codice deterministico, non l'LLM.

Il risultato per topic sono tre liste: **consigliati**, **da verificare**, **esclusi**, ognuna con il motivo.

Nasce da SubitoWatch (canali di parole chiave su Subito, Verona). Vedi ADR-000 e ADR-001 in "07 · Decisioni".

## Per chi

| Utente | Uso |
|---|---|
| Ale | crea e rifinisce i topic, legge i consigliati, mette preferiti e scarti. Da Mac e telefono |
| Hermes | via MCP. Oggi vede solo i canali legacy (`subitowatch__*`), non i topic |

App per una persona sola. Niente multi-utente.

## Stato

| Voce | Valore |
|---|---|
| Stato | **produzione** |
| URL | https://subitowatch.intecha.dev (dietro Authentik). Dominio `buywatcher.intecha.dev` previsto, DA VERIFICARE |
| Repo | `dagdaAle/SubitoWatch` (pubblico per scelta), branch `main`. Locale: `~/Progetti/server-apps/BuyWatcher` |
| Versione | backend 3.1.0, frontend 3.0.0 |
| Commit in produzione | DA VERIFICARE (ultimo merge su main: `c7dbbda`, 02/11/2026) |
| Lavori aperti | PR #19 `feat/card-ai`: scheda per annuncio al posto dell'analisi AI (aperta, non mergiata) |

Al 02/11/2026 (todo-app, task 1578): Vinted raccoglie annunci veri, eBay è attivo dopo l'iscrizione a Marketplace Account Deletion, 7 topic attivi.

## Stack

| Parte | Tecnologia |
|---|---|
| Backend | Python 3.13, FastAPI 0.115, Pydantic v2, sqlite3, Alembic, uv |
| HTTP verso fonti | httpx, curl_cffi (impronta TLS del browser per Subito e Vinted) |
| Immagini | Pillow (+ AVIF) |
| Database | SQLite in WAL, `/data/subito.db` sul volume `subito-data` |
| Frontend | React 18 + TypeScript + Vite, un solo `App.tsx` |
| LLM | endpoint compatibile OpenAI. Oggi Ollama sul server, modello vision `buywatcher-vision-8b` (base `qwen3-vl:8b-instruct`) |
| Deploy | Docker, Coolify, Authentik forward-auth |

## Pagine

- 01 · Architettura
- 02 · Modello dati
- 03 · API e tool MCP
- 04 · Configurazione
- 05 · Deploy e operations
- 06 · Runbook
- 07 · Decisioni (ADR)
- 08 · Sviluppo locale

Documenti di dettaglio nel repo: `docs/PRODUCT.md`, `docs/ARCHITECTURE.md` (architettura **di arrivo**), `docs/DESIGN.md`, `docs/adr/`, `docs/plans/`, `SETUP.md`.
