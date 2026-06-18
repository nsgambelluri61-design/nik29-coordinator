"""
nik29-coordinator: Framework Multi-Agente
AgentManager — Gestione centralizzata degli agenti specialisti.
"""

import os
import json
import time
import aiohttp
from typing import Optional, Dict, List, Any
from pathlib import Path

# Directory persistente per gli agenti (montata via Docker volume)
AGENTS_DIR = Path(os.environ.get("AGENTS_DATA_DIR", "/app/data/agents"))

# OpenAI config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")

# Max iterazioni tool-calling per agente delegato
MAX_AGENT_ITERATIONS = 5


class AgentManager:
    """Gestisce la creazione, persistenza e delegazione verso agenti specialisti."""

    def __init__(self, tool_executor=None):
        """
        Args:
            tool_executor: funzione async(tool_name, args) -> str che esegue i tool di nik29.
        """
        self._agents: Dict[str, dict] = {}
        self._tool_executor = tool_executor
        self._ensure_data_dir()
        self._load_all_agents()

    def _ensure_data_dir(self):
        """Crea la directory agents se non esiste."""
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_all_agents(self):
        """Carica tutti gli agenti salvati da disco."""
        self._agents = {}
        if not AGENTS_DIR.exists():
            return
        for f in AGENTS_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    agent = json.load(fp)
                    self._agents[agent["name"]] = agent
                    print(f"[AgentManager] Caricato agente: {agent['name']} ({agent['role']})")
            except Exception as e:
                print(f"[AgentManager] Errore caricamento {f.name}: {e}")
        print(f"[AgentManager] Totale agenti caricati: {len(self._agents)}")

    def _save_agent(self, agent: dict):
        """Salva un agente su disco."""
        filepath = AGENTS_DIR / f"{agent['name']}.json"
        with open(filepath, "w", encoding="utf-8") as fp:
            json.dump(agent, fp, indent=2, ensure_ascii=False)

    def create_agent(
        self,
        name: str,
        role: str,
        system_prompt: str,
        tools: Optional[List[str]] = None,
        model: str = "gpt-4.1",
        description: str = "",
        capabilities: str = "",
    ) -> dict:
        """
        Crea un nuovo agente specialista.

        Args:
            name: Identificativo univoco (snake_case)
            role: Ruolo dell'agente (es. "Specialista SEO")
            system_prompt: System prompt completo
            tools: Lista di nomi tool che l'agente può usare
            model: Modello OpenAI (default gpt-4.1)
            description: Descrizione breve
            capabilities: Cosa sa fare l'agente

        Returns:
            dict con i dati dell'agente creato
        """
        if name in self._agents:
            raise ValueError(f"Agente '{name}' già esistente. Usa delete_agent prima di ricrearlo.")

        agent = {
            "name": name,
            "role": role,
            "description": description,
            "capabilities": capabilities,
            "system_prompt": system_prompt,
            "tools": tools or [],
            "model": model,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "last_used": None,
            "total_tasks": 0,
        }

        self._agents[name] = agent
        self._save_agent(agent)
        print(f"[AgentManager] Creato agente: {name} (role: {role}, model: {model})")
        return agent

    def list_agents(self) -> List[dict]:
        """Restituisce la lista di tutti gli agenti con info sintetiche."""
        result = []
        for agent in self._agents.values():
            result.append({
                "name": agent["name"],
                "role": agent["role"],
                "description": agent.get("description", ""),
                "model": agent["model"],
                "tools": agent["tools"],
                "created_at": agent["created_at"],
                "last_used": agent.get("last_used"),
                "total_tasks": agent.get("total_tasks", 0),
            })
        return result

    def get_agent(self, name: str) -> Optional[dict]:
        """Restituisce i dati completi di un agente."""
        return self._agents.get(name)

    def delete_agent(self, name: str) -> bool:
        """
        Rimuove un agente dal sistema.

        Returns:
            True se rimosso, False se non trovato.
        """
        if name not in self._agents:
            return False

        del self._agents[name]
        filepath = AGENTS_DIR / f"{name}.json"
        if filepath.exists():
            filepath.unlink()
        print(f"[AgentManager] Rimosso agente: {name}")
        return True

    async def delegate(
        self,
        agent_name: str,
        task: str,
        context: Optional[str] = None,
        available_tools_schemas: Optional[List[dict]] = None,
    ) -> str:
        """
        Delega un task a un agente specialista.

        Esegue una conversazione con l'agente, gestendo eventuali tool call
        in un loop (max MAX_AGENT_ITERATIONS iterazioni).

        Args:
            agent_name: Nome dell'agente a cui delegare
            task: Descrizione del task da eseguire
            context: Contesto aggiuntivo opzionale
            available_tools_schemas: Schema dei tool disponibili (formato OpenAI)

        Returns:
            Risposta finale dell'agente (stringa)
        """
        agent = self._agents.get(agent_name)
        if not agent:
            return f"❌ Errore: agente '{agent_name}' non trovato. Usa list_agents per vedere quelli disponibili."

        # Aggiorna statistiche
        agent["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        agent["total_tasks"] = agent.get("total_tasks", 0) + 1
        self._save_agent(agent)

        # Costruisci messaggi
        messages = [
            {"role": "system", "content": agent["system_prompt"]},
        ]

        user_content = f"## Task\n{task}"
        if context:
            user_content += f"\n\n## Contesto\n{context}"
        messages.append({"role": "user", "content": user_content})

        # Filtra tool schemas per quelli assegnati all'agente
        agent_tools = None
        if agent["tools"] and available_tools_schemas:
            agent_tools = [
                t for t in available_tools_schemas
                if t.get("function", {}).get("name") in agent["tools"]
            ]
            if not agent_tools:
                agent_tools = None

        print(f"[AgentManager] Delegando a '{agent_name}': {task[:80]}...")
        if agent_tools:
            print(f"[AgentManager] Tool disponibili per {agent_name}: {[t['function']['name'] for t in agent_tools]}")

        # Loop di esecuzione con tool calling
        for iteration in range(MAX_AGENT_ITERATIONS):
            try:
                response = await self._call_openai(
                    model=agent["model"],
                    messages=messages,
                    tools=agent_tools,
                )
            except Exception as e:
                return f"❌ Errore chiamata OpenAI per agente '{agent_name}': {e}"

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")

            # Se l'agente ha finito (nessun tool call)
            if finish_reason == "stop" or not message.get("tool_calls"):
                final_response = message.get("content", "")
                print(f"[AgentManager] Agente '{agent_name}' ha risposto (iter {iteration + 1})")
                return final_response

            # L'agente vuole chiamare tool
            tool_calls = message.get("tool_calls", [])
            messages.append(message)  # Aggiungi il messaggio con tool_calls

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                print(f"[AgentManager] Agente '{agent_name}' chiama tool: {tool_name}({tool_args})")

                # Verifica che il tool sia tra quelli assegnati
                if tool_name not in agent["tools"]:
                    tool_result = f"❌ Tool '{tool_name}' non autorizzato per questo agente."
                elif self._tool_executor:
                    try:
                        tool_result = await self._tool_executor(tool_name, tool_args)
                    except Exception as e:
                        tool_result = f"❌ Errore esecuzione tool '{tool_name}': {e}"
                else:
                    tool_result = f"❌ Nessun tool executor configurato."

                # Aggiungi il risultato del tool alla conversazione
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(tool_result) if tool_result else "OK",
                })

        return f"⚠️ Agente '{agent_name}' ha raggiunto il limite di {MAX_AGENT_ITERATIONS} iterazioni senza risposta finale."

    async def _call_openai(
        self,
        model: str,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
    ) -> dict:
        """Chiamata asincrona all'API OpenAI chat completions."""
        url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"OpenAI API error {resp.status}: {error_text[:500]}")
                return await resp.json()


# --- Funzioni helper per generare system prompt automaticamente ---

def generate_agent_system_prompt(name: str, role: str, capabilities: str, tools: List[str]) -> str:
    """
    Genera automaticamente un system prompt per un agente basandosi su ruolo e capabilities.
    """
    tools_section = ""
    if tools:
        tools_section = f"""
## Tool Disponibili
Hai accesso ai seguenti tool: {', '.join(tools)}.
Usali SEMPRE quando servono per completare il task. Preferisci chiamare un tool piuttosto che rispondere senza dati concreti.
"""

    prompt = f"""Sei {name}, un agente specialista con il ruolo di: {role}.

## Le Tue Capacità
{capabilities}

## Regole di Comportamento
1. Rispondi SEMPRE in italiano
2. Sii conciso ma completo
3. Fornisci dati concreti e actionable
4. Se non hai informazioni sufficienti, usa i tool disponibili per cercarle
5. Struttura le risposte in modo chiaro con sezioni e bullet point
6. Indica sempre le fonti quando possibile
{tools_section}
## Formato Risposta
Rispondi con un report strutturato che includa:
- Analisi/Risultati
- Raccomandazioni concrete
- Prossimi passi suggeriti
"""
    return prompt.strip()
