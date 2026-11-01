# ADR 003 — SQLite, un processo, un thread di lavoro

- Data: 01/11/2026 (in produzione dal 21/10/2026)
- Stato: accettata; colonne al posto dei JSON e Alembic sono **proposta (scelta di Claude)**

## Contesto

Un utente, qualche migliaio di annunci per topic, fonti da interrogare piano per non farsi bloccare.
Le app sorelle usano SQLite su volume Docker.

## Decisione

- SQLite in WAL su `/data/subito.db`, volume `subito-data` (nome e percorso non cambiano).
- Un solo worker uvicorn; raccolta e valutazione in **un thread** con coda in memoria; scheduler nello stesso processo.
- Schema gestito da Alembic; i campi filtrabili di topic e annunci diventano colonne, l'analisi resta JSON validato.

## Perché

- Le fonti vanno comunque distanziate: lavorare in parallelo aumenterebbe solo il rischio di blocco.
- Un solo scrittore elimina i conflitti di SQLite e i doppi lanci dello stesso topic
  (in più c'è l'indice unico su un'esecuzione `running` per topic).
- Backup = copia coerente di un file.

## Conseguenze

- Mai due istanze sullo stesso DB, nemmeno durante un deploy: Coolify deve fermare la vecchia prima di avviare la nuova.
- Un riavvio interrompe l'esecuzione in corso: viene segnata `interrupted`, non ripresa.
- Se un giorno servissero più worker, la coda passa nel DB prima di cambiare database.
