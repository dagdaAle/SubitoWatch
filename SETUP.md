# Installazione e migrazione BuyWatcher

## 1. Database e deploy esistente

Prima di aggiornare ferma il vecchio processo e fai un backup coerente del database
SQLite (incluso WAL se presente, oppure usa l’API backup di SQLite). Conserva il
volume Docker esistente. Non cambiare nome di progetto Compose durante una
migrazione: influenzerebbe il nome effettivo del volume `subito-data`.

Il nuovo schema aggiunge tabelle `bw_*` e il flag `channel_listings.is_new`.
Le tabelle legacy e i preferiti originali restano presenti. Ogni canale legacy è
importato una sola volta come topic **in pausa**; gli annunci importati richiedono
una valutazione AI. Le modifiche successive ai vecchi canali via MCP non vengono
sincronizzate nei nuovi topic: usa `/api/topics` per BuyWatcher.

Per un volume già esistente con un altro nome, collegalo esplicitamente nel Compose
di deployment con `external: true` e `name: NOME_ESISTENTE`, senza crearne uno vuoto.
La configurazione Coolify va controllata prima del rilascio: questo repository non
modifica dominio, autenticazione, configurazione MCP o risorse Coolify.

Il processo usa **un solo worker uvicorn** e una coda in memoria con un esecutore.
Non avviare due istanze sullo stesso database: il recupero startup dei job interrotti
è progettato per un unico proprietario. I job interrotti sono segnalati, non
ripresi automaticamente a metà. Rilanciali dall’interfaccia.

## 2. Provider AI

Copia `.env.example` in `.env` e configura:

| Variabile | Significato |
|---|---|
| `BUYWATCHER_AI_BASE_URL` | URL base completo fino a `/v1` (o equivalente) del server compatibile |
| `BUYWATCHER_AI_MODEL` | Nome del modello testuale disponibile sul provider |
| `BUYWATCHER_AI_API_KEY` | Chiave se richiesta, vuota per server locali che non la richiedono |
| `BUYWATCHER_AI_TIMEOUT` | Timeout inferenza in secondi (30–600), predefinito 120 |
| `BUYWATCHER_AI_REASONING_EFFORT` | Facoltativo; `none` disattiva il ragionamento esteso nei provider compatibili |
| `BUYWATCHER_VISION_MODEL` | Modello multimodale con supporto `image_url`; vuoto disabilita analisi foto |
| `BUYWATCHER_MAX_AI_PER_RUN` | Massimo valutazioni per esecuzione, predefinito 40 |
| `BUYWATCHER_MAX_DETAILS_PER_SOURCE` | Massimo annunci arricchiti per fonte/esecuzione, predefinito 30 |
| `BUYWATCHER_DB` | Override facoltativo del database; normalmente mantieni `/data/subito.db` |

Il provider deve accettare `POST /chat/completions`, messaggi multimodali,
`response_format.type=json_schema` (valutazione) e `json_object` (proposta topic),
`temperature=0` e `max_tokens`. Lo schema di generazione consente riferimenti
fotografici solo agli indici effettivamente allegati; le risposte sono validate
anche contro lo schema Pydantic.
Non è sufficiente che un endpoint accetti una connessione: verifica la restituzione
di JSON valido e la capacità effettiva di leggere immagini con il modello scelto.

Con provider remoto vengono trasmessi bisogno, descrizione, dati del candidato e,
se configurata la visione, fino a sei foto codificate in base64. Scegli un provider appropriato
ai dati trattati. Il backend non visita le pagine annuncio inserite dall’utente. Recupera soltanto
le immagini pubbliche: massimo 4 MB ciascuna, JPEG/PNG/WebP/AVIF, fino a sei. Le immagini
sono validate, limitate a 20 megapixel e normalizzate a JPEG entro 1600×1600 pixel. Ogni
connessione è fissata a un IP pubblico dopo controllo DNS; i redirect sono
ricontrollati e non si usano cookie o proxy. Le foto irraggiungibili vengono
segnalate come non esaminate; resta disponibile la valutazione testuale.
Questa conversione permette di usare anche Ollama, che non accetta URL remoti
come immagini nell’endpoint compatibile.

Se l’AI manca o fallisce, gli annunci rimangono in **Da verificare**, senza giudizi
sostitutivi. Il pulsante “Valuta in attesa” riprova i candidati senza rifare la raccolta.
Gli errori non contengono chiavi o corpi di risposta del provider.
Il limite per esecuzione dà precedenza agli annunci pubblicati più recentemente;
se la data manca o non è valida usa la prima rilevazione, senza inventare una data.

## 3. Fonti

### Manuale

Inserisci titolo, descrizione e foto di cui puoi disporre. L’URL della pagina è un
riferimento e non viene automaticamente visitato. Non inserire dati sensibili nei
campi pubblicabili. Il budget e gli annunci non vanno committati nel repository.
I valori di spedizione/commissioni vuoti significano **sconosciuto**; 0 significa
costo effettivamente nullo. Senza tutti i costi non si assegna convenienza.

### Subito

`BUYWATCHER_ENABLE_SUBITO=true` abilita esplicitamente il connettore originale.
Verifica prima che il tuo utilizzo sia consentito. La ricerca resta circoscritta
alla provincia di Verona, una pagina per parola chiave, richieste distanziate.
Non sono introdotti login automatizzati, aggiramento di CAPTCHA o rotazione proxy.
Il formato HTML è esterno e può cambiare: cambi di struttura sono errori, non
ricerche vuote. Gli errori per keyword sono visibili nei report.

Il connettore conserva la descrizione e le immagini presenti nei risultati;
non garantisce la descrizione completa o tutta la galleria della pagina dettaglio.
Per dati non presenti usa l’inserimento manuale. Prezzi non riconosciuti e costi
mancanti non sono stimati dall’AI. Il filtro comune confronta il comune effettivo;
lascia vuoto per tutta la provincia. Il campo località del topic per questa fonte
va quindi compilato con il nome del comune, non un raggio o testo generico.

### eBay

Imposta `EBAY_CLIENT_ID` e `EBAY_CLIENT_SECRET` del tuo account sviluppatore.
Il connettore usa OAuth client credentials, Browse search e getItem su `EBAY_IT`.
OAuth e dettagli live non sono stati collaudati senza credenziali reali.

Le capacità sono distinte:

- Credenziali: ricerca e recupero dettagli dalla Browse API.
- `EBAY_ANALYSIS_ALLOWED=true`: abilita analisi AI dopo aver verificato che
  termini e autorizzazioni coprano il tuo utilizzo.
- Analisi prezzi eBay: non attiva; richiede un futuro percorso autorizzato.
  I suoi annunci non producono punteggi di convenienza.

Gli annunci eBay sono isolati visivamente e quelli verificati oltre sei ore prima
non vengono ripubblicati dal feed; aggiorna la ricerca per visualizzarli nuovamente.
Non usiamo Marketplace Insights né presupponiamo accesso alle vendite concluse.
Non usiamo contenuti eBay per addestrare modelli. Verifica conservazione,
visualizzazione e inferenza per il tuo caso d’uso prima di pubblicare il servizio.

Fonti ufficiali, consultate il 21 ottobre 2026:
- https://developer.ebay.com/develop/api/buy
- https://developer.ebay.com/join/api-license-agreement
- https://ebaypartnernetwork.ebay.com/page/developer-questionnaire

### Fonti future

Vinted, Wallapop e Astrosell sono mostrate come **non attive**. Non ci sono endpoint
privati travestiti da API pubbliche. Vinted vieta scraping non autorizzato;
Astrosell richiede autorizzazione scritta per accesso automatizzato. Aggiungere
un sito al catalogo non lo rende un’integrazione funzionante.

- https://www.vinted.it/terms-and-conditions
- https://www.astrosell.it/condizioni_utilizzo.php
- https://about.wallapop.com/it/termini-e-condizioni-duso-di-wallapop/

## 4. Valutazione e suoi limiti

L’AI estrae pertinenza e fatti con schema validato. Non stabilisce un prezzo di
mercato a memoria. Una violazione di un requisito o pertinenza sotto soglia esclude
l’annuncio dai consigliati; requisiti non verificati, condizioni sconosciute,
parti mancanti, rischi, confidenza bassa e
dati vecchi oltre 72 ore lo spostano in Da verificare. L’assenza da una ricerca non
viene interpretata come una vendita.

La convenienza richiede costo totale in EUR, prezzo fisso, modello/configurazione
identificati, condizioni note, nessun componente indispensabile mancante e almeno
3 offerte indipendenti equivalenti valutate con confidenza >=70. Confrontiamo
condizione e venditore professionale/privato; foto identiche o lo stesso nome
venditore non contano come confronti indipendenti. Non c’è ancora riconoscimento
percettivo delle foto né raggruppamento certo di inserzioni duplicate tra siti.

Riferimento = mediana dei costi totali comparabili. Punteggio = 50 + percentuale
di risparmio rispetto al riferimento, limitato a 0–100. Rischi o confidenza bassa
limitano il punteggio a 59. “Potenziale affare” richiede almeno 75. Le soglie sono
iniziali, **non calibrate su un dataset reale**. I confronti sono offerte attive,
non transazioni concluse, e non determinano un valore certificato.

Le foto possono documentare dettagli visibili; non provano il funzionamento.
Le osservazioni fotografiche richiedono un indice di una foto effettivamente
allegata al modello. Questa validazione non dimostra che il modello l’abbia
interpretata correttamente. Prima del rilascio operativo valuta un campione di
annunci con giudizi umani per categoria.

## 5. Sviluppo locale

```sh
python3 -m venv .venv
.venv/bin/pip install -r webapp/requirements.txt
npm ci --prefix webapp/frontend
npm run build --prefix webapp/frontend
cd webapp
../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8081
```

Carica le variabili nel processo (o usa Docker Compose con `.env`); il server Python
non carica automaticamente `.env`. Con UI Vite usa `npm run dev` da
`webapp/frontend`; proxy `/api` e `/health` verso `http://localhost:8081`.

## 6. Protezione e ripristino

L’app conserva il modello originario di autenticazione esterna: non ha login
interno. La porta Compose è legata a localhost. Mantieni Authentik/reverse proxy
prima di esporla ad altri; non pubblicare direttamente la porta applicativa.

`GET /health` controlla accesso al database e segnala se l’AI è configurata;
non certifica accesso live alle fonti né qualità dell’AI. Usa report esecuzioni e
risultati per la verifica funzionale. Per rollback ripristina immagine precedente
e backup coerente del database, senza cancellare il volume.

Per healthcheck Coolify di tipo CMD usa `python /app/healthcheck.py`: non richiede curl o wget.

Per risposte JSON con Qwen3-VL usa un tag esplicito Instruct, ad esempio `qwen3-vl:4b-instruct`; il tag generico può puntare alla variante Thinking e consumare il limite senza produrre una risposta finale.
