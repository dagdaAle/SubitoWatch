# ADR 008 — LLM dietro un endpoint compatibile OpenAI

- Data: 01/11/2026 (in produzione dal 21/10/2026)
- Stato: accettata per l'interfaccia; la scelta del provider è **aperta**

## Contesto

La valutazione manda all'LLM bisogno, testo dell'annuncio e fino a 6 foto. Sul server c'è una RTX 3060
con Ollama; i provider remoti sono più bravi ma ricevono quei dati.

## Decisione

- Un client unico verso `POST /chat/completions` con `json_schema`, `temperature=0`, configurato da
  `BUYWATCHER_AI_*`. Modello testuale e modello visione separati.
- Le foto vengono scaricate e normalizzate dal backend e inviate in base64 (Ollama non accetta URL remoti).
- La firma del modello entra nella chiave di cache: cambiare modello rimette in coda le valutazioni.

## Perché

- Cambiare provider è un cambio di variabili, non di codice.
- Il confronto tra modelli si fa con `scripts/eval_ai` sugli stessi casi.

## Conseguenze

- Per Qwen3-VL va usato un tag Instruct esplicito (es. `qwen3-vl:4b-instruct`), il tag generico può
  rispondere con la variante Thinking.
- Locale o remoto resta una domanda aperta di PRODUCT.md.
