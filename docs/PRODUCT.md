# PRODUCT — cosa è e perché esiste

> Stato: bozza del 01/11/2026. Nome: `BuyWatcher` (repo ancora `dagdaAle/SubitoWatch`).
> Le voci marcate **(scelta di Claude)** non sono state decise da Ale: vanno confermate o cambiate.

## Il problema

Ale compra molto usato (abbigliamento, hardware, cose per hobby) e lo cerca su più marketplace:
Subito, Vinted, eBay, Facebook Marketplace. Oggi questo vuol dire:

- **Ricerche ripetute a mano** su ogni sito, ogni giorno, con gli stessi filtri.
- **Troppo rumore**: una ricerca "scheda grafica" restituisce PC completi, ricambi, annunci di negozi,
  taglie sbagliate. Il filtro per parola chiave non capisce il bisogno.
- **Nessun metro di giudizio**: un prezzo richiesto non dice se l'annuncio conviene, e le foto vanno
  guardate una per una per capire le condizioni.

SubitoWatch (canali di parole chiave su Subito, Verona) risolveva solo la prima parte. Il 20/10/2026 Ale ha
chiesto di *"mettere a posto subito watch e metterci dentro anche vinted"*: da lì è nato BuyWatcher, che
sposta il centro dalle **parole chiave** al **bisogno d'acquisto**.

## L'idea

Un radar personale dell'usato, sul server di casa, organizzato per **bisogni d'acquisto (topic)**:

- Un topic descrive **cosa serve e perché**: uso previsto, requisiti, preferenze, esclusioni, difetti
  accettati, budget, località, fonti. Le parole chiave sono solo il modo di cercarlo.
- L'app **raccoglie** gli annunci dalle fonti attive, li **normalizza** e conserva storico e prezzi.
- Un **LLM valuta** ogni annuncio contro il topic: pertinenza, condizioni, foto, parti mancanti, rischi,
  domande da fare al venditore. Il modello estrae fatti, **non inventa prezzi né giudizi senza dati**.
- La **convenienza** è calcolata in modo deterministico confrontando offerte equivalenti, non chiesta all'AI.
- Ale apre il topic e trova tre liste: **consigliati**, **da verificare**, **esclusi**, ognuno con il motivo.

## Stato al 01/11/2026

In produzione su `https://subitowatch.intecha.dev` dietro Authentik, commit `fac8798`.

- **6 topic**, tutti importati dai vecchi canali (Vans, The North Face, Server usati, Schede grafiche,
  Telescopi due volte). Nessuno ha un budget e i bisogni dicono *"ancora da definire"*: oggi sono canali
  travestiti da topic, la parte di valore (il bisogno) non è stata compilata.
- **Fonti**: Subito funziona. Vinted raccoglie ma scartava tutti gli annunci (fix in produzione, mai
  verificato). eBay è bloccato da `401 invalid_client` (keyset Production disabilitato). Facebook è solo
  un link di ricerca.
- **MCP**: Hermes vede solo i vecchi canali (`subitowatch.list_channels`, `create_channel`...),
  non i topic né le valutazioni.

## Principi trasversali (gli stessi di todo-app)

- **Tutto interrogabile da un LLM via MCP**: ogni cosa visibile o fattibile nell'app lo è anche per Hermes.
  Oggi non è vero, ed è il primo buco da chiudere.
- **Pensata per il server e per più client**: web oggi, telefono domani, stessa API.
- **Backend fatto bene**: strati, migrazioni, contratto API stabile (ARCHITECTURE.md).
- **Onestà sui dati**: ciò che non si sa resta "non noto". Spedizione vuota non è zero, foto non analizzata
  non è foto buona, assenza dalla ricerca non è vendita. Questo principio c'è già nel codice e va tenuto.

## Utenti

- **Ale**: crea e rifinisce i topic, legge i consigliati, mette preferiti e scarti, decide se contattare.
  Da Mac e da telefono.
- **Hermes**: crea un topic da un bisogno dettato (*"mi serve una GPU per il server, max 250 €"*),
  avvia ricerche, riassume i consigliati, segnala le novità.

App per una persona sola. Niente multi-utente: il profilo taglie è uno solo per installazione.

## Le pagine **(scelta di Claude)**

1. **Radar**: elenco dei topic con contatori (nuovi, consigliati, da verificare) e stato dell'ultima ricerca.
2. **Topic**: le tre liste (consigliati · da verificare · esclusi), più preferiti e scartati. Ogni annuncio
   mostra prezzo totale (o cosa manca per saperlo), punteggio, motivo, foto e fonte.
3. **Annuncio** (popup, come il task in todo-app): analisi completa, evidenze dalle foto e dal testo tenute
   separate, domande al venditore, storico prezzi, link all'annuncio.
4. **Nuovo topic**: Ale scrive il bisogno in una frase, l'AI propone il topic completo, Ale lo rivede.
   Compilare il modulo a mano resta possibile ma non è la strada principale.
5. **Ricerche**: storico delle esecuzioni per topic, con errori per fonte.
6. **Personalizzazione**: taglie (scarpe EU, abbigliamento).

## Fonti

| Fonte | Come | Stato |
|---|---|---|
| Manuale | Ale incolla titolo, descrizione, foto | Attiva |
| Subito | Scraping HTML, provincia di Verona | Attiva |
| Vinted | Catalogo anonimo, una pagina per ricerca | Attiva, da verificare |
| eBay | Browse API ufficiale | Bloccata (credenziali) |
| Facebook Marketplace | Solo link di ricerca | Nessuna raccolta |
| Wallapop, Astrosell | — | Future |

Regola già in vigore e da tenere: **nessun login automatizzato, nessun aggiramento di CAPTCHA, nessuna
rotazione di proxy**. Una fonte che rifiuta passa in errore, non si forza.

## Obiettivi

- Aprire un topic e capire in meno di 10 secondi se oggi c'è qualcosa che vale la pena contattare.
- Zero ricerche manuali ripetute sulle fonti attive.
- Ogni giudizio è spiegato: perché è consigliato, perché è escluso, cosa manca per decidere.
- Hermes può fare tutto quello che fa Ale nella UI.
- Pezzo da portfolio AI/ML: valutazione LLM con output a schema, visione sulle foto, inferenza locale,
  e un sistema di valutazione della qualità (vedi "Misurare l'AI").

## Non obiettivi

- **Non** un comparatore di prezzi pubblico, **non** un bot che contatta i venditori o compra.
- **Non** una stima del "prezzo di mercato": i confronti sono tra offerte attive, non tra vendite concluse.
- **Non** multi-utente, **non** un'app mobile nativa.
- **Non** una copertura completa dei marketplace: meglio poche fonti affidabili che tante fragili.

## Anti-obiettivi (se succede, il progetto è fallito anche se funziona)

- I consigliati sono pieni di annunci fuori tema: Ale smette di fidarsi e torna a cercare a mano.
- Un punteggio o un prezzo inventato dall'AI viene mostrato come fatto.
- Un account di Ale (o l'IP di casa) viene bannato da un marketplace per colpa dell'app.
- Creare un topic richiede di compilare 15 campi: la cattura resta una frase, a voce o scritta.
- Per sapere cosa succede bisogna leggere i log del container.

## Misurare l'AI **(scelta di Claude)**

Le soglie di oggi (pertinenza 70, confidenza 70, affare da 75) sono **iniziali e non calibrate**.
Servono:

- un **set di casi etichettati** da Ale (annuncio + topic + giudizio atteso), partendo da preferiti e scarti
  che già esistono nel DB (`bw_feedback`);
- uno script che rilancia la valutazione sul set e misura precisione dei consigliati e annunci validi
  finiti per errore negli esclusi, per modello e per categoria;
- il confronto tra modelli locali (Ollama) e remoti sugli stessi casi prima di cambiare modello.

## Decisioni da prendere **(proposte di Claude)**

1. **Canali legacy**: si eliminano. I 6 topic esistono già; le rotte `/channels`, `/feedback`, `/favorites`
   e `/deals` si tolgono dopo che l'MCP passa ai topic, insieme alle tabelle `channels`, `channel_listings`,
   `feedback` e `deals` (con backup). Alternativa: tenerle in sola lettura.
2. **Nome**: repo `dagdaAle/SubitoWatch` → `dagdaAle/BuyWatcher`, dominio `buywatcher.intecha.dev`
   con redirect dal vecchio. Il volume `subito-data` resta (rinominarlo non porta nulla).
3. **Cancellazione dei topic**: diventa **archiviazione**, come gruppi e task in todo-app. Si perde
   meno storico di prezzi e preferiti.
4. **Un solo clone**: quello vero è `~/Progetti/Codex/2026-10-21/.../work/BuyWatcher`. Va spostato in
   `~/Progetti/server-apps/BuyWatcher` e il vecchio `server-apps/SubitoWatch` va archiviato.
5. **Notifiche**: un nuovo consigliato arriva ad Ale tramite Hermes (messaggio o riga nel todo) solo se
   supera la soglia di affare, non per ogni annuncio.
6. **Ricerche pianificate**: deciso da Ale il 02/11/2026: ogni notte alle 2, poi la coda di valutazione
   si svuota fino alle 7. Di giorno solo ricerche a mano.

## Fasi **(scelta di Claude)**

1. **Consolidare**: un clone, documenti (questo, ARCHITECTURE, DESIGN, ADR), verifica di Vinted e sblocco eBay.
2. **Backend**: strati `routers → services → repositories`, Alembic, `/api/v1` con Problem Details.
   La logica di valutazione, scoring, fonti e taglie si sposta senza cambiare comportamento: i test esistenti
   fanno da rete.
3. **MCP sui topic**: nuovi strumenti in `intecha-mcp`, poi via i canali legacy.
4. **Frontend**: rifatto con lo stesso stack di todo-app (Mantine, TanStack Query, client generato).
5. **Qualità AI**: set etichettato, script di valutazione, calibrazione delle soglie.

## Domande aperte

- **Cosa compra davvero Ale nei prossimi mesi?** I 6 topic attuali sono generici: servono 2-3 bisogni
  veri e compilati (con budget) per collaudare e calibrare.
- **Vinted**: va bene il rischio di blocco dell'IP di casa per il connettore anonimo, o si torna al
  solo link di ricerca?
- **Raggio**: oltre a Verona, quali province o distanze contano per Subito?
- **Provider AI**: si resta su Ollama locale (RTX 3060) o si accetta un provider remoto per la qualità,
  sapendo che riceve testo e foto degli annunci?
