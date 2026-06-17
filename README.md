# nik29-coordinator

**Agente coordinatore autonomo a 360° al servizio di Nicola.**

nik29 è un coordinatore AI universale che gira in Docker (porta 4001) con FastAPI + WebSocket + OpenAI function calling. A differenza di Maestro (che gestisce solo ildormire.com), nik29 è un agente UNIVERSALE che può fare tutto.

## Versione

**v0.6.0** - Release 17 Giugno 2026

## Caratteristiche

- **WebSocket non-bloccante**: chat real-time con aggiornamenti di progresso
- **OpenAI function calling**: loop autonomo con gpt-4.1-mini
- **18 tool nativi**: shell, web search, file manager, memoria, delegazione, Manus, create_tool, think, verify, retry_strategy, conversation_summary, reminder, self_improve, instructions, auto_update
- **Meta-tool create_tool**: crea nuovi tool a runtime con AI
- **Tool cognitivi**: pianificazione, verifica, retry intelligente
- **Self-improve**: lezioni apprese e regole auto-imposte
- **Auto-update**: aggiornamento automatico da GitHub
- **Sub-agenti**: architettura modulare con agenti specializzati

## Installazione

### Prerequisiti

- Docker e Docker Compose
- Chiave API OpenAI
- (Opzionale) Chiave API Manus

### Setup

```bash
# Clona il repository
git clone https://github.com/nsgambelluri61-design/nik29-coordinator.git
cd nik29-coordinator

# Configura l'ambiente
cp .env.example .env
# Modifica .env con le tue chiavi API

# Avvia
docker compose up -d --build
```

### Verifica

```bash
curl http://localhost:4001/health
```

## Struttura

```
nik29-coordinator/
├── docker-compose.yml          # Configurazione Docker
├── manifest.json               # Per auto-update (v0.6.0)
├── README.md                   # Questa documentazione
├── .env.example                # Template variabili ambiente
├── .gitignore
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI + WebSocket + Frontend
│   ├── coordinator.py          # Cervello: tool calling loop
│   ├── memory.py               # Memoria base: save/recall
│   ├── memory_v2.py            # Memoria strutturata: lessons, rules
│   ├── agent_client.py         # Client per sub-agenti
│   └── tools/
│       ├── __init__.py
│       ├── shell_tool.py       # Esecuzione comandi
│       ├── web_tool.py         # Ricerca web
│       ├── file_tool.py        # Gestione file
│       ├── delegate_tool.py    # Delega a sub-agenti
│       ├── manus_tool.py       # ask_manus (2 fasi)
│       ├── create_tool.py      # Meta-tool creazione tool
│       ├── think_tool.py       # Pianificazione step-by-step
│       ├── verify_tool.py      # Verifica risultati
│       ├── retry_strategy_tool.py
│       ├── conversation_summary_tool.py
│       ├── reminder_tool.py
│       ├── self_improve_tool.py
│       ├── instructions_tool.py
│       └── auto_update_tool.py
├── config/
│   └── system_prompt.txt       # System prompt completo
└── data/                       # Creato a runtime (gitignored)
    ├── memory/
    └── workspace/
```

## API Endpoints

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/` | GET | Frontend chat |
| `/health` | GET | Health check con versione |
| `/chat` | POST | REST API (SSE stream) |
| `/ws/{session_id}` | WS | WebSocket real-time |
| `/task/{task_id}` | GET | Status task asincroni |
| `/upload` | POST | Upload file |
| `/files/{path}` | GET | Serve file dal workspace |
| `/agents` | GET | Lista sub-agenti |
| `/agents/health` | GET | Stato sub-agenti |
| `/agents/reload` | POST | Ricarica configurazione agenti |

## Tool Disponibili

### Nativi
- **shell**: esecuzione comandi di sistema
- **web_search**: ricerca internet via DuckDuckGo
- **file_manager**: CRUD file nel workspace
- **delegate_task**: delega a sub-agenti
- **save_memory / recall_memory**: memoria persistente

### Manus Integration
- **ask_manus_propose**: prepara richiesta (richiede conferma)
- **ask_manus_execute**: esegue dopo conferma
- **ask_manus_pending**: lista richieste pendenti

### Meta-tool
- **create_tool_propose/generate/test/list**: crea nuovi tool a runtime

### Cognitivi
- **think**: pianificazione multi-step
- **verify**: verifica risultati
- **retry_strategy**: strategia retry intelligente
- **conversation_summary**: riassunto conversazioni
- **reminder**: promemoria con scheduling

### Self-improvement
- **self_improve**: rifletti, salva lezioni, gestisci regole
- **instructions**: gestione istruzioni personalizzate
- **auto_update**: aggiornamento automatico da GitHub

## Aggiornamento

```bash
# Controlla aggiornamenti
docker exec nik29-coordinator curl -s http://localhost:4001/health

# Aggiornamento manuale
cd nik29-coordinator
git pull
docker compose up -d --build
```

L'auto-update integrato può anche aggiornare il container dall'interno (con conferma utente).

## Sviluppo

```bash
# Installa dipendenze localmente
pip install -r requirements.txt

# Avvia in locale (senza Docker)
uvicorn app.main:app --host 0.0.0.0 --port 4001 --reload
```

## Licenza

Progetto privato - Nicola Sgambelluri / Sgambelluri srls
