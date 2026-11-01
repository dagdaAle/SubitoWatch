# ADR 009 — I topic si archiviano, non si cancellano

- Data: 01/11/2026
- Stato: proposta (scelta di Claude, da confermare)

## Contesto

Oggi `DELETE /api/topics/{id}` cancella il topic e a cascata valutazioni, preferiti ed esecuzioni.
In todo-app né i task né i gruppi si cancellano.

## Decisione

`POST /topics/{id}/archive` e `/restore` al posto del `DELETE`. Un topic archiviato non viene cercato dallo
scheduler, non compare nel Radar e resta consultabile con `?archived=true`.

## Perché

- Un bisogno torna: "telescopio" archiviato a ottobre può servire di nuovo in primavera, con il suo storico prezzi.
- Preferiti e scarti sono i dati da cui nasce il set di valutazione dell'AI: non vanno persi.

## Conseguenze

- Nome unico solo tra i topic non archiviati.
- Il DB cresce senza pulizia: va bene alla scala di un utente; se servirà, una pulizia degli annunci vecchi
  non collegati a preferiti.
