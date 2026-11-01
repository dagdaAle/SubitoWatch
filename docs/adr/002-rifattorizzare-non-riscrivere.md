# ADR 002 — Rifattorizzare, non riscrivere

- Data: 01/11/2026
- Stato: proposta (scelta di Claude, da confermare)

## Contesto

Il codice di oggi ha una logica di dominio curata (cache delle valutazioni, convenienza deterministica,
download sicuro delle foto, controllo taglie, politica per fonte) dentro una struttura troppo semplice:
moduli piatti, SQL grezzo, schema senza migrazioni, API senza contratto, frontend in un solo componente.

## Decisione

Si cambia la **struttura** (strati, SQLAlchemy, Alembic, `/api/v1`, frontend come todo-app) e si **sposta**
la logica di dominio senza cambiarne il comportamento. I test esistenti si portano per primi e restano verdi
a ogni passo.

## Perché

- La parte difficile (regole di valutazione, sicurezza sulle foto, connettori) è già stata pagata e collaudata.
- Una riscrittura perderebbe casi limite che oggi sono solo nel codice.
- I passi piccoli tengono l'app in produzione durante il lavoro.

## Conseguenze

- Per un periodo convivono le rotte `/api/...` e `/api/v1/...` (alias).
- Le regole di dominio cambiano solo in PR dedicate, con il report di `scripts/eval_ai` se toccano l'AI.
