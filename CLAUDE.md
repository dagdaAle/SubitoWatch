# CLAUDE.md — SubitoWatch

Monitor personale degli annunci **Subito.it** in provincia di Verona, organizzati
in canali. FastAPI + SQLite + scraper in Docker (`webapp/app.py`, `scraper.py`,
`storage.py`), esposto a Claude via MCP. In produzione su `subitowatch.intecha.dev`,
dietro Authentik (gruppo `utenti-app`).

## ⚠️ Stato reale: l'app è un guscio vuoto

Verificato il 18/09/2026 (rilievo **APP-01**): database **40 KB, solo schema**,
**0 canali, 0 annunci**. Il codice gira, ma nessuno l'ha mai configurata.

Prima di aggiungere funzionalità qui, la domanda vera è: **la si configura o la si
spegne?** Scrivere codice nuovo su un'app che nessuno usa è lavoro che non verrà
mai esercitato — ed è esattamente così che questa app è finita in questo stato.

## Da non toccare

| Elemento | Regola | Perché |
|---|---|---|
| Volume `subito-data` (`/data`) | Non ricreare | Tiene gli annunci già visti e i preferiti: è ciò che distingue un annuncio nuovo da uno già scartato. Oggi è quasi vuoto, ma appena la si configura diventa l'unico dato non rigenerabile — gli annunci scadono e spariscono da Subito. |
| `scraper.py` | Trattare con cautela: dipende dall'HTML di Subito.it | Non c'è un'API. Ogni modifica al parsing va provata su pagine reali, e si romperà da sola quando Subito cambia il markup. Se lo scraper smette di trovare annunci, **sospettare prima Subito che il codice**. |
| Il ritmo delle richieste dello scraper | Non alzarlo | È scraping non autorizzato di un sito commerciale: la cortesia sulle richieste è ciò che tiene l'IP di casa fuori dai blocchi. |

## Comandi

```bash
docker compose up -d --build         # app su http://localhost:8081
docker compose logs -f subitowatch
```

Porte locali: **8080** jobspy · **8081** subitowatch · **8082** hnwatch.

## Regole operative

- **Manca il README**: è l'unica delle tre app gemelle senza. Se lavori qui,
  scriverlo vale più di una funzionalità nuova — prendi come modello quello di HNWatch.
- Commit in italiano, indicativo presente: "Initial commit: SubitoWatch".
- **Stesso stack di JobSpy e HNWatch**: storage, canali e struttura sono gemelli.
  Guardare là prima di decidere qui.
- Gli strumenti MCP stanno in `servers/subitowatch.py` nella repo `intecha-mcp`,
  non qui.

## Cosa non fare

- **Non popolare questa repo con filtri e preferiti reali**: è **pubblica**, e cosa
  cerchi e quanto spendi sono dati personali. Oggi non è un problema solo perché
  l'app è vuota (rilievo REP-02).
- **Non allargare le ricerche a tutta Italia**: il progetto è per la provincia di
  Verona, e allargare moltiplica le richieste allo scraper.
- **Non riavviare su Coolify per applicare una variabile**: serve stop + start.
- Non presumere che l'app funzioni perché il container è "healthy": 6 delle 8 app
  sul server non hanno healthcheck applicativo (OPS-08). Verificare i dati, non lo stato.

## Riferimenti

- Repo gemelle: `dagdaAle/hnwatch` (ha il README migliore), `dagdaAle/JobSpy`
- Lato MCP: `dagdaAle/intecha-mcp` (`servers/subitowatch.py`)
- Vault Obsidian, `server/Intecha-audit-2026-09-18.md` — rilievo APP-01
