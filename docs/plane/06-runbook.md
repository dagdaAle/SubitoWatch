Stato: bozza generata da agente · Aggiornato: 2026-11-16 · Fonte: dagdaAle/SubitoWatch@c7dbbda (main)

# Runbook

| Sintomo | Causa | Fix |
|---|---|---|
| Fonte Vinted `failed`: "Vinted ha rifiutato la richiesta" | 403/429 dal WAF anti-bot | Nessun nuovo tentativo per scelta. Aspetta e rilancia più tardi. Se persiste può essere bloccato l'IP di casa (anche il browser). Non aggiungere proxy o login (ADR-005) |
| Vinted trova 30 risultati ma tutti scartati ("Dettagli di un annuncio non recuperabili") | mapping rigido sulle varianti del catalogo (run 55–57 del 27/10/2026) | Fix in PR #7 (`fac8798`). Verificato il 02/11: 688 annunci Vinted in DB. Se torna: leggi `Listing enrich failed: source=vinted` nei log |
| Vinted smette di rispondere dopo un cambio | endpoint o cookie cambiati (già successo: `/api/v2` → `/svc-catalogue`) | Aggiorna il connettore e le fixture registrate |
| eBay `401 invalid_client` | App ID e Cert ID non dello stesso keyset, o keyset Production disabilitato | Ricopia entrambi dallo stesso box Production in Coolify, redeploy |
| eBay disabilita il keyset Production | manca l'iscrizione a Marketplace Account Deletion | Imposta `EBAY_VERIFICATION_TOKEN` e `EBAY_DELETION_ENDPOINT`, escludi `^/ebay/account-deletion$` da Authentik, registra URL e token su developer.ebay.com (SETUP.md §3). Fatto il 02/11/2026 |
| eBay: mail "Your eBay Application Keys have changed" (28/10) | chiavi ruotate da eBay | Controlla che i valori in Coolify siano quelli correnti. Stato attuale: DA VERIFICARE |
| Annunci eBay non valutati dall'AI | `EBAY_ANALYSIS_ALLOWED` non attivo | Verifica la variabile in Coolify (punto aperto dal 02/11) |
| Subito: ricerca in errore invece che vuota | l'HTML di Subito è cambiato | È voluto: un cambio di struttura è un errore. Aggiorna `sources/subito.py` |
| Valutazioni JSON vuote o troncate con Qwen3-VL | il tag generico punta alla variante Thinking e consuma `max_tokens` | Usa un tag Instruct esplicito (`qwen3-vl:...-instruct`) |
| Foto "non esaminate" | URL irraggiungibile, formato non supportato, oltre 4 MB o 20 MP | Normale. Resta la valutazione testuale |
| Tutto in "Da verificare" | AI non configurata o in errore | `/health` → `ai_configured`. Poi "Valuta in attesa" (`POST /topics/{id}/evaluate`) |
| Run `interrupted` | riavvio o deploy durante un run | Non si riprende da solo: rilancia dall'interfaccia |
| 409 `run_in_progress` | un run per quel topic è già attivo | Aspetta. Indice unico `bw_one_run` |
| Hermes crea un canale ma non si vede in BuyWatcher | l'MCP usa ancora le rotte `/channels` legacy | Usa la UI per i topic. Fix strutturale: piano 03 (MCP sui topic) |
| App sembra rotta dal browser | sessione Authentik scaduta (caso del 17/09/2026) | Nuovo login su Authentik |
| DB vuoto dopo un deploy | volume ricreato (`down -v` o nome progetto Compose cambiato) | Ripristina dal backup. Prevenzione: mai `down -v`, volume esterno con nome esplicito |
| Healthcheck Coolify fallisce con "curl not found" | healthcheck HTTP con curl | Usa il tipo CMD: `python /app/healthcheck.py` |
