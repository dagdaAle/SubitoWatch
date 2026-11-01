# Qualità dell'AI — piano di implementazione

> **Per agenti:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata) oppure
> superpowers:executing-plans. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** misurare quanto sono giusti consigliati ed esclusi, e calibrare soglie e modello sui dati di Ale
([adr/004](../adr/004-llm-estrae-fatti-convenienza-deterministica.md), [adr/008](../adr/008-llm-compatibile-openai.md)).

**Dipende da:** [02-backend](02-backend.md); utile dopo qualche settimana di preferiti e scarti sui topic veri.

## Passi

- [ ] `backend/scripts/eval_ai/export_cases.py`: da `topic_listing.verdict` e da casi scritti a mano a `cases.jsonl`
      (topic, annuncio, foto, vista attesa). Foto scaricate una volta e tenute fuori dal repo.
- [ ] Partire da `buywatcher-eval-cases.json` del lavoro Codex del 21/10, se ancora valido.
- [ ] Con Ale: etichettare almeno 50 casi su 3 categorie (abbigliamento, hardware, astronomia).
- [ ] `run_eval.py --model ...`: report con consigliati corretti, validi finiti negli esclusi, errori di schema, tempo e token per caso.
- [ ] Confronto: modello locale di oggi contro un modello remoto sugli stessi casi; decisione in adr/008.
- [ ] Calibrare `relevance_threshold` di default, confidenza 70, tetto 59, affare 75; aggiornare ARCHITECTURE.md e adr/004.
- [ ] Regola in AGENTS.md: ogni PR che tocca prompt, schema o soglie allega il report.

## Fatto quando

Esiste un set etichettato, un report per il modello in uso e soglie scelte su numeri invece che a occhio.
