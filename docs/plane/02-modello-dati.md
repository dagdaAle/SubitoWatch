Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Modello dati

## Dove stanno i dati

| Cosa | Dove |
|---|---|
| Database | SQLite `/data/subito.db`, modalità WAL |
| Volume | Docker `subito-data` montato su `/data`. **Non rinominare, non cancellare** |
| Override | `BUYWATCHER_DB`, poi `SUBITO_DB` (impostato nel Dockerfile) |

Nome del volume, percorso del file e chiave del servizio Compose (`subitowatch`) restano quelli di SubitoWatch per compatibilità.

## Tabelle BuyWatcher (`bw_*`)

Topic, annunci e profilo hanno il contenuto in un JSON nella colonna `body`. Le colonne vere sono solo quelle sotto.

| Tabella | Colonne | Note |
|---|---|---|
| `bw_topics` | id, body, revision, created_at, updated_at, legacy_channel_id (unico) | `revision` per `If-Match`. `legacy_channel_id` = canale da cui è stato importato |
| `bw_listings` | id, url (unico), source, body, content_hash, first_seen, last_seen | identità globale dell'annuncio = URL |
| `bw_snapshots` | id, listing_id, body, content_hash, captured_at | una riga per versione diversa: storico prezzi. Unico (listing_id, content_hash) |
| `bw_matches` | topic_id, listing_id (PK), state, analysis, evaluation_key, error, first_seen, last_seen, evaluated_at | legame topic ↔ annuncio. `state`: pending, evaluating, evaluated, excluded, error |
| `bw_runs` | id, topic_id, state, started_at, finished_at, report (JSON) | indice unico parziale `bw_one_run`: un solo run `running` per topic |
| `bw_feedback` | topic_id, listing_id (PK), verdict | preferiti e scarti, per topic |
| `bw_profile` | id (=1), body, revision, updated_at | profilo taglie, una riga sola |

## Relazioni

```
bw_topics 1──N bw_matches N──1 bw_listings 1──N bw_snapshots
    │                                  ▲
    ├──N bw_runs                       │
    └──N bw_feedback ──────────────────┘
```

`bw_matches`, `bw_runs`, `bw_feedback` hanno `ON DELETE CASCADE` sul topic: oggi `DELETE /topics/{id}` cancella anche valutazioni, preferiti e run (ADR-009 propone di archiviare).

## Tabelle legacy SubitoWatch

`channels`, `channel_listings`, `feedback`, `deals`. Gestite da `repositories/legacy_storage.py`, usate solo dalle rotte legacy dell'MCP. Al primo avvio ogni canale è stato importato **una volta** come topic in pausa. Le modifiche successive ai canali non arrivano ai topic. ADR-007 propone di eliminarle.

## Migrazioni

- Alembic in `backend/alembic/`. A ogni avvio `init_db()` porta il DB a `head`.
- Oggi c'è solo `0001_baseline`: `CREATE TABLE IF NOT EXISTS` delle `bw_*`, sicura sul DB esistente. Il downgrade non esiste: si ripristina un backup.
- Le tabelle legacy le crea ancora `legacy_storage.init_db()`, fuori da Alembic.
- Previste (piano 02): `0002` colonne vere al posto dei JSON, `0003` eliminazione delle tabelle legacy.
- **Backup coerente prima di ogni migrazione** (`sqlite3 .backup`).

## Recupero al riavvio

All'avvio i run `running` diventano `interrupted` e le valutazioni `evaluating` tornano `pending`. Non si riprendono a metà.
