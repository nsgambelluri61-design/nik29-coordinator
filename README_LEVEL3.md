# Level 3 Autonomy Package — nik29-coordinator

## Panoramica

Questo pacchetto aggiunge **3 capacità fondamentali** a nik29-coordinator:

| Feature | Descrizione |
|---------|-------------|
| **Auto-Debug & Monitoring** | Controlla automaticamente lo stato dei sistemi ogni 5 minuti. Se qualcosa non va, prova a risolvere da solo. Se non riesce, ti avvisa su Telegram. |
| **Scheduled Tasks (Cron)** | Esegue task programmati: briefing mattutino, controllo sito ogni ora, report settimanale. Puoi aggiungere nuovi task via chat. |
| **Web Search & Browse** | nik29 può cercare su internet (Brave Search) e LEGGERE le pagine web. Può fare ricerche complete e riassumere i risultati. |

---

## Struttura File

```
nik29-coordinator/
├── app/
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── monitoring_tools.py    ← Health check, auto-debug, alert
│   │   ├── scheduler_tools.py     ← Gestione task programmati
│   │   └── web_tools.py           ← Brave Search, browse URL, research
│   ├── monitoring/
│   │   ├── __init__.py
│   │   └── monitor.py             ← Background monitor loop
│   └── scheduler/
│       ├── __init__.py
│       └── scheduler.py           ← APScheduler engine
├── data/
│   ├── monitoring/
│   │   └── health_log.json        ← Log di tutti i controlli
│   └── scheduler/
│       └── tasks.json             ← Task programmati
├── scripts/
│   └── install_level3.sh          ← Script di installazione
├── requirements_level3.txt        ← Dipendenze aggiuntive
├── PATCH_COORDINATOR.py           ← Istruzioni per coordinator.py
├── PATCH_DOCKER_COMPOSE.yml       ← Istruzioni per docker-compose.yml
└── README_LEVEL3.md               ← Questo file
```

---

## Installazione Rapida

### Prerequisiti

- nik29-coordinator già funzionante su porta 4001
- Host bridge attivo su porta 4003
- Telegram bot configurato (TELEGRAM_BOT_TOKEN nel .env)

### Passi

**1. Estrai lo ZIP nella directory del progetto:**

```bash
cd ~/nik29-coordinator
unzip ~/Downloads/nik29-level3.zip -d ~/nik29-level3-pkg
```

**2. Esegui lo script di installazione:**

```bash
cd ~/nik29-coordinator
~/nik29-level3-pkg/scripts/install_level3.sh
```

**3. Modifica `app/coordinator.py`** — aggiungi queste righe:

```python
# In cima, dopo gli import esistenti:
from app.tools.monitoring_tools import MONITORING_TOOLS, MONITORING_TOOL_HANDLERS
from app.tools.scheduler_tools import SCHEDULER_TOOLS, SCHEDULER_TOOL_HANDLERS
from app.tools.web_tools import WEB_TOOLS, WEB_TOOL_HANDLERS
from app.monitoring.monitor import create_monitor_task
from app.scheduler.scheduler import start_scheduler

# Dove definisci la lista TOOLS:
TOOLS.extend(MONITORING_TOOLS)
TOOLS.extend(SCHEDULER_TOOLS)
TOOLS.extend(WEB_TOOLS)

# Dove definisci TOOL_HANDLERS:
TOOL_HANDLERS.update(MONITORING_TOOL_HANDLERS)
TOOL_HANDLERS.update(SCHEDULER_TOOL_HANDLERS)
TOOL_HANDLERS.update(WEB_TOOL_HANDLERS)

# Nella funzione di startup (lifespan o @app.on_event("startup")):
monitor_task = create_monitor_task()
await start_scheduler()
```

**4. Modifica `docker-compose.yml`** — aggiungi:

```yaml
services:
  coordinator:
    environment:
      - BRAVE_API_KEY=${BRAVE_API_KEY:-}
      - MONITOR_SITE_URL=https://ildormire.com
      - HOST_BRIDGE_URL=http://host.docker.internal:4003
    volumes:
      - ./data/monitoring:/data/monitoring
      - ./data/scheduler:/data/scheduler
```

**5. Aggiungi la Brave API key al `.env`:**

```bash
echo 'BRAVE_API_KEY=la_tua_chiave_brave' >> .env
```

Per ottenere una chiave gratuita: https://brave.com/search/api/

**6. Rebuild e restart:**

```bash
docker compose build && docker compose up -d
```

---

## Come Funziona

### Monitoring Automatico

Ogni 5 minuti, nik29 controlla:
- Il sito ildormire.com risponde? (HTTP GET)
- I container Docker sono attivi? (via host bridge)
- Lo spazio disco è sufficiente? (< 85%)
- La memoria è ok?

Se qualcosa non va:
1. **Primo tentativo**: prova a risolvere da solo (restart container, ecc.)
2. **Secondo fallimento**: ti manda un messaggio Telegram di avviso
3. **Fallimenti ripetuti**: alert critico ogni 5 cicli (per non spammare)

### Task Programmati

3 task predefiniti:

| Task | Quando | Cosa fa |
|------|--------|---------|
| `morning_briefing` | Ogni giorno alle 9:00 | Manda su Telegram un riassunto dello stato |
| `site_health_check` | Ogni ora | Verifica che il sito risponda |
| `weekly_report` | Lunedì alle 9:00 | Report settimanale: uptime, errori, fix |

Puoi aggiungere task via chat con nik29:
> "Aggiungi un task che ogni giorno alle 20:00 mi manda un messaggio con lo stato del sito"

### Web Search

nik29 ora può:
- **Cercare su internet** con Brave Search
- **Leggere pagine web** estraendo il testo pulito
- **Fare ricerche complete** (cerca + legge + riassume)

Esempi di richieste:
> "Cerca le ultime novità sui materassi in memory foam"
> "Leggi questa pagina e dimmi cosa dice: https://..."
> "Fai una ricerca su come migliorare la SEO per e-commerce"

---

## Nuovi Tool Disponibili

Dopo l'installazione, nik29 ha questi nuovi tool:

| Tool | Descrizione |
|------|-------------|
| `health_check` | Controlla stato sistemi |
| `auto_debug` | Diagnosi e fix automatico |
| `send_alert` | Invia alert Telegram |
| `schedule_task` | Gestisci task programmati |
| `run_task_now` | Esegui un task subito |
| `brave_search` | Cerca sul web |
| `browse_url` | Leggi una pagina web |
| `web_research` | Ricerca completa (cerca + leggi) |

---

## Configurazione Avanzata

### Variabili d'Ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `BRAVE_API_KEY` | Chiave API Brave Search | (vuoto — search disabilitato) |
| `MONITOR_SITE_URL` | URL del sito da monitorare | `https://ildormire.com` |
| `HOST_BRIDGE_URL` | URL dell'host bridge | `http://host.docker.internal:4003` |
| `TELEGRAM_BOT_TOKEN` | Token del bot Telegram | (già configurato) |
| `TELEGRAM_ALLOWED_USER_ID` | Chat ID Telegram | `7072645786` |

### Intervallo Monitoring

Per cambiare l'intervallo di check (default 5 minuti), modifica in `app/monitoring/monitor.py`:

```python
MONITOR_INTERVAL = 300  # secondi (300 = 5 minuti)
```

### Log

Tutti i controlli e le azioni sono salvati in:
- `/data/monitoring/health_log.json` — ultimi 1000 eventi
- Il file viene automaticamente troncato per non crescere troppo

---

## Troubleshooting

**Il monitoring non parte:**
- Verifica che i volumi siano montati correttamente in Docker
- Controlla i log: `docker logs nik29-coordinator | grep monitor`

**Brave Search non funziona:**
- Verifica che `BRAVE_API_KEY` sia nel .env
- Ottieni una chiave gratuita su https://brave.com/search/api/

**Alert Telegram non arrivano:**
- Verifica `TELEGRAM_BOT_TOKEN` e `TELEGRAM_ALLOWED_USER_ID` nel .env
- Assicurati di aver avviato il bot (/start) su Telegram

**Host bridge non raggiungibile:**
- Verifica che il bridge sia attivo sulla porta 4003
- Controlla che `extra_hosts: host.docker.internal:host-gateway` sia nel docker-compose

---

## Versione

- **Package**: Level 3 Autonomy v1.0
- **Compatibile con**: nik29-coordinator (Python/FastAPI, Docker, gpt-4.1-mini)
- **Data**: Giugno 2025
