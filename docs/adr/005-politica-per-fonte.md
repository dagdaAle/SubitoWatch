# ADR 005 — Una politica esplicita per ogni fonte

- Data: 01/11/2026 (in produzione dal 21/10/2026)
- Stato: accettata

## Contesto

I marketplace hanno termini diversi: eBay offre un'API ufficiale con limiti d'uso, Vinted e Facebook vietano
la raccolta automatica, Subito non offre API. Un blocco può colpire l'IP di casa e quindi anche la navigazione di Ale.

## Decisione

Ogni fonte dichiara quattro capacità separate: `enabled` (si raccoglie), `automatic` (la raccoglie lo scheduler),
`analysis` (i dati possono andare all'LLM), `pricing` (entrano nei confronti di prezzo). Le fonti non ufficiali
si accendono solo con una variabile esplicita. Regole fisse per tutte:

- niente login automatizzati, niente CAPTCHA, niente proxy a rotazione;
- una pagina per ricerca, pause tra le richieste;
- 403 o 429 fermano la fonte per quell'esecuzione, senza nuovi tentativi;
- un cambio di struttura della risposta è un errore visibile, non una ricerca vuota.

## Perché

- Le credenziali di eBay non danno automaticamente il diritto di analizzare o confrontare i prezzi.
- Separare le capacità permette di usare una fonte per vedere gli annunci senza usarla per i prezzi.

## Conseguenze

- Facebook resta solo un link di ricerca. Vinted è attivo a rischio di Ale (domanda aperta in PRODUCT.md).
- Un connettore nuovo non entra senza la sua riga di politica e i test su risposte registrate.
