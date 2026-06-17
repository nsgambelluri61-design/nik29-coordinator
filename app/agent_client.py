"""
Client per comunicare con i sub-agenti registrati.
Gestisce il registro agenti e le chiamate HTTP.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("agent_client")

AGENTS_CONFIG = os.environ.get("AGENTS_CONFIG", "/data/memory/agents.json")

DEFAULT_AGENTS = [
    {
        "name": "immagini",
        "description": "Editing immagini: resize, scontorno, compressione, info",
        "url": "http://nik29-images:4000",
        "capabilities": ["resize", "remove_bg", "compress", "info", "convert"]
    }
]


class AgentRegistry:
    """Registro dei sub-agenti disponibili."""

    def __init__(self):
        self._agents: list = []
        self._load()

    def _load(self):
        """Carica la configurazione degli agenti."""
        if os.path.exists(AGENTS_CONFIG):
            try:
                with open(AGENTS_CONFIG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._agents = data.get("agents", [])
                    return
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        # Default
        self._agents = DEFAULT_AGENTS
        self._save()

    def _save(self):
        """Salva la configurazione degli agenti."""
        os.makedirs(os.path.dirname(AGENTS_CONFIG), exist_ok=True)
        with open(AGENTS_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"agents": self._agents}, f, ensure_ascii=False, indent=2)

    def list_agents(self) -> list:
        """Lista tutti gli agenti registrati."""
        return self._agents

    def get_agent(self, name: str) -> Optional[dict]:
        """Recupera un agente per nome."""
        for agent in self._agents:
            if agent["name"] == name:
                return agent
        return None

    def reload(self):
        """Ricarica la configurazione."""
        self._load()


class AgentClient:
    """Client HTTP per comunicare con i sub-agenti."""

    def __init__(self):
        self.registry = AgentRegistry()

    async def send_task(self, agent_name: str, instruction: str, files: list = None) -> str:
        """Invia un task a un sub-agente."""
        agent = self.registry.get_agent(agent_name)
        if not agent:
            return f"Agente '{agent_name}' non trovato. Agenti disponibili: {[a['name'] for a in self.registry.list_agents()]}"

        url = f"{agent['url']}/task"
        payload = {
            "instruction": instruction,
            "files": files or []
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("result", "Task completato senza risultato.")
                else:
                    return f"Errore dall'agente {agent_name}: HTTP {resp.status_code} - {resp.text[:200]}"
        except httpx.ConnectError:
            return f"Impossibile connettersi all'agente '{agent_name}' ({agent['url']}). Verifica che sia in esecuzione."
        except httpx.TimeoutException:
            return f"Timeout nella comunicazione con l'agente '{agent_name}'."
        except Exception as e:
            return f"Errore comunicazione con '{agent_name}': {str(e)}"

    async def check_all_agents_health(self) -> dict:
        """Controlla lo stato di salute di tutti gli agenti."""
        results = {}
        for agent in self.registry.list_agents():
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{agent['url']}/health")
                    results[agent["name"]] = resp.status_code == 200
            except Exception:
                results[agent["name"]] = False
        return results


# Singleton
agent_client = AgentClient()
