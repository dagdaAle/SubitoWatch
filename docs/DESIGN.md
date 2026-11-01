# DESIGN — come si presenta

> Stato: bozza del 01/11/2026. Il perché sta in [PRODUCT.md](PRODUCT.md), le API in [ARCHITECTURE.md](ARCHITECTURE.md).
> Non c'è ancora un progetto Stitch per BuyWatcher: le voci marcate **(scelta di Claude)** vanno confermate,
> idealmente su mockup prima del codice.

## Principi

1. **La decisione prima dell'elenco.** Aprendo un topic la prima cosa visibile è "c'è qualcosa da contattare?":
   i consigliati, con il motivo in una riga. Tutto il resto è un clic più in là.
2. **Il motivo è il contenuto.** Ogni annuncio dice *perché* è consigliato, da verificare o escluso.
   Il punteggio da solo non basta mai.
3. **Il non noto si vede.** Spedizione sconosciuta, foto non analizzata, taglia non dichiarata hanno un
   aspetto proprio, diverso da "ok" e da "problema". Mai uno zero o un segno di spunta al posto di un dato mancante.
4. **Testo e foto separati.** Ciò che dice il venditore e ciò che si vede nelle foto stanno in due blocchi distinti,
   con la foto citata accanto all'osservazione.
5. **Un gesto, un'azione.** Preferito, scarto, rivaluta: un clic, nessuna conferma per azioni reversibili,
   toast con "Annulla" (come todo-app).
6. **Calma.** Il verde è riservato ai "potenziali affari", il rosso agli errori delle fonti. Niente badge colorati
   per ogni campo.

## Base visiva **(scelta di Claude)**

Stesso design system di todo-app: **Lumina Workspace** (token in `todo-app/docs/stitch-design.md`), Mantine con
tema dai token, Inter per il testo, Outfit per i titoli, JetBrains Mono per prezzi e numeri.
Le app personali di Ale si somigliano: chi ne usa una sa usare le altre.

Differenze rispetto a todo-app:

- le **foto** sono il contenuto principale delle card: rapporto 4:3, angoli 4px, segnaposto neutro se manca;
- un colore d'accento in più per la **fonte** (Subito, Vinted, eBay, manuale): solo un puntino e il nome, non lo sfondo;
- i **prezzi** sono in monospace, allineati a destra, con il costo totale in evidenza e il prezzo richiesto sotto.

Il logo `◎` di oggi resta come base; il logo vero si fa insieme agli altri (nota `progetti/Logo - set di varianti e misure.md`).

## Layout

Come todo-app: barra laterale a sinistra su desktop, menu in basso su telefono.

```
┌───────────────┬──────────────────────────────────────────────────────────┐
│ ◎ BuyWatcher  │  Schede grafiche                    [Cerca ora] [⋯]      │
│               │  Bisogno: GPU per il server, max 250 € spedita           │
│ + Nuovo topic │  Ultima ricerca 06:00 · prossima 06:00 domani · Vinted ⚠ │
│               ├──────────────────────────────────────────────────────────┤
│ RADAR         │  Consigliati 3 · Da verificare 12 · Esclusi 41 · ★ 2     │
│ ● Schede gr. 3│  ┌────────┐ RTX 3060 12GB                    189,00 € ▸ │
│ ● Vans      1 │  │  foto  │ Pertinente: 12 GB, scatola, scontrino   +9 € │
│ ○ Telescopi   │  └────────┘ Subito · Verona · 2 giorni fa   ★  ✕        │
│               │  ...                                                     │
│ Fonti         │                                                          │
│ Taglie        │                                                          │
└───────────────┴──────────────────────────────────────────────────────────┘
```

- Nella barra laterale ogni topic mostra il numero di **consigliati nuovi** (non tutti gli annunci).
  Pallino pieno = attivo, vuoto = in pausa; gli archiviati stanno in fondo, chiusi.
- La testata del topic riassume il bisogno in una riga e lo stato delle fonti; un'icona ⚠ su una fonte
  apre il report dell'ultima esecuzione.

## Pagine

### 1. Radar (home)

Una riga per topic: nome, bisogno in breve, budget, consigliati nuovi, ultima e prossima ricerca, stato.
Ordinati per consigliati nuovi, poi per ultima attività. Su telefono è la prima schermata.

### 2. Topic

- **Schede**: Consigliati · Da verificare · Esclusi · Preferiti · Scartati, con i contatori.
  Si apre su Consigliati; se è vuota, su Da verificare con una riga che spiega perché.
- **Card annuncio**: foto, titolo, una riga di motivo, costo totale (o "spedizione non nota"), fonte, comune,
  età dell'annuncio, preferito e scarto. Sui potenziali affari: il risparmio rispetto al riferimento (es. "−18%").
- **Ordinamento**: punteggio di convenienza, poi pertinenza (come oggi); in alternativa più recenti e prezzo.
- **Filtro testo** e filtro per fonte.
- **Cerca anche su**: i link esterni (Vinted, eBay, Facebook) stanno in un menu della testata, non in un pannello fisso.
- **Esecuzione in corso**: barra sottile sotto la testata con fase e contatori ("Vinted: 18 annunci · valutati 7/18").

### 3. Annuncio (popup)

Come il task in todo-app: finestra centrata su desktop, a tutto schermo su telefono.

1. Galleria foto, con il numero di ogni foto (le osservazioni la citano).
2. Verdetto: vista, motivo, pertinenza, confidenza, convenienza, ciascuno con la sua spiegazione.
3. **Costo**: prezzo + spedizione + commissioni, con "non noto" dove manca; riferimento e offerte confrontate.
4. **Requisiti**: soddisfatti, violati, non verificati.
5. **Dal testo** (dichiarazioni del venditore) e **Dalle foto** (osservazioni con il numero della foto), separati.
6. Parti mancanti, rischi, **domande da fare al venditore** (copiabili con un clic).
7. Storico prezzi e date in cui è stato visto.
8. Link all'annuncio originale, preferito, scarto, "rivaluta".

### 4. Nuovo topic

1. Un solo campo grande: "Cosa ti serve?" con un esempio sotto
   (*"Una GPU per il server di casa, almeno 12 GB, max 250 € spedita"*).
2. "Proponi" chiama l'AI e mostra il topic compilato in sezioni modificabili: ricerche, requisiti, preferenze,
   esclusioni, budget, fonti, taglie.
3. "Crea" salva; la prima ricerca parte solo se Ale lo chiede.

Senza AI configurata si va direttamente al modulo, con il messaggio che spiega perché.

### 5. Fonti

Una card per fonte: stato (attiva, spenta, in errore), cosa è permesso (raccolta, analisi, prezzi),
ultimo errore e da quando, link ai termini. Sostituisce il pannello "Fonti" di oggi dentro il topic.

### 6. Taglie

Come oggi (`#personalizzazione`): numero di scarpe EU e taglie abbigliamento, con l'elenco dei topic che le
usano e l'avviso che salvarle rimette in coda le valutazioni di quei topic.

## Stati da progettare

- **Vuoto**: nessun topic (invito a scrivere il primo bisogno); topic senza annunci (non è ancora stata fatta una ricerca,
  oppure le fonti hanno fallito: dirlo).
- **AI non configurata**: tutto finisce in Da verificare; un banner lo dice una volta, non su ogni card.
- **Fonte in errore**: ⚠ in testata con il messaggio della fonte; gli annunci già raccolti restano.
- **Esecuzione interrotta** dopo un riavvio: messaggio e pulsante "Riprova".
- **Valutazione superata** (topic o modello cambiati): la card mostra "da rivalutare", non il vecchio giudizio.
- **Annuncio non più visto da 72 h**: card attenuata con "potrebbe essere venduto".
- **Caricamento**: scheletri delle card, mai la pagina bianca.

## Accessibilità

- Contrasto AA in tema chiaro e scuro; il significato non è mai affidato solo al colore
  (consigliato / da verificare / escluso hanno anche icona e testo).
- Preferito e scarto hanno `aria-label` e sono raggiungibili da tastiera; il popup intrappola il focus e si chiude con Esc.
- Le foto hanno come testo alternativo il titolo dell'annuncio e il numero della foto.
- Touch target di almeno 44 px su telefono.

## Prossimo passo

1. Creare un progetto Stitch "BuyWatcher" con il design system Lumina Workspace e generare le 4 schermate principali
   (Radar, Topic, Annuncio, Nuovo topic) su desktop e telefono.
2. Rivederle con Ale e aggiornare questo documento prima di scrivere il frontend (fase 4 di PRODUCT.md).
