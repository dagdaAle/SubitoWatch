# ADR 004 — L'LLM estrae fatti, la convenienza è calcolata

- Data: 01/11/2026 (regola in produzione dal 21/10/2026)
- Stato: accettata

## Contesto

Un LLM chiamato a dire "questo annuncio conviene" risponde con sicurezza anche senza dati, e un modello
piccolo locale inventa prezzi di mercato a memoria.

## Decisione

- L'LLM produce solo un'**analisi a schema** (`Analysis`): pertinenza, confidenza, condizioni, requisiti violati
  o non verificati, osservazioni con la loro base (testo, foto con indice, metadati), parti mancanti, rischi, domande.
- La **convenienza** la calcola `scoring.py` dai costi della fonte: mediana di almeno 3 offerte equivalenti
  indipendenti, con costo totale noto. Senza questi dati la risposta è "non determinabile".
- Ciò che non si sa resta `null` o "non noto": spedizione vuota non è zero, foto non analizzata non è foto buona.

## Perché

- Un punteggio inventato mostrato come fatto è un anti-obiettivo (PRODUCT.md).
- Le regole deterministiche si testano; i giudizi del modello si misurano a parte (`scripts/eval_ai`).

## Conseguenze

- Molti annunci restano "da verificare" o senza punteggio: è voluto.
- Le soglie (70, 59, 75) sono iniziali e vanno calibrate su casi etichettati da Ale.
