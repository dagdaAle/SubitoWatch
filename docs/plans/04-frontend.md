# Frontend — piano di implementazione

> **Per agenti:** sotto-skill richiesta: superpowers:subagent-driven-development (consigliata) oppure
> superpowers:executing-plans. I passi usano le checkbox (`- [ ]`).

**Obiettivo:** UI di [DESIGN.md](../DESIGN.md) con lo stack di todo-app, al posto del solo `App.tsx`.

**Stack:** React + TypeScript + Vite, Mantine (tema dai token Lumina Workspace), TanStack Query, client generato da
`backend/openapi.json`, React Router, vitest.

**Dipende da:** [02-backend](02-backend.md) e dai mockup Stitch approvati (DESIGN.md, "Prossimo passo").

## Passi

- [ ] Mockup Stitch delle 4 schermate (Radar, Topic, Annuncio, Nuovo topic), desktop e telefono; revisione con Ale; DESIGN.md aggiornato.
- [ ] `frontend/` nuovo: Vite, Mantine con tema dai token (riusare quello di todo-app), router, client generato, login OIDC + PKCE.
- [ ] Layout: barra laterale / menu in basso, Radar.
- [ ] Topic: schede delle viste, card annuncio, ordinamento, filtri, barra dell'esecuzione in corso (query su `/runs/{id}` solo mentre è attiva).
- [ ] Popup annuncio con tutte le sezioni di DESIGN.md.
- [ ] Nuovo topic: frase → proposta AI → revisione → crea; modulo diretto senza AI.
- [ ] Fonti e Taglie.
- [ ] Stati: vuoti, AI non configurata, fonte in errore, interrotta, da rivalutare, non più visto, scheletri.
- [ ] Accessibilità: contrasto AA chiaro/scuro, tastiera, `aria-label`, touch target 44 px.
- [ ] Test vitest su filtri delle viste e formattazione dei costi; `tsc --noEmit` e build in CI.
- [ ] Togliere gli alias `/api/...` dal backend.

## Fatto quando

Tutte le pagine di DESIGN.md in produzione, nessuna chiamata alle rotte senza `/v1`, Ale usa la UI da telefono.
