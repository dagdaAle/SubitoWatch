Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Deploy e operations

## Dove gira

| Voce | Valore |
|---|---|
| Server | server di casa (HP, RTX 3060), Coolify, progetto **homelab** (riordino del 12/11/2026) |
| Risorsa Coolify | app dal repo GitHub `dagdaAle/SubitoWatch`, branch `main`. UUID annotato il 17/09: `8veuvvdimhhhctntuwih52so` — DA VERIFICARE che sia ancora quello |
| Container | `subitowatch-api` (in Coolify). In `docker-compose.yml` locale: `subitowatch` |
| Immagine | `buywatcher:latest`, Dockerfile multi-stage (Node 22 per il frontend, Python 3.13-slim + uv) |
| Dominio | https://subitowatch.intecha.dev |
| Auth | Authentik forward-auth, gruppo `utenti-app`. Escluso solo `^/ebay/account-deletion$` |
| Porta | interna 8000. Compose locale: `127.0.0.1:8081:8000` |
| Dati | volume `subito-data` su `/data` |
| LLM | Ollama sul server, modello `buywatcher-vision-8b` |

## Regole di deploy

- **Un solo processo, un solo worker uvicorn** (`--workers 1`). Mai due istanze sullo stesso DB, nemmeno durante il deploy: Coolify deve fermare la vecchia prima di avviare la nuova. Impostazione Coolify che lo garantisce: DA VERIFICARE.
- `stop_grace_period: 3m`: lascia finire una valutazione in corso.
- **Mai `docker compose down -v`**: cancella il volume con annunci e preferiti.
- Non cambiare il nome del progetto Compose: cambierebbe il nome effettivo del volume.
- Il repo non modifica dominio, Authentik o configurazione MCP: quelle si cambiano a mano.

## Healthcheck

- Dockerfile: `HEALTHCHECK` ogni 30 s con `python /app/healthcheck.py` (niente curl o wget nell'immagine).
- Coolify, healthcheck di tipo CMD: stesso comando.
- `/health` controlla solo il DB e dice se l'AI è configurata. Non verifica le fonti né la qualità dell'AI: per quello si leggono i report dei run.

## Come si aggiorna

1. Merge su `main` via PR.
2. Backup coerente del DB se il rilascio tocca lo schema.
3. Redeploy da Coolify (automatico al push o manuale: DA VERIFICARE).
4. Controlla `/health` e un run di prova su un topic.

## Backup

- **Non** è nel backup notturno restic (`/opt/app-backup/app-backup.sh`, ore 02:30): la lista in STATO-SERVER non comprende buywatcher. DA VERIFICARE.
- Esistono backup manuali in `~/backups/` sul server (cartella buywatcher).
- Metodo: `sqlite3 /data/subito.db ".backup ..."` (copia coerente con WAL), oppure ferma il container e copia anche `-wal` e `-shm`.
- Prova di ripristino: mai fatta. DA VERIFICARE.

## Rollback

Immagine precedente in Coolify + backup coerente del DB. Il volume non si cancella. La migrazione `0001` non ha downgrade.

## Log

- Log di uvicorn e dell'app su stdout: Coolify → Logs, oppure Dozzle.
- Errori di normalizzazione: riga `Listing enrich failed: source=... ` con il motivo.
- Errori per fonte e per valutazione: nel `report` del run (`GET /api/v1/runs/{id}`), visibili nella UI.
