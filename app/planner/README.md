# Planner Module — nik29-coordinator

Modulo di pianificazione autonoma che trasforma il tool-loop in un ciclo **think → plan → execute → verify** per task complessi, mantenendo invariato il flusso per task semplici.

## Architettura

```
Messaggio utente
       │
       ▼
┌─────────────────┐
│  classify_message│  ← euristiche (zero LLM calls)
│  SIMPLE/COMPLEX │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
 SIMPLE    COMPLEX
    │         │
    ▼         ▼
 [flusso   ┌──────────────┐
 esistente]│ TaskPlanner   │ ← 1 chiamata GPT-4.1 (temp 0.3)
           │ genera piano  │
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │ PlanExecutor  │ ← esegue step-by-step
           │ (riusa tool   │    con meta-istruzioni
           │  infrastruttura)│
           └──────┬───────┘
                  │
                  ▼
           [risposta finale con summary]
```

## File

| File | Descrizione |
|------|-------------|
| `__init__.py` | Package init (import shortcuts) |
| `planner.py` | Classificatore euristico + generatore piani LLM |
| `executor.py` | Esecutore step-by-step con safety limits |
| `patch_planner.py` | Script idempotente per patchare coordinator.py |
| `test_classifier.py` | Test suite per il classificatore |

## Installazione

```bash
# 1. Copia il modulo nella directory dell'app
cp -r /path/to/planner /app/planner/

# 2. Applica il patch al coordinator
python3 /app/planner/patch_planner.py

# 3. Verifica
python3 /app/planner/patch_planner.py --verify

# 4. (Opzionale) Rollback
python3 /app/planner/patch_planner.py --unpatch
```

## Classificazione (euristiche)

Il classificatore NON usa LLM — è istantaneo. Regole:

- **COMPLEX** se: multi-step esplicito + 2+ verbi d'azione
- **COMPLEX** se: ricerca + azione combinata ("cerca X e preparami Y")
- **COMPLEX** se: creazione complessa (sistema/modulo/agente/bot)
- **COMPLEX** se: messaggio > 200 chars + 3+ azioni
- **COMPLEX** se: 4+ verbi d'azione in qualsiasi messaggio
- **SIMPLE** per: saluti, conferme, domande brevi, comandi singoli

## Safety Limits

- Max **30 iterazioni tool** totali (tutti gli step combinati)
- Max **3 retry** per step fallito (poi skip + nota nel summary)
- Max **8 step** per piano (imposto nel prompt di pianificazione)
- **Auto-reflect** automatico se ci sono errori risolti

## Compatibilità

- Zero modifiche al flusso SIMPLE (fallthrough garantito)
- Riusa `_execute_tool`, `_progress_message`, `_safe_truncate_messages`
- Yield stessi event types: `progress`, `status`, `response`
- Auto-reflect e persistent_memory funzionano anche nel flusso COMPLEX
- Il patch è idempotente e reversibile
