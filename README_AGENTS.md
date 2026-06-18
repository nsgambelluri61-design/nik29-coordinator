# nik29-coordinator: Framework Multi-Agente

## Panoramica

Questo framework trasforma nik29-coordinator in un **coordinatore multi-agente**: può creare, gestire e delegare task ad agenti specialisti, ognuno con il proprio system prompt, tool e ruolo specifico.

### Architettura

```
┌─────────────────────────────────────────────────┐
│              nik29-coordinator                    │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │           AgentManager                    │   │
│  │                                           │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │   │
│  │  │agente_  │ │agente_  │ │agente_  │   │   │
│  │  │seo      │ │social   │ │catalogo │   │   │
│  │  └────┬────┘ └────┬────┘ └────┬────┘   │   │
│  │       │            │            │        │   │
│  │       ▼            ▼            ▼        │   │
│  │  [brave_search] [send_msg] [get_logs]   │   │
│  │  [web_research] [post_ig]  [edit_page]  │   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  Tool: create_agent | delegate_to_agent |        │
│        list_agents                               │
└─────────────────────────────────────────────────┘
```

## Contenuto del Package

| File | Descrizione |
|------|-------------|
| `app/agents/__init__.py` | Package init |
| `app/agents/agent_manager.py` | Classe AgentManager (cuore del sistema) |
| `app/agents/agent_tools.py` | Schema e handler dei 3 tool |
| `data/agents/agente_seo.json` | Agente SEO pre-configurato |
| `patch_agents.py` | Script di installazione automatica |
| `README_AGENTS.md` | Questo file |

## Installazione

### Prerequisiti

- Progetto nik29-coordinator-v0.6.0 funzionante
- Python 3.10+
- Docker e Docker Compose

### Procedura

**1. Estrai lo zip nella root del progetto:**

```bash
cd ~/Downloads/nik29-coordinator-v0.6.0
unzip nik29_agents_framework.zip
```

**2. Esegui il patch:**

```bash
python3 patch_agents.py
```

Lo script:
- Crea `data/agents/` (persistente via Docker volume)
- Copia i file del framework in `app/agents/`
- Installa l'agente SEO di esempio
- Patcha `coordinator.py` per registrare i nuovi tool
- Verifica l'installazione

**3. Ricostruisci e riavvia Docker:**

```bash
docker compose build
docker compose up -d
```

**4. Verifica:**

```bash
docker compose logs -f nik29 | grep AgentManager
# Dovresti vedere: [AgentManager] Inizializzato con 1 agenti
```

### Installazione Manuale (se il patch automatico fallisce)

Se `patch_agents.py` non riesce a modificare `coordinator.py` automaticamente, aggiungi manualmente:

**In cima al file (dopo gli altri import):**

```python
from app.agents import AgentManager
from app.agents.agent_tools import (
    ALL_AGENT_TOOL_SCHEMAS,
    handle_create_agent,
    handle_delegate_to_agent,
    handle_list_agents,
)
```

**Dopo la definizione di `_execute_tool`:**

```python
agent_manager = AgentManager(tool_executor=_execute_tool)
```

**Nel dispatcher `_execute_tool`, aggiungi i nuovi elif:**

```python
elif tool_name == "create_agent":
    return await handle_create_agent(args, agent_manager)
elif tool_name == "delegate_to_agent":
    return await handle_delegate_to_agent(args, agent_manager, all_tools_schemas=tools)
elif tool_name == "list_agents":
    return await handle_list_agents(args, agent_manager)
```

**Dopo la definizione della lista `tools`:**

```python
tools.extend(ALL_AGENT_TOOL_SCHEMAS)
```

## Utilizzo

### Via Telegram (linguaggio naturale)

Nik29 capirà automaticamente quando usare i tool multi-agente:

- **"Quali agenti hai?"** → chiama `list_agents`
- **"Analizza la SEO di ildormire.com"** → delega ad `agente_seo`
- **"Crea un agente per i social media"** → chiama `create_agent`
- **"Chiedi all'agente SEO di controllare il posizionamento per 'materassi siderno'"** → `delegate_to_agent`

### Via API diretta

```python
# Creare un agente
await handle_create_agent({
    "name": "agente_social",
    "role": "Social Media Manager per ildormire.com",
    "description": "Gestisce contenuti social",
    "capabilities": "Creazione post, pianificazione calendario editoriale, analisi engagement",
    "tools": "brave_search,send_telegram_message",
    "model": "gpt-4.1"
}, agent_manager)

# Delegare un task
await handle_delegate_to_agent({
    "agent_name": "agente_seo",
    "task": "Analizza il posizionamento di ildormire.com per la keyword 'materassi reggio calabria'",
    "context": "Ultimo check: 2 settimane fa, eravamo in posizione 15"
}, agent_manager, all_tools_schemas=tools)
```

## Tool Registrati

### create_agent

Crea un nuovo agente specialista. Nik29 genera automaticamente il system prompt basandosi su ruolo e capabilities.

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|:---:|-------------|
| name | string | ✅ | Nome univoco in snake_case |
| role | string | ✅ | Ruolo dell'agente |
| description | string | ✅ | Descrizione breve |
| capabilities | string | ✅ | Cosa sa fare |
| tools | string | ❌ | Tool separati da virgola |
| model | string | ❌ | Modello (default: gpt-4.1) |

### delegate_to_agent

Delega un task a un agente esistente. L'agente esegue il task con il suo system prompt e i suoi tool (max 5 iterazioni di tool calling).

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|:---:|-------------|
| agent_name | string | ✅ | Nome dell'agente |
| task | string | ✅ | Descrizione del task |
| context | string | ❌ | Contesto aggiuntivo |

### list_agents

Mostra tutti gli agenti disponibili con ruolo, descrizione, statistiche.

Nessun parametro richiesto.

## Agente SEO Pre-configurato

L'agente `agente_seo` è già pronto all'uso con:

- **Ruolo**: Specialista SEO per ildormire.com
- **Modello**: gpt-4.1
- **Tool**: brave_search, web_research, deep_research, browse_url
- **Keyword target**: materassi siderno, materassi reggio calabria, negozio materassi calabria, ecc.
- **Focus**: SEO locale provincia RC, e-commerce, Local SEO

### Esempi di task per l'agente SEO

1. "Controlla il posizionamento attuale per le keyword target"
2. "Analizza i competitor principali per 'materassi reggio calabria'"
3. "Suggerisci miglioramenti per la pagina categoria materassi"
4. "Verifica i Core Web Vitals di ildormire.com"
5. "Proponi una strategia di contenuti per il blog"

## Come Funziona il Delegate

Quando `delegate_to_agent` viene chiamato:

1. Carica il system prompt dell'agente
2. Costruisce il messaggio con task + contesto
3. Filtra i tool disponibili (solo quelli assegnati all'agente)
4. Chiama OpenAI chat.completions con il system prompt dell'agente
5. Se l'agente chiama un tool → esegue il tool → restituisce il risultato all'agente
6. Ripete il loop fino a risposta finale (max 5 iterazioni)
7. Restituisce la risposta dell'agente al coordinator

## Persistenza

Gli agenti sono salvati come file JSON in `data/agents/`:

```json
{
  "name": "agente_seo",
  "role": "Specialista SEO per ildormire.com",
  "system_prompt": "...",
  "tools": ["brave_search", "web_research"],
  "model": "gpt-4.1",
  "created_at": "2026-06-18T10:00:00Z",
  "last_used": "2026-06-18T15:30:00Z",
  "total_tasks": 12
}
```

La directory `data/` è montata come Docker volume, quindi gli agenti persistono tra restart del container.

## Creare Nuovi Agenti (Esempi)

### Agente Social Media

```
name: agente_social
role: Social Media Manager per ildormire.com
capabilities: Creazione contenuti per Instagram/Facebook, pianificazione calendario editoriale, analisi trend settore arredamento/benessere, copywriting persuasivo per e-commerce
tools: brave_search, web_research
```

### Agente Catalogo

```
name: agente_catalogo
role: Gestore Catalogo Prodotti ildormire.com
capabilities: Aggiornamento schede prodotto, ottimizzazione descrizioni, gestione prezzi, controllo disponibilità, generazione contenuti prodotto
tools: browse_url, web_research
```

### Agente Customer Care

```
name: agente_customer_care
role: Assistente Clienti per ildormire.com
capabilities: Risposta FAQ, informazioni prodotti, guida alla scelta materasso, gestione reclami, informazioni spedizioni e resi
tools: brave_search
```

## Troubleshooting

| Problema | Soluzione |
|----------|-----------|
| "AgentManager non inizializzato" | Verifica che `_init_agent_manager()` venga chiamato all'avvio |
| "Agente non trovato" | Controlla che il file JSON esista in `data/agents/` |
| "Tool non autorizzato" | Il tool deve essere nella lista `tools` dell'agente |
| "OpenAI API error" | Verifica OPENAI_API_KEY e OPENAI_API_BASE nel .env |
| "Max iterazioni raggiunto" | L'agente ha fatto 5 tool call senza dare risposta finale |
| Agente non usa i tool | Verifica che i tool siano registrati in `tools` (lista) dell'agente |

## Note Tecniche

- Le chiamate OpenAI usano `aiohttp` (coerente con il resto del progetto)
- Timeout di 120 secondi per chiamata OpenAI
- Temperature 0.3 per risposte consistenti
- Il tool_executor è la stessa funzione `_execute_tool` del coordinator
- Supporta sia `OPENAI_API_BASE` che il default `https://api.openai.com/v1`
