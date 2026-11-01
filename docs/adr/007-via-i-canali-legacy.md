# ADR 007 — Via i canali legacy

- Data: 01/11/2026
- Stato: proposta (scelta di Claude, da confermare)

## Contesto

Nello stesso DB convivono le tabelle di SubitoWatch (`channels`, `channel_listings`, `feedback`, `deals`)
e quelle di BuyWatcher. Le rotte legacy sono copiate dentro `app.py` solo per l'MCP. I canali sono già stati
importati una volta come topic in pausa; le modifiche successive ai canali non arrivano ai topic.
`/deals` è già sparito dall'MCP (404).

## Decisione

1. L'MCP passa ai topic (ADR 006).
2. Si rimuovono le rotte `/channels`, `/feedback`, `/favorites`, `/deals` e i moduli `legacy.py`, `storage.py`, `scraper.py`
   (lo scraper di Subito vive in `sources/subito.py`).
3. Dopo qualche giorno di uso e un backup, una migrazione Alembic elimina le tabelle legacy.

Alternativa scartata: tenerle in sola lettura. Costa codice da mantenere per dati già copiati nei topic.

## Conseguenze

- Il backup prima della migrazione è l'unico modo di recuperare i canali originali.
- Un solo modello dati: niente più "ho creato un canale ma non lo vedo in BuyWatcher".
