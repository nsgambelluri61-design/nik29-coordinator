"""
reminder_tool.py - Tool cognitivo di task scheduling per nik29-coordinator.

Gestisce promemoria con data/ora, supporta linguaggio naturale per le date.
Controlla promemoria scaduti per notificare il coordinator.

Azioni:
  - add: Aggiunge un promemoria con testo e data/ora
  - list: Elenca promemoria attivi
  - complete: Segna un promemoria come completato
  - check_due: Controlla se ci sono promemoria scaduti
"""

import json
import os
import re
from datetime import datetime, timedelta

# Path persistenza
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
REMINDERS_FILE = os.path.join(MEMORY_DIR, "reminders.json")

# --- TOOL DEFINITION (OpenAI function calling) ---
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "reminder",
        "description": "Tool cognitivo di scheduling. Gestisce promemoria con data/ora (ISO 8601 o linguaggio naturale come 'domani', 'tra 2 ore').",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "complete", "check_due"],
                    "description": "Azione: 'add', 'list', 'complete', o 'check_due'"
                },
                "text": {
                    "type": "string",
                    "description": "Testo del promemoria (per action=add)"
                },
                "due": {
                    "type": "string",
                    "description": "Data/ora scadenza: ISO 8601 o naturale ('domani', 'tra 2 ore', 'lunedì')"
                },
                "reminder_id": {
                    "type": "string",
                    "description": "ID del promemoria (per action=complete)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Priorità del promemoria (default: medium)"
                }
            },
            "required": ["action"]
        }
    }
}


def _load_reminders() -> dict:
    """Carica i promemoria salvati."""
    try:
        if os.path.exists(REMINDERS_FILE):
            with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"reminders": []}


def _save_reminders(data: dict):
    """Salva i promemoria."""
    os.makedirs(os.path.dirname(REMINDERS_FILE), exist_ok=True)
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _parse_natural_date(text: str) -> datetime:
    """
    Converte espressioni di data naturali in datetime.
    Supporta: 'domani', 'tra X ore/minuti/giorni', 'dopodomani', 'lunedì', ecc.
    Fallback: prova ISO 8601.
    """
    now = datetime.now()
    text_lower = text.lower().strip()

    # ISO 8601
    try:
        return datetime.fromisoformat(text_lower.replace("Z", "+00:00").replace("z", "+00:00"))
    except (ValueError, TypeError):
        pass

    # "tra X ore/minuti/giorni/settimane"
    match = re.match(r"tra\s+(\d+)\s+(or[ae]|minut[oi]|giorn[oi]|settiman[ae]|mes[ei])", text_lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if "or" in unit:
            return now + timedelta(hours=amount)
        elif "minut" in unit:
            return now + timedelta(minutes=amount)
        elif "giorn" in unit:
            return now + timedelta(days=amount)
        elif "settiman" in unit:
            return now + timedelta(weeks=amount)
        elif "mes" in unit:
            return now + timedelta(days=amount * 30)

    # "in X hours/minutes/days"
    match = re.match(r"in\s+(\d+)\s+(hour|minute|day|week|month)s?", text_lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "hour":
            return now + timedelta(hours=amount)
        elif unit == "minute":
            return now + timedelta(minutes=amount)
        elif unit == "day":
            return now + timedelta(days=amount)
        elif unit == "week":
            return now + timedelta(weeks=amount)
        elif unit == "month":
            return now + timedelta(days=amount * 30)

    # Parole chiave
    if text_lower in ("domani", "tomorrow"):
        return now + timedelta(days=1)
    elif text_lower in ("dopodomani", "day after tomorrow"):
        return now + timedelta(days=2)
    elif text_lower in ("stasera", "tonight"):
        return now.replace(hour=21, minute=0, second=0)
    elif text_lower in ("stamattina", "this morning"):
        return now.replace(hour=9, minute=0, second=0)
    elif text_lower in ("tra poco", "soon"):
        return now + timedelta(minutes=30)
    elif text_lower in ("prossima settimana", "next week"):
        return now + timedelta(weeks=1)

    # Giorni della settimana
    days_it = {"lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3,
               "venerdì": 4, "sabato": 5, "domenica": 6}
    for day_name, day_num in days_it.items():
        if day_name in text_lower:
            days_ahead = day_num - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return now + timedelta(days=days_ahead)

    # Fallback: 1 ora da adesso
    return now + timedelta(hours=1)


def _generate_reminder_id() -> str:
    """Genera un ID univoco per il promemoria."""
    return f"rem_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class ReminderTool:
    """Tool cognitivo di task scheduling."""

    def __init__(self):
        self.name = "reminder"

    async def execute(self, action: str, **kwargs) -> str:
        """Esegue l'azione richiesta."""
        try:
            if action == "add":
                return await self._add(**kwargs)
            elif action == "list":
                return await self._list(**kwargs)
            elif action == "complete":
                return await self._complete(**kwargs)
            elif action == "check_due":
                return await self._check_due(**kwargs)
            else:
                return f"ERRORE: Azione '{action}' non supportata. Usa 'add', 'list', 'complete', o 'check_due'."
        except Exception as e:
            return f"ERRORE reminder_tool: {str(e)}"

    async def _add(self, text: str = "", due: str = "", priority: str = "medium", **kwargs) -> str:
        """Aggiunge un nuovo promemoria."""
        if not text:
            return "ERRORE: Parametro 'text' richiesto per aggiungere un promemoria."

        # Parse della data
        if due:
            due_dt = _parse_natural_date(due)
        else:
            due_dt = datetime.now() + timedelta(hours=1)  # Default: tra 1 ora

        reminder_id = _generate_reminder_id()

        reminder = {
            "id": reminder_id,
            "text": text,
            "due": due_dt.isoformat(),
            "priority": priority,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "completed_at": None
        }

        data = _load_reminders()
        data["reminders"].append(reminder)
        _save_reminders(data)

        return f"PROMEMORIA AGGIUNTO:\n" \
               f"  ID: {reminder_id}\n" \
               f"  Testo: {text}\n" \
               f"  Scadenza: {due_dt.strftime('%Y-%m-%d %H:%M')}\n" \
               f"  Priorità: {priority}"

    async def _list(self, **kwargs) -> str:
        """Elenca i promemoria attivi."""
        data = _load_reminders()
        active = [r for r in data["reminders"] if r["status"] == "active"]

        if not active:
            return "Nessun promemoria attivo."

        # Ordina per scadenza
        active.sort(key=lambda r: r.get("due", ""))

        output = f"PROMEMORIA ATTIVI ({len(active)}):\n"
        now = datetime.now()

        for r in active:
            due_dt = datetime.fromisoformat(r["due"])
            is_overdue = due_dt < now
            status_icon = "⚠️ SCADUTO" if is_overdue else "⏳"
            priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(r["priority"], "")

            output += f"  {priority_icon} [{r['id']}] {r['text']}\n"
            output += f"     Scadenza: {due_dt.strftime('%Y-%m-%d %H:%M')} {status_icon}\n"

        return output

    async def _complete(self, reminder_id: str = "", **kwargs) -> str:
        """Segna un promemoria come completato."""
        if not reminder_id:
            return "ERRORE: Parametro 'reminder_id' richiesto."

        data = _load_reminders()

        for r in data["reminders"]:
            if r["id"] == reminder_id:
                if r["status"] == "completed":
                    return f"Promemoria '{reminder_id}' già completato."
                r["status"] = "completed"
                r["completed_at"] = datetime.now().isoformat()
                _save_reminders(data)
                return f"COMPLETATO: Promemoria '{reminder_id}' segnato come completato."

        return f"ERRORE: Promemoria '{reminder_id}' non trovato."

    async def _check_due(self, **kwargs) -> str:
        """Controlla se ci sono promemoria scaduti."""
        data = _load_reminders()
        now = datetime.now()

        active = [r for r in data["reminders"] if r["status"] == "active"]
        overdue = []

        for r in active:
            try:
                due_dt = datetime.fromisoformat(r["due"])
                if due_dt <= now:
                    overdue.append(r)
            except (ValueError, TypeError):
                continue

        if not overdue:
            return "Nessun promemoria scaduto."

        # Ordina per priorità (high prima)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        overdue.sort(key=lambda r: priority_order.get(r.get("priority", "medium"), 1))

        output = f"⚠️ PROMEMORIA SCADUTI ({len(overdue)}):\n"
        for r in overdue:
            due_dt = datetime.fromisoformat(r["due"])
            delta = now - due_dt
            hours_late = delta.total_seconds() / 3600

            output += f"  [{r['priority'].upper()}] {r['text']}\n"
            output += f"    Scaduto da: {hours_late:.1f} ore (ID: {r['id']})\n"

        return output


# --- Helper per uso esterno ---
def get_reminder_context() -> str:
    """Restituisce info sui promemoria scaduti per il contesto del coordinator."""
    data = _load_reminders()
    now = datetime.now()

    active = [r for r in data.get("reminders", []) if r.get("status") == "active"]
    overdue = []

    for r in active:
        try:
            due_dt = datetime.fromisoformat(r["due"])
            if due_dt <= now:
                overdue.append(r)
        except (ValueError, TypeError):
            continue

    if overdue:
        texts = [r["text"][:50] for r in overdue[:3]]
        return f"[REMINDER] {len(overdue)} promemoria scaduti: {'; '.join(texts)}"
    return ""
