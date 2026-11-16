Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Decisioni (ADR)

Le ADR complete sono in `docs/adr/` del repo. Qui il riassunto, più ADR-000 scritta per questa pagina.

## ADR-000 — Da SubitoWatch a BuyWatcher

- Stato: accettata, in produzione.
- Date: richiesta il 20/10/2026, primo commit BuyWatcher `ea1f98c` (PR #3, `feat/buywatcher`), documentazione di prodotto e ADR il 01/11/2026 (PR #10). Archiviazione di SubitoWatch indicata al 2026-11-01: cosa sia stato archiviato esattamente (progetto, servizio o solo il nome) DA VERIFICARE.

**Contesto.** SubitoWatch era un monitor di canali: parole chiave, comune, prezzo minimo e massimo, solo Subito Verona. Al 18/09/2026 l'audit lo trovava vuoto (0 canali, 0 annunci, APP-01: "o si configura o si spegne"). La parola chiave non distingue una GPU da un PC che la contiene né una taglia giusta da una sbagliata. Il 20/10 Ale chiede di *"mettere a posto subito watch e metterci dentro anche vinted"*.

**Decisione.** Stesso repo e stessa installazione, nuovo prodotto: BuyWatcher. L'unità diventa il topic (bisogno d'acquisto) con valutazione AI; più fonti (Subito, Vinted, eBay, manuale, link Facebook).

**Cosa è rimasto di SubitoWatch, per compatibilità.**
- Repo GitHub `dagdaAle/SubitoWatch` e dominio `subitowatch.intecha.dev`.
- Volume `subito-data`, file `/data/subito.db`, chiave Compose `subitowatch`, container `subitowatch-api`.
- Tabelle e rotte legacy (`/channels`...) e i tool MCP `subitowatch__*`.
- I canali sono stati importati una volta come topic in pausa.

**Alternative scartate.** Nuovo repo e nuovo DB: avrebbe perso storico e preferiti e richiesto di rifare Coolify, Authentik e MCP. Tenere SubitoWatch e aggiungere solo Vinted: non risolveva il rumore.

**Conseguenze.** Nomi misti: chi cerca "buywatcher" sul server trova `subitowatch`. I tool MCP non vedono i topic finché non arriva il piano 03. Rinominare dominio, volume o tool va fatto in un rilascio coordinato.

## ADR-001 — Topic invece di canali
Accettata. Il giudizio si fa contro il bisogno, non contro le parole chiave. I 6 topic importati dai canali hanno il bisogno "da definire": vanno riscritti.

## ADR-002 — Rifattorizzare, non riscrivere
Proposta (scelta di Claude). Si cambia la struttura (strati, Alembic, `/api/v1`) e si sposta la logica di dominio senza cambiarne il comportamento. Scartata la riscrittura: perderebbe casi limite che oggi stanno solo nel codice.

## ADR-003 — SQLite, un processo, un thread di lavoro
Accettata (colonne al posto dei JSON: proposta). Le fonti vanno distanziate comunque, un solo scrittore evita conflitti. Conseguenza: mai due istanze, un riavvio interrompe il run.

## ADR-004 — L'LLM estrae fatti, la convenienza è calcolata
Accettata. L'LLM produce un'analisi a schema. La convenienza viene da `scoring.py`: mediana di almeno 3 offerte equivalenti con costo totale noto. Ciò che non si sa resta `null`. Soglie 70 / 59 / 75 non calibrate.

## ADR-005 — Una politica esplicita per ogni fonte
Accettata. Capacità separate `enabled`, `automatic`, `analysis`, `pricing`. Niente login automatici, CAPTCHA, proxy a rotazione. 403/429 fermano la fonte.

## ADR-006 — Una sola API, MCP sui topic
Proposta. `/api/v1` con `openapi.json`, server MCP `buywatcher` / `buywatcher_write` con test di parità, JWT Authentik per web e mobile, token di servizio per l'MCP.

## ADR-007 — Via i canali legacy
Proposta. Dopo il passaggio dell'MCP ai topic si tolgono rotte e moduli legacy, poi le tabelle. Scartato: tenerle in sola lettura.

## ADR-008 — LLM dietro un endpoint compatibile OpenAI
Accettata per l'interfaccia, provider aperto (locale o remoto). Cambiare provider è un cambio di variabili. Foto inviate in base64 perché Ollama non accetta URL remoti.

## ADR-009 — I topic si archiviano, non si cancellano
Proposta, **non implementata**: oggi esiste ancora `DELETE /topics/{id}` con cascata.

## In discussione: scheda per annuncio al posto dell'analisi
PR #19 (`feat/card-ai`, 07/11/2026), **aperta**. Ale ha deciso di tenere l'LLM (DeepSeek) solo per compilare una scheda strutturata per annuncio. Via triage, punteggio di pertinenza, confidenza e rischi. Resta il confronto deterministico su 3 offerte. La PR aggiunge `docs/adr/010`. Task collegati in todo-app: 1623 (togliere la valutazione LLM), 1624 (tagging con "jeff").
