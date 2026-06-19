"""
Client per comunicare con i sub-agenti registrati.
Gestisce il registro agenti e le chiamate HTTP.
"""
import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger("agent_client")

AGENTS_CONFIG = os.environ.get("AGENTS_CONFIG", "/data/memory/agents.json")
WORKSPACE_DIR = "/data/workspace"

DEFAULT_AGENTS = [
    {
        "name": "immagini",
        "description": "Agente immagini autonomo: analisi Vision, editing, scontorno, composizione, pipeline",
        "url": "http://nik29-images:4002",
        "capabilities": ["analyze", "edit", "remove_bg", "composite", "pipeline"]
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


def _resolve_file_to_base64(file_info: dict) -> Optional[dict]:
    """
    Converte un file (da URL locale o path) in formato base64
    compatibile con nik29-images /task endpoint.
    """
    name = file_info.get("name", "file.jpg")
    url = file_info.get("url", "")
    data = file_info.get("data", "")

    # Se ha gia' il campo data in base64, usalo direttamente
    if data:
        return {"name": name, "data": data}

    # Prova a risolvere il file dal workspace locale
    # URL tipo: http://localhost:4001/files/nomefile.jpg
    if "/files/" in url:
        filename = url.split("/files/")[-1]
        filepath = os.path.join(WORKSPACE_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"name": name, "data": b64}

    # Prova con il nome del file direttamente nel workspace
    filepath = os.path.join(WORKSPACE_DIR, name)
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return {"name": name, "data": b64}

    # Cerca qualsiasi file immagine recente nel workspace
    workspace = Path(WORKSPACE_DIR)
    if workspace.exists():
        image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        image_files = [
            f for f in workspace.iterdir()
            if f.suffix.lower() in image_extensions
        ]
        if image_files:
            # Prendi il piu' recente
            latest = max(image_files, key=lambda f: f.stat().st_mtime)
            with open(latest, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"name": latest.name, "data": b64}

    logger.warning(f"Impossibile risolvere file: {name} (url: {url})")
    return None


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

        # Converti i file in base64 per nik29-images
        resolved_files = []
        if files:
            for file_info in files:
                resolved = _resolve_file_to_base64(file_info)
                if resolved:
                    resolved_files.append(resolved)

        # Se non ci sono file risolti, cerca l'immagine piu' recente nel workspace
        if not resolved_files:
            workspace = Path(WORKSPACE_DIR)
            if workspace.exists():
                image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
                image_files = [
                    f for f in workspace.iterdir()
                    if f.suffix.lower() in image_extensions
                ]
                if image_files:
                    latest = max(image_files, key=lambda f: f.stat().st_mtime)
                    with open(latest, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    resolved_files.append({"name": latest.name, "data": b64})
                    logger.info(f"Auto-incluso file recente: {latest.name}")

        payload = {
            "instruction": instruction,
            "files": resolved_files
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
