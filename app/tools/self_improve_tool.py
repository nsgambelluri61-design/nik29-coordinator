"""
self_improve_tool.py - Tool per auto-miglioramento di nik29-coordinator v0.5.1

Permette a nik29 di:
- Riflettere sui task completati e salvare lezioni apprese
- Gestire regole auto-imposte per migliorare il comportamento
- Rivedere e ottimizzare le proprie regole nel tempo
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

# Importa le funzioni di memoria v2
try:
    from app.memory_v2 import (
        save_lesson,
        _load_json_safe,
        _save_json_safe,
        SELF_RULES_FILE,
        VALID_CATEGORIES
    )
except ImportError:
    from memory_v2 import (
        save_lesson,
        _load_json_safe,
        _save_json_safe,
        SELF_RULES_FILE,
        VALID_CATEGORIES
    )


# Definizione tool per OpenAI function calling
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "self_improve",
        "description": "Strumento di auto-miglioramento. Permette di riflettere sui task, gestire regole comportamentali e migliorare nel tempo.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["reflect", "get_rules", "add_rule", "review_rules"],
                    "description": "Azione da eseguire: 'reflect' per analizzare un task completato, 'get_rules' per leggere le regole attuali, 'add_rule' per aggiungere una regola, 'review_rules' per rivedere tutte le regole"
                },
                "task_summary": {
                    "type": "string",
                    "description": "Riassunto del task completato (richiesto per 'reflect')"
                },
                "rule": {
                    "type": "string",
                    "description": "Testo della regola (richiesto per 'add_rule')"
                },
                "reason": {
                    "type": "string",
                    "description": "Motivazione della regola (richiesto per 'add_rule')"
                }
            },
            "required": ["action"]
        }
    }
}


class SelfImproveTool:
    """Tool per auto-miglioramento e riflessione."""

    def __init__(self):
        self.name = "self_improve"

    async def execute(self, action: str, **kwargs) -> str:
        """
        Esegue l'azione richiesta.
        
        Args:
            action: Una tra "reflect", "get_rules", "add_rule", "review_rules"
            **kwargs: Parametri aggiuntivi specifici per l'azione
        
        Returns:
            Stringa con il risultato dell'azione
        """
        try:
            if action == "reflect":
                return await self._reflect(kwargs.get("task_summary", ""))
            elif action == "get_rules":
                return await self._get_rules()
            elif action == "add_rule":
                return await self._add_rule(
                    kwargs.get("rule", ""),
                    kwargs.get("reason", "")
                )
            elif action == "review_rules":
                return await self._review_rules()
            else:
                return f"❌ Azione non riconosciuta: '{action}'. Usa: reflect, get_rules, add_rule, review_rules"
        except Exception as e:
            return f"❌ Errore in self_improve/{action}: {str(e)}"

    async def _reflect(self, task_summary: str) -> str:
        """
        Riflette su un task completato e salva una lezione.
        Analizza cosa è andato bene/male e genera una lezione appresa.
        """
        if not task_summary.strip():
            return "❌ Fornisci un riassunto del task (task_summary) per la riflessione."

        # Determina la categoria in base al contenuto
        summary_lower = task_summary.lower()

        if any(w in summary_lower for w in ["errore", "sbagliato", "fallito", "bug", "problema"]):
            category = "errore"
        elif any(w in summary_lower for w in ["risolto", "soluzione", "fixato", "funziona"]):
            category = "soluzione"
        elif any(w in summary_lower for w in ["preferisce", "vuole", "piace", "stile"]):
            category = "preferenza"
        else:
            category = "procedura"

        # Salva come lezione
        result = await save_lesson(
            category=category,
            lesson=task_summary,
            context=f"Riflessione automatica del {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

        return f"🪞 Riflessione completata:\n{result}\n\nCategoria assegnata: {category}"

    async def _get_rules(self) -> str:
        """Restituisce tutte le regole auto-imposte attive."""
        data = _load_json_safe(SELF_RULES_FILE, {"rules": []})
        rules = data.get("rules", [])

        if not rules:
            return "📋 Nessuna regola auto-imposta al momento. Usa 'add_rule' per aggiungerne una."

        lines = [f"📋 Regole attive: {len(rules)}"]
        for i, r in enumerate(rules, 1):
            applied = f" (applicata {r['times_applied']}x)" if r.get("times_applied", 0) > 0 else ""
            lines.append(
                f"\n{i}. {r['rule']}"
                f"\n   Motivo: {r['reason']}"
                f"\n   ID: {r['id']} | Aggiunta: {r.get('added_date', r.get('date', 'N/A'))[:10]}{applied}"
            )

        return "\n".join(lines)

    async def _add_rule(self, rule: str, reason: str) -> str:
        """Aggiunge una nuova regola auto-imposta."""
        if not rule.strip():
            return "❌ Specifica il testo della regola."
        if not reason.strip():
            return "❌ Specifica la motivazione della regola."

        data = _load_json_safe(SELF_RULES_FILE, {"rules": []})

        # Controlla duplicati (ricerca approssimativa)
        rule_lower = rule.lower()
        for existing in data.get("rules", []):
            if rule_lower in existing.get("rule", "").lower() or existing.get("rule", "").lower() in rule_lower:
                return f"⚠️ Regola simile già esistente: '{existing['rule']}' (ID: {existing['id']})"

        new_rule = {
            "id": str(uuid.uuid4())[:8],
            "rule": rule.strip(),
            "reason": reason.strip(),
            "added_date": datetime.now().isoformat(),
            "times_applied": 0
        }

        data["rules"].append(new_rule)
        _save_json_safe(SELF_RULES_FILE, data)

        return f"✅ Nuova regola aggiunta (ID: {new_rule['id']}):\n📌 {rule}\n💡 Motivo: {reason}"

    async def _review_rules(self) -> str:
        """
        Rivede tutte le regole con statistiche d'uso.
        Suggerisce quali tenere e quali rimuovere.
        """
        data = _load_json_safe(SELF_RULES_FILE, {"rules": []})
        rules = data.get("rules", [])

        if not rules:
            return "📋 Nessuna regola da rivedere."

        lines = [f"📊 Revisione regole ({len(rules)} totali):"]
        lines.append("")

        # Classifica le regole
        never_used = []
        low_usage = []
        high_usage = []

        for r in rules:
            times = r.get("times_applied", 0)
            if times == 0:
                never_used.append(r)
            elif times < 3:
                low_usage.append(r)
            else:
                high_usage.append(r)

        if high_usage:
            lines.append("✅ REGOLE CONSOLIDATE (usate 3+ volte):")
            for r in high_usage:
                lines.append(f"  • {r['rule']} ({r['times_applied']}x)")

        if low_usage:
            lines.append("\n🔄 REGOLE IN RODAGGIO (usate 1-2 volte):")
            for r in low_usage:
                lines.append(f"  • {r['rule']} ({r['times_applied']}x)")

        if never_used:
            lines.append("\n⚠️ REGOLE MAI USATE (candidati per rimozione):")
            for r in never_used:
                # Calcola giorni dall'aggiunta
                try:
                    added = datetime.fromisoformat(r["added_date"])
                    days = (datetime.now() - added).days
                    lines.append(f"  • {r['rule']} (aggiunta {days} giorni fa) [ID: {r['id']}]")
                except (ValueError, KeyError):
                    lines.append(f"  • {r['rule']} [ID: {r['id']}]")

        lines.append(f"\n💡 Suggerimento: Considera di rimuovere le regole mai usate dopo 7+ giorni.")

        return "\n".join(lines)


# Funzione helper per incrementare l'uso di una regola
async def increment_rule_usage(rule_id: str) -> None:
    """Incrementa il contatore di applicazione di una regola."""
    data = _load_json_safe(SELF_RULES_FILE, {"rules": []})
    for rule in data.get("rules", []):
        if rule.get("id") == rule_id:
            rule["times_applied"] = rule.get("times_applied", 0) + 1
            _save_json_safe(SELF_RULES_FILE, data)
            return
