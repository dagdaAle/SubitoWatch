# ADR 010 — Una scheda AI per annuncio al posto dell'analisi

- Data: 07/11/2026
- Stato: accettata (decisione di Ale)
- Sostituisce in parte: [004](004-llm-estrae-fatti-convenienza-deterministica.md)

## Contesto

L'analisi a schema (`Analysis`: pertinenza 0-100, confidenza, osservazioni, rischi) non dava ad Ale quello che
serve per scegliere. Le taglie venivano filtrate male (L o XL, scarpe 33 o 45): il dato c'era, ma in campi della
piattaforma che la raccolta buttava via (le `features` di Subito, gli aspects di eBay) oppure in mezzo alla
descrizione, dove le regex non lo trovavano.

## Decisione

- La raccolta salva i **campi strutturati della fonte** in `attributes` (Subito: Taglia, Marca, Genere,
  Condizione, spedizione; Vinted: Marca, Taglia, Condizione; eBay: aspects e paese).
- Per ogni annuncio **una sola chiamata** al modello (oggi DeepSeek, `json_object`) riceve tutto: bisogno,
  titolo, descrizione, `attributes`, prezzi, località, foto se c'è un modello con visione. Restituisce la
  **scheda** (`Card`): nome, marca, modello, categoria, genere, taglia (e da dove viene), condizioni, difetti,
  da dove spedisce, prezzo stimato del nuovo, se è ciò che cerchi, se è una vera offerta.
- Il **filtro taglie** è un confronto deterministico tra i campi della scheda e il profilo
  (`personalization.assess`), fatto in lettura: cambiare il profilo non costa nuove chiamate.
- Via triage, punteggio di pertinenza, confidenza e rischi. Il `relevance_threshold` del topic non è più usato.

## Cosa cambia rispetto all'ADR 004

- Il modello **stima il prezzo del nuovo** e dà un verdetto di convenienza. La UI lo mostra come stima del
  modello, mai come prezzo verificato.
- Il confronto con almeno 3 offerte equivalenti resta, deterministico, come controllo aggiuntivo
  (`score`); non sovrascrive il verdetto del modello.
- Resta valido: ciò che non si sa è `null`/"non noto", mai 0.

## Conseguenze

- DeepSeek non legge le foto: una taglia scritta solo sull'etichetta in foto resta sconosciuta
  ("Da verificare"). Se serve, si aggiunge `BUYWATCHER_VISION_MODEL`.
- Le schede esistenti vanno ricompilate (versione `card-1`): il primo passaggio notturno lo fa da solo.
- La qualità va misurata su annunci veri (piano 05) prima di fidarsi del verdetto "vera offerta".
