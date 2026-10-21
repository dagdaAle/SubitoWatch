# BuyWatcher

Radar personale dell’usato organizzato per **bisogni di acquisto**. Ogni topic
contiene uso previsto, requisiti, preferenze, budget totale e ricerche. I candidati
passano attraverso una valutazione AI di pertinenza, condizioni e foto disponibili
prima di entrare nei risultati consigliati.

React + TypeScript + FastAPI + SQLite. Un processo applicativo e una coda di lavoro
in background, adatta a un’installazione personale dietro autenticazione esterna.

## Funzioni

- Crea e modifica topic manualmente o rivedi una proposta preparata dall’AI.
- Aggrega annunci normalizzati; conserva provenienza, versioni e storico prezzi.
- Separa pertinenza, convenienza e confidenza. Evidenze fotografiche e dichiarazioni
  del venditore restano distinte. Foto non analizzate e informazioni mancanti sono visibili.
- La convenienza è calcolata deterministicamente su almeno tre offerte indipendenti
  equivalenti, con costi totali noti. I prezzi richiesti non sono prezzi di vendita.
- Annunci non valutati, incerti o incompatibili hanno viste distinte. Preferiti e
  scarti appartengono al topic. Nessun punteggio viene inventato senza un modello.
- Ricerca in background, report degli errori per fonte, cache delle valutazioni,
  invalidazione su modifica del topic/modello/dati, recupero dopo riavvio.
- Importa una volta i vecchi canali e preferiti in topic in pausa, senza cancellare
  le tabelle originali. Le API MCP precedenti restano disponibili.

## Fonti

| Fonte | Stato |
|---|---|
| Inserimento manuale | Testo e URL pubblici di foto forniti dall’utente; nessun fetch arbitrario |
| Subito | Connettore esistente, attivazione esplicita, Verona, una pagina per ricerca |
| eBay | Connettore Browse API; credenziali e permessi analisi separati |
| Vinted, Wallapop, Astrosell | Catalogo di fonti future, nessuna raccolta automatica attiva |

I risultati eBay sono visualizzati in una sezione distinta; i loro dati non alimentano
confronti economici tra fonti. L’API ufficiale non concede automaticamente il diritto
a qualsiasi elaborazione. Vedi [SETUP.md](SETUP.md) per capacità, vincoli e impostazioni.

## Avvio

```sh
cp .env.example .env
# Imposta il provider AI e abilita solo le fonti verificate.
docker compose up -d --build
```

Apri <http://localhost:8081>. Il Dockerfile ricompila il frontend dal sorgente.
Il volume storico `subito-data`, il percorso `/data/subito.db` e la chiave del
servizio Compose restano compatibili con SubitoWatch. Non usare `down -v`.

## Verifica

```sh
python3 -m venv .venv
.venv/bin/pip install -r webapp/requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
npm ci --prefix webapp/frontend
npm run build --prefix webapp/frontend
```

I test non contattano marketplace o provider AI: verificano migrazioni, contratti,
pertinenza, cache, errori, evidenze, confronti, concorrenza e API con dati sintetici.
Il funzionamento e la qualità di un provider reale vanno verificati dopo la sua
configurazione. Non sono inclusi account, credenziali o ricerche personali.
