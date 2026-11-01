# ADR 001 — Bisogni d'acquisto (topic) invece di canali di parole chiave

- Data: 01/11/2026 (decisione presa il 21/10/2026, in produzione)
- Stato: accettata

## Contesto

SubitoWatch era fatto di **canali**: parole chiave, comune, prezzo minimo e massimo su Subito. Una ricerca per
parola chiave non sa distinguere una GPU da un PC che la contiene, una taglia giusta da una sbagliata, un
negozio da un privato. Ale doveva comunque aprire ogni annuncio.

## Decisione

L'unità è il **topic**: un bisogno d'acquisto con uso previsto, requisiti, preferenze, esclusioni, difetti
accettati, budget e fonti. Le parole chiave servono solo a raccogliere i candidati; il giudizio è fatto
contro il bisogno, non contro le parole chiave.

## Perché

- Il valore dell'app sta nel filtro, non nella raccolta: la raccolta la fa già qualunque alert.
- Un bisogno scritto in italiano è quello che Ale detta a Hermes; un canale richiede di pensare ai filtri del sito.

## Conseguenze

- Un topic senza bisogno compilato vale quanto un canale. I 6 topic importati dai canali sono in questo
  stato e vanno riscritti (PRODUCT.md, domande aperte).
- La creazione passa da una proposta AI (`analyze_need`) rivista da Ale, non da un modulo di 15 campi.
