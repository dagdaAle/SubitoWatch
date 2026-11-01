# Consolidare repo, fonti e dati — piano di implementazione

> **Per agenti:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata) oppure
> superpowers:executing-plans. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** un solo clone, repo rinominato, fonti verificate in produzione, topic veri con bisogno e budget.
Nessun cambio di architettura: è il terreno su cui poggiano le fasi successive.

**Spec:** [PRODUCT.md](../PRODUCT.md) (decisioni 2 e 4, domande aperte), [adr/005](../adr/005-politica-per-fonte.md).

**Dipende da:** merge della PR dei documenti.

## Repo

- [ ] Rinominare su GitHub `dagdaAle/SubitoWatch` → `dagdaAle/BuyWatcher` (GitHub tiene il redirect del vecchio URL).
- [ ] Spostare il clone in `~/Progetti/server-apps/BuyWatcher`, aggiornare `origin`, cancellare i branch locali già mergiati.
- [ ] Archiviare `~/Progetti/server-apps/SubitoWatch` (fermo a `81b9d6f`): prima `git status`, nessuna modifica da salvare.
- [ ] Aggiornare la sorgente dell'app su Coolify al repo rinominato; redeploy; `/health` risponde.
- [ ] Aggiornare i path nel vault (`Link importanti.md`, daily) e in `server-apps.code-workspace`.

## Fonti

- [ ] **Vinted**: avviare la ricerca sul topic Vans, leggere `GET /api/runs/{id}` e i log `Listing enrich failed: source=vinted`.
      Se gli annunci entrano: chiudere il todo. Se no: fixture con la risposta vera (anonimizzata) + test rosso + fix.
- [ ] **eBay**: con Ale, ricopiare App ID e Cert ID dallo stesso keyset Production, gestire *Marketplace Account Deletion*
      (esenzione o endpoint), aggiornare Coolify, redeploy. Verifica: un'esecuzione con eBay `success`.
- [ ] **Subito**: un'esecuzione su ogni topic attivo, nessun errore di struttura.

## Dati

- [ ] Backup coerente di `/data/subito.db` (`sqlite3 .backup`) fuori dal server.
- [ ] Unire o archiviare il doppione "Telescopi" / "Telescopi · ricerca astronomica".
- [ ] Con Ale: riscrivere 2-3 topic veri (bisogno, requisiti, budget) partendo da "Cosa ti serve?".
- [ ] Segnare in PRODUCT.md le decisioni confermate (togliere "scelta di Claude" dove Ale ha detto sì).

## Fatto quando

Un solo clone, repo `BuyWatcher`, tutte le fonti attive con un'esecuzione riuscita, almeno 2 topic con bisogno e budget.
