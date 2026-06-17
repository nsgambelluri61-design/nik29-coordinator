"""
Modulo memoria persistente per nik29-coordinator.
Gestisce conversazioni, fatti, preferenze e log delegazioni.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("memory")

MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
CONVERSATIONS_DIR = os.path.join(MEMORY_DIR, "conversations")
FACTS_FILE = os.path.join(MEMORY_DIR, "facts.json")
PREFERENCES_FILE = os.path.join(MEMORY_DIR, "preferences.json")
DELEGATIONS_LOG = os.path.join(MEMORY_DIR, "delegations.json")


class Memory:
    """Gestisce la memoria persistente del coordinatore."""

    def __init__(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
        self._ensure_file(FACTS_FILE, {"facts": []})
        self._ensure_file(PREFERENCES_FILE, {"preferences": {}})
        self._ensure_file(DELEGATIONS_LOG, {"delegations": []})

    def _ensure_file(self, path: str, default: dict):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)

    def _read_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_json(self, path: str, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Conversazioni
    # ------------------------------------------------------------------

    def load_conversation(self, conversation_id: str) -> list:
        """Carica la cronologia di una conversazione."""
        path = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        if os.path.exists(path):
            data = self._read_json(path)
            return data.get("messages", [])
        return []

    def save_conversation(self, conversation_id: str, messages: list):
        """Salva la cronologia di una conversazione."""
        path = os.path.join(CONVERSATIONS_DIR, f"{conversation_id}.json")
        data = {
            "conversation_id": conversation_id,
            "messages": messages[-50:],  # Mantieni ultimi 50 messaggi
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self._write_json(path, data)

    # ------------------------------------------------------------------
    # Fatti e preferenze
    # ------------------------------------------------------------------

    def save_fact(self, fact: str, category: str = "general") -> str:
        """Salva un fatto nella memoria."""
        data = self._read_json(FACTS_FILE)
        facts = data.get("facts", [])
        entry = {
            "fact": fact,
            "category": category,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        facts.append(entry)
        # Mantieni ultimi 200 fatti
        data["facts"] = facts[-200:]
        self._write_json(FACTS_FILE, data)
        return f"Fatto salvato nella categoria '{category}'."

    def recall_facts(self, category: Optional[str] = None) -> list:
        """Recupera fatti dalla memoria."""
        data = self._read_json(FACTS_FILE)
        facts = data.get("facts", [])
        if category:
            facts = [f for f in facts if f.get("category") == category]
        return facts[-20:]  # Ultimi 20

    def save_preference(self, key: str, value: str) -> str:
        """Salva una preferenza."""
        data = self._read_json(PREFERENCES_FILE)
        prefs = data.get("preferences", {})
        prefs[key] = {
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        data["preferences"] = prefs
        self._write_json(PREFERENCES_FILE, data)
        return f"Preferenza '{key}' salvata."

    def get_preferences(self) -> dict:
        """Recupera tutte le preferenze."""
        data = self._read_json(PREFERENCES_FILE)
        return data.get("preferences", {})

    # ------------------------------------------------------------------
    # Contesto
    # ------------------------------------------------------------------

    def get_context_summary(self) -> str:
        """Genera un riassunto del contesto dalla memoria."""
        facts = self.recall_facts()
        prefs = self.get_preferences()

        lines = []
        if prefs:
            lines.append("Preferenze:")
            for k, v in list(prefs.items())[-5:]:
                lines.append(f"  - {k}: {v.get('value', '')}")

        if facts:
            lines.append("Fatti recenti:")
            for f in facts[-5:]:
                lines.append(f"  - [{f.get('category', 'general')}] {f.get('fact', '')}")

        return "\n".join(lines) if lines else "Nessun contesto in memoria."

    # ------------------------------------------------------------------
    # Log delegazioni
    # ------------------------------------------------------------------

    def log_delegation(self, agent_name: str, instruction: str, result: str, success: bool):
        """Logga una delegazione a un sub-agente."""
        data = self._read_json(DELEGATIONS_LOG)
        delegations = data.get("delegations", [])
        delegations.append({
            "agent": agent_name,
            "instruction": instruction[:200],
            "result": result[:500],
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        data["delegations"] = delegations[-100:]
        self._write_json(DELEGATIONS_LOG, data)


# Singleton
memory = Memory()
