# ARCHITECTURE — come è fatta

> Stato: bozza del 01/11/2026. Il perché sta in [PRODUCT.md](PRODUCT.md).
> Descrive l'architettura **di arrivo**; dove il codice di oggi è diverso c'è la sezione "Da oggi ad arrivo".
> Le voci marcate **(scelta di Claude)** vanno confermate.

## Vista d'insieme

```
  Ale (voce/Telegram) ──▶ Hermes (~/.hermes)
                              │  tool MCP: buywatcher / buywatcher_write
                              ▼
                       MCPJungle  mcp.intecha.dev ──▶ mcp-backend (intecha-mcp)
                                                          │  HTTP rete Docker interna, token di servizio
                                                          ▼
  Browser / telefono ──Authentik──▶  BuyWatcher  (FastAPI + React buildato, 1 processo)
                                        │
                                        ├── SQLite  /data/subito.db   (topic, annunci, valutazioni, ricerche)
                                        ├── worker  1 thread + scheduler (raccolta e valutazione)
                                        ├── fonti   Subito (HTML) · Vinted (catalogo anonimo) · eBay (Browse API)
                                        └── LLM     endpoint compatibile OpenAI (Ollama su RTX 3060, o remoto)
```

Un solo container, come le app sorelle. FastAPI serve l'API, la build statica del frontend e possiede il worker.

## Da oggi ad arrivo

| Aspetto | Oggi (`fac8798`) | Arrivo |
|---|---|---|
| Struttura backend | moduli piatti in `webapp/`, `app.py` fa da router e da servizio | package `backend/app/` a strati `routers → services → repositories` |
| Accesso ai dati | `sqlite3` grezzo, due moduli (`storage.py` legacy, `repository.py`) | SQLAlchemy 2 tipizzato, un solo modulo di repository per entità |
| Schema | `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE` a mano; topic e annunci come JSON in `body` | Alembic; colonne vere per ciò che si filtra, JSON solo per l'analisi |
| API | `/api/...`, errori stringa, nessun contratto | `/api/v1`, Problem Details, `openapi.json` committato |
| Legacy | rotte `/channels`, `/feedback`, `/favorites`, `/deals` copiate dentro l'app | rimosse dopo il passaggio dell'MCP ai topic |
| MCP | solo canali legacy (`subitowatch`) | server `buywatcher` / `buywatcher_write` sui topic |
| Auth | solo forward-auth Authentik; l'MCP entra senza token | JWT Authentik (OIDC) per web e mobile, token di servizio per l'MCP |
| Frontend | un `App.tsx` da 190 righe, `useState` e polling manuale | Mantine + TanStack Query + client generato, pagine separate |
| Tooling | pip, Python 3.11, `unittest` | `uv`, Python 3.13, `pytest` |

**Cosa non cambia**: la logica di dominio (`ai.py`, `scoring.py`, `sources.py`, `personalization.py`,
`images.py`) si sposta nei servizi senza cambiare comportamento. I test esistenti la proteggono e vanno
portati per primi.

## Stack

| Parte | Scelta |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, `pydantic-settings` |
| HTTP verso fonti e LLM | `httpx`; `curl_cffi` solo dove serve l'impronta TLS di un browser (Vinted, Subito) |
| Immagini | Pillow (+ AVIF), normalizzate a JPEG prima dell'LLM |
| Database | SQLite in WAL sul volume `subito-data` — vedi [adr/003](adr/003-sqlite-un-processo.md) **(scelta di Claude)** |
| Frontend | React + TypeScript + Vite, Mantine, TanStack Query, client da OpenAPI (come todo-app) |
| LLM | qualunque endpoint `POST /chat/completions` con `json_schema`; oggi Ollama locale |
| Deploy | Docker, Coolify, Authentik, `subitowatch.intecha.dev` (poi `buywatcher.intecha.dev`) |

## Struttura del repo **(scelta di Claude)**

Stessa forma di todo-app:

```
BuyWatcher/
├── AGENTS.md  CLAUDE.md  README.md  SETUP.md
├── docker-compose.yml  Dockerfile  .env.example
├── backend/
│   ├── pyproject.toml  uv.lock  openapi.json
│   ├── alembic/
│   ├── app/
│   │   ├── main.py            FastAPI, lifespan (DB + worker), monta /api/v1 e la build statica
│   │   ├── config.py          Settings (pydantic-settings), legge le variabili BUYWATCHER_*
│   │   ├── db.py  models.py  schemas.py  errors.py  auth.py
│   │   ├── routers/           topics, listings, runs, profile, sources, health
│   │   ├── services/
│   │   │   ├── topics.py      creazione, modifica, archiviazione, proposta AI
│   │   │   ├── pipeline.py    una esecuzione: raccolta → triage → valutazione → report
│   │   │   ├── evaluation.py  chiave di cache, invalidazione, controllo taglie (ex engine + personalization)
│   │   │   ├── scoring.py     convenienza deterministica (ex scoring.py, invariato)
│   │   │   ├── views.py       consigliati / da verificare / esclusi
│   │   │   ├── ai.py          client LLM, schemi di output (ex ai.py)
│   │   │   └── images.py      download sicuro e normalizzazione foto (ex images.py)
│   │   ├── sources/           base.py (interfaccia + policy), subito.py, vinted.py, ebay.py, manual.py
│   │   ├── worker.py          coda a un thread + scheduler
│   │   └── repositories/
│   ├── scripts/eval_ai/       set etichettato e misura della qualità (vedi sotto)
│   └── tests/
├── frontend/                  build in backend/app/static (non committata)
└── docs/
```

## La pipeline di un'esecuzione

Un'esecuzione (`run`) riguarda un topic. Parte a mano (`refresh`), dallo scheduler, o solo per rivalutare
(`evaluate`, senza raccolta). Le regole sono quelle già in produzione:

1. **Raccolta**, per ogni fonte attiva del topic e ogni parola chiave: `search` (una pagina) → `enrich`
   → validazione con `ListingInput`. Al massimo `BUYWATCHER_MAX_DETAILS_PER_SOURCE` annunci per fonte.
   Pausa di 1 s tra parole chiave (2 s su Vinted). Un 403/429 ferma la fonte, non si riprova.
2. **Dedup**: un annuncio è unico per URL in tutto il DB; lo stesso annuncio può stare in più topic.
   Se il contenuto cambia (hash diverso) si salva uno **snapshot**: da qui viene lo storico prezzi.
3. **Controllo taglie** (deterministico): se il testo dichiara una taglia incompatibile con il profilo,
   l'annuncio è escluso senza chiamare l'LLM.
4. **Triage testuale** (LLM, economico): `exclude` o `inspect`. Gli esclusi non consumano analisi foto.
5. **Valutazione** (LLM con visione): output validato contro lo schema `Analysis`; le osservazioni sulle foto
   devono citare l'indice di una foto davvero allegata. Al massimo `BUYWATCHER_MAX_AI_PER_RUN` per esecuzione di giorno,
   senza limite nella finestra notturna, prima gli annunci pubblicati più di recente.
6. **Report** per fonte e per valutazione, salvato sull'esecuzione: `success`, `partial`, `failed`.

**Cache e invalidazione.** Ogni valutazione ha una chiave = hash del contenuto dell'annuncio + hash di
(topic effettivo, firma del modello, politica della fonte, profilo taglie se usato). Se la chiave cambia la
valutazione torna `pending`; non si ricalcola nulla senza un'esecuzione esplicita. Questo meccanismo resta
identico.

**Viste** (calcolate in `services/views.py`, non salvate):

| Vista | Regola |
|---|---|
| Esclusi | requisito violato, oppure pertinenza sotto la soglia del topic |
| Da verificare | non ancora valutato, requisiti non verificati, parti mancanti, condizioni ignote, rischi, confidenza < 70, non disponibile, visto l'ultima volta oltre 72 h fa |
| Consigliati | il resto |
| Preferiti / Scartati | per verdetto di Ale, indipendenti dalle viste |

**Convenienza** (`scoring.py`, deterministica): serve il costo totale noto (prezzo + spedizione + commissioni),
prezzo fisso, modello identificato, condizioni note, nessuna parte mancante e almeno 3 offerte equivalenti
indipendenti con confidenza ≥ 70. Riferimento = mediana; punteggio = 50 + % di risparmio, tra 0 e 100;
rischi o confidenza bassa lo limitano a 59; "potenziale affare" da 75. Le fonti con `pricing=false`
(eBay, Vinted) non entrano nei confronti. Soglie non calibrate: vedi "Misurare l'AI".

## Modello dati

**(scelta di Claude)** Oggi topic e annunci sono un JSON in `body`. All'arrivo i campi su cui si filtra o
si ordina diventano colonne; restano JSON solo le liste del topic e l'analisi (già validata da Pydantic).

### `topic`

| Campo | Tipo | Note |
|---|---|---|
| id | int PK | |
| version | int | concorrenza ottimistica (`If-Match`); sostituisce `revision` |
| name | str | unico tra i non archiviati |
| need | text | il bisogno in parole di Ale |
| keywords, requirements, preferences, exclusions | JSON list[str] | |
| accepted_defects | text | |
| budget | decimal? | EUR, costo totale |
| location | str | per Subito: nome del comune |
| shipping_allowed | bool | |
| sources | JSON list[str] | `manual`, `subito`, `vinted`, `ebay` |
| relevance_threshold | int | 0-100, default 70 |
| interval_hours | int | 6-168, default 24 |
| profile_scope | enum | `none`, `footwear`, `clothing`, `fashion` |
| active | bool | lo scheduler lo considera |
| archived_at | datetime? | i topic non si cancellano, si archiviano |
| legacy_channel_id | int? unico | provenienza dall'import dei canali |
| created_at, updated_at | datetime | |

### `listing` e `listing_snapshot`

| Campo | Tipo | Note |
|---|---|---|
| id | int PK | |
| url | str unico | identità globale dell'annuncio |
| source | enum | |
| external_id | str? | |
| title, description | text | |
| price, shipping_cost, fees | decimal? | `null` = non noto, `0` = gratis |
| currency | str | |
| town, seller | str | |
| is_shop | bool | |
| buying_format | enum | `fixed`, `auction`, `unknown` |
| availability | enum | `active`, `unavailable`, `unknown` |
| images | JSON list[str] | URL pubblici |
| published_at | datetime? | |
| content_hash | str | |
| first_seen, last_seen | datetime | |

`listing_snapshot` (listing_id, content_hash, body JSON, captured_at) conserva ogni versione diversa:
lo storico prezzi è una query qui sopra.

### `topic_listing` (ex `bw_matches` + `bw_feedback`)

| Campo | Tipo | Note |
|---|---|---|
| topic_id, listing_id | PK composta | |
| state | enum | `pending`, `evaluating`, `evaluated`, `excluded`, `error` |
| analysis | JSON? | schema `Analysis`, con `schema_version` |
| evaluation_key | str? | chiave di cache |
| error | str? | messaggio pubblico, mai il corpo della risposta del provider |
| verdict | enum? | `like`, `dislike`; il feedback entra qui invece che in una tabella a parte |
| verdict_at | datetime? | |
| first_seen, last_seen, evaluated_at | datetime | |

### `run` e `run_source`

`run`: id, topic_id, kind (`collect`, `evaluate`), trigger (`manual`, `scheduler`, `mcp`), state, started_at,
finished_at, contatori della valutazione. Indice unico parziale: una sola esecuzione `running` per topic.

`run_source`: run_id, source, state, found, truncated, errors JSON. Oggi tutto questo è un JSON in `report`;
in tabella si può chiedere "da quanti giorni Vinted fallisce".

### `profile`

Una riga sola (id = 1): `shoe_size_eu`, `clothing_sizes` JSON, `version`, `updated_at`.

## Fonti

Ogni connettore implementa la stessa interfaccia in `sources/base.py`:

```python
class Source(Protocol):
    id: str
    policy: SourcePolicy          # enabled, automatic, analysis, pricing, policy_url
    def search(self, keyword: str, topic: Topic) -> list[RawItem]: ...
    def enrich(self, raw: RawItem) -> ListingInput: ...
```

| Fonte | enabled | analysis | pricing | Note |
|---|---|---|---|---|
| manual | sempre | sì | sì | l'URL dell'annuncio non viene mai visitato |
| subito | `BUYWATCHER_ENABLE_SUBITO` | sì | sì | provincia di Verona, una pagina |
| vinted | `BUYWATCHER_ENABLE_VINTED` | sì | no | sessione anonima, una foto, spedizione ignota |
| ebay | credenziali presenti | `EBAY_ANALYSIS_ALLOWED` | no | Browse API, dati mostrati per 6 h al massimo |
| facebook | no | no | no | solo link di ricerca (`/topics/{id}/marketplaces`) |

Regole fisse: niente login automatici, niente CAPTCHA, niente proxy a rotazione. Un cambio di struttura
dell'HTML è un **errore**, non una ricerca vuota. I connettori si testano su risposte registrate in
`tests/fixtures/sources/`, mai contro i siti veri in CI.

## LLM

- Client unico (`services/ai.py`) verso un endpoint compatibile OpenAI, `temperature=0`, output
  `json_schema` validato anche con Pydantic. Tre chiamate: `plan` (bisogno → topic), `triage`, `evaluate`.
- La firma del modello (`VERSION` del prompt + URL + modelli) entra nella chiave di cache: cambiare modello
  o prompt rimette le valutazioni in `pending`.
- **Foto**: scaricate dal backend solo da URL pubblici, IP fissato dopo il controllo DNS, redirect ricontrollati,
  massimo 6 foto da 4 MB, 20 megapixel, convertite in JPEG ≤ 1600 px e mandate in base64. Questo resta identico.
- L'LLM **non produce prezzi**: costi e convenienza vengono solo dai dati della fonte e da `scoring.py`.
- Senza LLM configurato l'app funziona: raccoglie e lascia tutto in "Da verificare".

### Misurare l'AI **(scelta di Claude)**

`backend/scripts/eval_ai/`:

1. `export_cases`: dai verdetti di Ale (`topic_listing.verdict`) e da casi scritti a mano costruisce
   `cases.jsonl` (topic, annuncio, foto, giudizio atteso: consigliato / da verificare / escluso).
2. `run_eval --model ...`: rivaluta ogni caso e scrive un report: consigliati corretti, annunci validi finiti
   negli esclusi, errori di schema, tempo e token per caso.
3. Il report entra nel PR quando si cambia prompt, modello o soglie.

## Worker e scheduler

- **Un solo processo uvicorn, un solo thread di lavoro** (`ThreadPoolExecutor(max_workers=1)`): le fonti
  vanno distanziate comunque e SQLite ha un solo scrittore. Vedi [adr/003](adr/003-sqlite-un-processo.md).
- Lo scheduler lavora solo nella **finestra notturna** (`BUYWATCHER_NIGHT_START`–`END`, predefinito 2–7,
  `BUYWATCHER_TIMEZONE` Europe/Rome): ogni 60 s accoda una ricerca per i topic `active` non ancora cercati
  in questa notte (`interval_hours` oltre 24 salta notti), poi esecuzioni di sola valutazione finché la coda
  scende. Di notte il limite `BUYWATCHER_MAX_AI_PER_RUN` non vale (la GPU è libera); di giorno sì.
  Salvare un topic non avvia ricerche nascoste.
- **Riavvio**: le esecuzioni `running` diventano `interrupted`, le valutazioni `evaluating` tornano `pending`.
  Non si riprendono a metà.
- La UI non fa polling a tempo fisso: TanStack Query interroga `GET /runs/{id}` solo mentre l'esecuzione è attiva.

## Principi del backend

Gli stessi di todo-app (vedi `todo-app/docs/ARCHITECTURE.md` e la sua adr/005), applicati qui:

- **Strati**: i router non toccano la sessione; mai modelli ORM in risposta, solo schemi `XRead`/`XCreate`/`XUpdate`.
- **API versionata** sotto `/api/v1`, `operation_id` stabili, `openapi.json` committato e confrontato in CI.
- **Errori Problem Details** (RFC 9457) con `code` stabile: `topic_not_found`, `run_in_progress`,
  `source_not_manual`, `ai_not_configured`, `version_mismatch`...
- **Idempotenza**: `Idempotency-Key` sulle `POST` (Hermes che ripete `create_topic` non crea un doppione).
- **Concorrenza ottimistica**: `If-Match` sulle `PATCH` di topic e profilo.
- **Paginazione a cursore** sugli annunci di un topic e sulle esecuzioni.
- **Date** in UTC, ISO 8601 con fuso; la UI mostra `Europe/Rome`.
- **Operatività**: `/health` (vivo) e `/ready` (DB raggiungibile), log JSON con `run_id` e `topic_id`,
  limiti di frequenza su `refresh`, `evaluate` e `plan`.
- **Sicurezza**: nessun fetch di URL inseriti dall'utente a parte le foto (con le regole sopra),
  segreti solo in `.env`, nessun corpo di risposta del provider nei messaggi d'errore.

## API

REST sotto `/api/v1`. Documentazione su `/api/v1/docs`.

```
GET    /config                                    AI, visione, catalogo fonti
GET    /topics?archived=                          con contatori per vista e ultima esecuzione
POST   /topics                                    GET /topics/{id}    PATCH /topics/{id} (If-Match)
POST   /topics/{id}/archive | restore
POST   /topic-plans          {need}               proposta AI, non salva nulla
GET    /topics/{id}/listings?view=&verdict=&q=&cursor=
POST   /topics/{id}/listings                      inserimento manuale (solo source=manual)
GET    /topics/{id}/listings/{listing_id}         annuncio + analisi + raccomandazione
PUT    /topics/{id}/listings/{listing_id}/verdict {verdict: like|dislike|null}
GET    /listings/{id}/history                     storico prezzi
POST   /topics/{id}/runs     {kind: collect|evaluate, max_evaluations?}   → 202 {run_id}
GET    /topics/{id}/runs?cursor=                  GET /runs/{id}
GET    /topics/{id}/marketplaces                  link di ricerca esterni
GET    /profile                                   PATCH /profile (If-Match)
GET    /sources                                   stato e politica di ogni fonte, ultimo errore
```

Nessun `DELETE` sui topic: si archiviano. Le rotte di oggi (`/api/topics/...`) restano come alias fino al
cambio del frontend, poi si tolgono.

## MCP: tutto interrogabile da un LLM

Due server in `intecha-mcp`, con le sue convenzioni (inglese, `verb_object`, verbi della lista chiusa).
Sostituiscono `subitowatch` e `subitowatch_write`, che vengono tolti nello stesso cambio insieme a
`tests/tool_names.txt` e ai client che li usano (Hermes, n8n).

| Server | Tool |
|---|---|
| `buywatcher` (lettura) | `list_topics`, `get_topic`, `list_listings`, `get_listing`, `get_price_history`, `list_runs`, `get_run`, `get_profile`, `list_sources`, `list_marketplaces` |
| `buywatcher_write` | `analyze_need` (proposta di topic da una frase), `create_topic`, `update_topic`, `archive_topic`, `restore_topic`, `refresh_topic` (raccolta + valutazione), `analyze_listings` (solo valutazione), `add_listing` (manuale), `set_favorite`, `discard_listing`, `restore_listing`, `update_profile` |

- Le descrizioni insegnano a Hermes: prima `analyze_need` e poi `create_topic` con la proposta rivista da Ale;
  cercare tra i topic esistenti prima di crearne uno; `refresh_topic` restituisce un `run_id` da seguire con `get_run`.
- `list_listings` di default restituisce solo i consigliati, con motivo e costo totale: è la risposta a
  "c'è qualcosa di buono per la GPU?".
- **Parità** con un test, come in todo-app: gli `operation_id` di `openapi.json` contro i tool esposti.

## Autenticazione

Come todo-app (adr/005 di quel repo):

- **Web e mobile**: Authentik come provider OIDC, Authorization Code + PKCE, `Authorization: Bearer`.
  Il backend valida firma (JWKS), `iss`, `aud`, scadenza.
- **MCP**: token di servizio (client credentials) con scope `buywatcher:read` e `buywatcher:write`.
  Oggi l'MCP chiama `http://subitowatch-api:8000` senza credenziali: va chiuso.
- `AUTH_DISABLED=true` solo con `ENV=dev`.

## Migrazione dei dati

Il DB in produzione è `/data/subito.db` sul volume `subito-data`, con le tabelle legacy e le `bw_*`.

1. **Backup** coerente (`sqlite3 .backup`) prima di ogni passo.
2. **Baseline Alembic**: una migrazione `0001` descrive lo schema di oggi; sul DB esistente si fa `alembic stamp 0001`.
3. **`0002`**: crea le tabelle nuove, copia da `bw_*` spacchettando i JSON in colonne, unisce `bw_feedback`
   in `topic_listing.verdict`, porta il `report` delle esecuzioni in `run_source`. Le tabelle `bw_*` restano.
4. **`0003`**, solo dopo il passaggio dell'MCP e qualche giorno di uso: elimina le tabelle legacy
   (`channels`, `channel_listings`, `feedback`, `deals`) e le `bw_*`.

Il volume e il percorso del DB non cambiano. Mai `docker compose down -v`.

## Configurazione

Restano le variabili di oggi (vedi SETUP.md), lette da `Settings`:

| Variabile | Default | Cosa fa |
|---|---|---|
| `BUYWATCHER_DB` | `/data/subito.db` | |
| `BUYWATCHER_AI_BASE_URL`, `_MODEL`, `_API_KEY`, `_TIMEOUT`, `_REASONING_EFFORT` | — / 120 | LLM testuale |
| `BUYWATCHER_VISION_MODEL` | — | senza, niente analisi foto |
| `BUYWATCHER_MAX_AI_PER_RUN` | 40 | |
| `BUYWATCHER_MAX_DETAILS_PER_SOURCE` | 30 | |
| `BUYWATCHER_ENABLE_SUBITO`, `BUYWATCHER_ENABLE_VINTED` | false | attivazione esplicita |
| `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `EBAY_ANALYSIS_ALLOWED` | — / false | |
| `AUTHENTIK_ISSUER`, `AUTHENTIK_AUDIENCE` | — | nuove, per i JWT |
| `ENV`, `AUTH_DISABLED` | `prod` / false | |

## Test

- `pytest` al posto di `unittest`; le 676 righe di test di oggi si portano per primi, senza cambiarne il senso.
- Ogni connettore: test su fixture registrate (risposta HTML/JSON vera, anonimizzata).
- LLM: provider finto nei test; la qualità vera si misura con `scripts/eval_ai`, non in CI.
- Contratto: snapshot di `openapi.json`.
- Frontend: `tsc --noEmit`, build, vitest sui pezzi con logica (filtri delle viste, formattazione dei costi).

## Deploy

App Coolify dal repo GitHub, branch `main`, volume `subito-data` montato su `/data`, porta interna 8000,
porta host `127.0.0.1:8081`, Authentik davanti. Un solo worker uvicorn; `stop_grace_period: 3m` per lasciar
finire una valutazione in corso. Healthcheck `python /app/healthcheck.py`.
