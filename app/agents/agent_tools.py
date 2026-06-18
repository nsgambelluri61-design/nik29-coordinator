"""
nik29-coordinator: Framework Multi-Agente
Tool definitions per il coordinator — create_agent, delegate_to_agent, list_agents.

Ogni tool ha:
- SCHEMA: dict OpenAI function calling format
- handler: funzione async che esegue il tool
"""

import json
from typing import Optional
from .agent_manager import AgentManager, generate_agent_system_prompt


# ============================================================
# TOOL SCHEMAS (formato OpenAI function calling)
# ============================================================

CREATE_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_agent",
        "description": "Crea un nuovo agente specialista nel sistema multi-agente. L'agente avrà il suo system prompt, i suoi tool e un ruolo specifico. Usa questo tool quando vuoi creare un assistente dedicato a un compito ricorrente.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome univoco dell'agente in snake_case (es. 'agente_seo', 'agente_social')"
                },
                "role": {
                    "type": "string",
                    "description": "Ruolo dell'agente (es. 'Specialista SEO per ildormire.com')"
                },
                "description": {
                    "type": "string",
                    "description": "Descrizione breve di cosa fa l'agente"
                },
                "capabilities": {
                    "type": "string",
                    "description": "Elenco dettagliato delle capacità dell'agente (cosa sa fare, in che ambito opera)"
                },
                "tools": {
                    "type": "string",
                    "description": "Lista di tool separati da virgola che l'agente può usare (es. 'brave_search,web_research,browse_url'). Lascia vuoto se l'agente non usa tool."
                },
                "model": {
                    "type": "string",
                    "description": "Modello OpenAI da usare (default: gpt-4.1). Opzioni: gpt-4.1, gpt-4.1-mini, gpt-4o"
                }
            },
            "required": ["name", "role", "description", "capabilities"]
        }
    }
}

DELEGATE_TO_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_to_agent",
        "description": "Delega un task a un agente specialista. L'agente eseguirà il compito usando il suo system prompt e i suoi tool, poi restituirà il risultato. Usa questo tool quando un task rientra nelle competenze di un agente esistente.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Nome dell'agente a cui delegare (usa list_agents per vedere quelli disponibili)"
                },
                "task": {
                    "type": "string",
                    "description": "Descrizione dettagliata del task da eseguire"
                },
                "context": {
                    "type": "string",
                    "description": "Contesto aggiuntivo utile per l'agente (es. dati precedenti, vincoli, preferenze)"
                }
            },
            "required": ["agent_name", "task"]
        }
    }
}

LIST_AGENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_agents",
        "description": "Mostra tutti gli agenti specialisti disponibili nel sistema con il loro ruolo, descrizione e statistiche di utilizzo.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

# Lista completa degli schema per registrazione rapida
ALL_AGENT_TOOL_SCHEMAS = [
    CREATE_AGENT_SCHEMA,
    DELEGATE_TO_AGENT_SCHEMA,
    LIST_AGENTS_SCHEMA,
]


# ============================================================
# TOOL HANDLERS (funzioni async che eseguono i tool)
# ============================================================

async def handle_create_agent(args: dict, agent_manager: AgentManager) -> str:
    """Handler per il tool create_agent."""
    name = args.get("name", "").strip().lower().replace(" ", "_")
    role = args.get("role", "")
    description = args.get("description", "")
    capabilities = args.get("capabilities", "")
    tools_str = args.get("tools", "")
    model = args.get("model", "gpt-4.1")

    if not name or not role:
        return "❌ Errore: 'name' e 'role' sono obbligatori."

    # Parse lista tool
    tools = [t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else []

    # Genera system prompt automaticamente
    system_prompt = generate_agent_system_prompt(name, role, capabilities, tools)

    try:
        agent = agent_manager.create_agent(
            name=name,
            role=role,
            system_prompt=system_prompt,
            tools=tools,
            model=model,
            description=description,
            capabilities=capabilities,
        )
        return (
            f"✅ Agente '{name}' creato con successo!\n"
            f"- Ruolo: {role}\n"
            f"- Modello: {model}\n"
            f"- Tool: {', '.join(tools) if tools else 'nessuno'}\n"
            f"- Descrizione: {description}\n"
            f"\nUsa `delegate_to_agent` per assegnargli un task."
        )
    except ValueError as e:
        return f"❌ Errore: {e}"
    except Exception as e:
        return f"❌ Errore imprevisto nella creazione dell'agente: {e}"


async def handle_delegate_to_agent(
    args: dict,
    agent_manager: AgentManager,
    all_tools_schemas: Optional[list] = None,
) -> str:
    """Handler per il tool delegate_to_agent."""
    agent_name = args.get("agent_name", "").strip()
    task = args.get("task", "")
    context = args.get("context", "")

    if not agent_name or not task:
        return "❌ Errore: 'agent_name' e 'task' sono obbligatori."

    # Verifica che l'agente esista
    agent = agent_manager.get_agent(agent_name)
    if not agent:
        available = [a["name"] for a in agent_manager.list_agents()]
        return (
            f"❌ Agente '{agent_name}' non trovato.\n"
            f"Agenti disponibili: {', '.join(available) if available else 'nessuno'}"
        )

    # Delega il task
    result = await agent_manager.delegate(
        agent_name=agent_name,
        task=task,
        context=context if context else None,
        available_tools_schemas=all_tools_schemas,
    )

    return f"📋 **Risposta da {agent_name}** ({agent['role']}):\n\n{result}"


async def handle_list_agents(args: dict, agent_manager: AgentManager) -> str:
    """Handler per il tool list_agents."""
    agents = agent_manager.list_agents()

    if not agents:
        return "📋 Nessun agente specialista configurato. Usa `create_agent` per crearne uno."

    lines = [f"📋 **Agenti Specialisti Disponibili** ({len(agents)} totale):\n"]
    for a in agents:
        tools_str = ", ".join(a["tools"]) if a["tools"] else "nessuno"
        last_used = a["last_used"] or "mai"
        lines.append(
            f"### {a['name']}\n"
            f"- **Ruolo**: {a['role']}\n"
            f"- **Descrizione**: {a.get('description', '-')}\n"
            f"- **Modello**: {a['model']}\n"
            f"- **Tool**: {tools_str}\n"
            f"- **Ultimo uso**: {last_used}\n"
            f"- **Task completati**: {a['total_tasks']}\n"
        )

    return "\n".join(lines)
