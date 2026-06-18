# Aggiornamento Memoria Persistente Automatica (v0.7.0)

Questo aggiornamento introduce il caricamento automatico della memoria persistente all'inizio di ogni nuova sessione e il salvataggio automatico di nuovi apprendimenti e riassunti al termine di ogni conversazione.

## File Modificati/Aggiunti

1. **`app/persistent_memory.py`** (NUOVO FILE)
   Questo è il nuovo modulo "motore" della memoria. Si occupa di leggere tutti i file JSON e Markdown dalla cartella `/data/memory/` in modo sicuro, generare i riassunti delle conversazioni recenti e fare l'estrazione automatica di nuovi fatti/preferenze dai messaggi utente.

2. **`app/coordinator.py`** (MODIFICATO)
   Il coordinatore è stato aggiornato per:
   - Includere un sistema di caching per la memoria (così non rilegge i file ad ogni singolo messaggio, ma solo all'inizio della sessione).
   - Iniettare il blocco `<persistent_memory>` nel system prompt.
   - Chiamare `persistent_memory.end_session()` al termine di ogni risposta per salvare eventuali nuovi apprendimenti o aggiornare il riassunto della conversazione.

## Come Installare l'Aggiornamento

Poiché usi Docker, l'installazione è molto semplice. Non è necessario modificare le dipendenze o i volumi, basta sostituire i file.

1. **Copia il nuovo file `persistent_memory.py`**
   Copia il file fornito dentro la cartella `app/` del tuo progetto nik29-coordinator.

2. **Sostituisci il file `coordinator.py`**
   Sostituisci il tuo attuale file `app/coordinator.py` con quello nuovo fornito.

3. **Ricostruisci il container Docker**
   Apri il terminale nella cartella del progetto (dove si trova `docker-compose.yml`) ed esegui:
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

## Come Funziona Ora

- **All'inizio di una nuova chat:** nik29 leggerà automaticamente `istruzioni.md`, `facts.json`, `preferences.json`, `lessons.json`, `self_rules.json` e un breve riassunto delle ultime 3 conversazioni. Saprà subito chi sei e di cosa avete parlato di recente.
- **Durante la chat:** Se gli dici esplicitamente cose come *"Ricordati che il mio numero è..."* o *"Preferisco che tu faccia..."*, il nuovo sistema di auto-save analizzerà il messaggio.
- **Alla fine della risposta:** nik29 salverà silenziosamente in background le nuove informazioni nei file `facts.json` o `preferences.json` (fino a 3 per sessione) e aggiornerà il file `summaries.json` con l'ultimo argomento discusso.

Tutto questo avviene senza che tu debba chiedere esplicitamente a nik29 di usare il tool `save_memory` o `conversation_summary`!
