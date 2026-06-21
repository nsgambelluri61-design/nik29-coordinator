"""
conversation_summary_tool.py - Tool cognitivo di gestione contesto per nik29-coordinator.

Riassume conversazioni lunghe in punti chiave per mantenere il contesto
senza superare i limiti di token. Salva riassunti per conversation_id.

Azioni:
  - summarize: Riassume la conversazione corrente in punti chiave
  - get_summary: Restituisce il riassunto attuale per una conversazione
"""

import json
import os
from datetime import datetime

# Path persistenza
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
SUMMARIES_FILE = os.path.join(MEMORY_DIR, "summaries.json")

# --- TOOL DEFINITION (OpenAI function calling) ---
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "conversation_summary",
        "description": "Tool cognitivo di gestione contesto. Riassume conversazioni lunghe in punti chiave per mantenere il contesto senza superare i limiti di token.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["summarize", "get_summary"],
                    "description": "Azione: 'summarize' per creare riassunto, 'get_summary' per recuperarlo"
                },
                "conversation_id": {
                    "type": "string",
                    "description": "ID della conversazione"
                },
                "messages": {
                    "type": "string",
                    "description": "Testo dei messaggi da riassumere (per action=summarize)"
                },
                "key_points": {
                    "type": "string",
                    "description": "Punti chiave aggiuntivi da includere nel riassunto"
                }
            },
            "required": ["action"]
        }
    }
}


def _load_summaries() -> dict:
    """Carica i riassunti salvati."""
    try:
        if os.path.exists(SUMMARIES_FILE):
            with open(SUMMARIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"conversations": {}}


def _save_summaries(data: dict):
    """Salva i riassunti."""
    os.makedirs(os.path.dirname(SUMMARIES_FILE), exist_ok=True)
    with open(SUMMARIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _extract_key_points(messages: str) -> list:
    """Estrae punti chiave dal testo dei messaggi."""
    points = []

    # Dividi in frasi/righe significative
    lines = [l.strip() for l in messages.split("\n") if l.strip()]

    # Filtra righe significative (non troppo corte, non solo punteggiatura)
    significant = [l for l in lines if len(l) > 15]

    # Identifica richieste utente (pattern comuni)
    for line in significant:
        lower = line.lower()
        # Richieste dirette
        if any(w in lower for w in ["vorrei", "puoi", "fammi", "crea", "modifica",
                                     "aggiorna", "controlla", "dimmi", "spiega"]):
            points.append(f"RICHIESTA: {line[:150]}")
        # Decisioni prese
        elif any(w in lower for w in ["ho deciso", "facciamo", "procedi", "ok",
                                       "confermo", "va bene", "approvo"]):
            points.append(f"DECISIONE: {line[:150]}")
        # Informazioni importanti
        elif any(w in lower for w in ["importante", "nota", "attenzione", "ricorda"]):
            points.append(f"NOTA: {line[:150]}")

    # Se non abbiamo trovato abbastanza punti, prendi le prime righe significative
    if len(points) < 3 and significant:
        for line in significant[:5]:
            if line not in [p.split(": ", 1)[-1] for p in points]:
                points.append(f"CONTESTO: {line[:150]}")
            if len(points) >= 5:
                break

    return points[:10]  # Max 10 punti chiave


class ConversationSummaryTool:
    """Tool cognitivo di gestione contesto lungo."""

    def __init__(self):
        self.name = "conversation_summary"

    async def execute(self, action: str, **kwargs) -> str:
        """Esegue l'azione richiesta."""
        try:
            if action == "summarize":
                return await self._summarize(**kwargs)
            elif action == "get_summary":
                return await self._get_summary(**kwargs)
            else:
                return f"ERRORE: Azione '{action}' non supportata. Usa 'summarize' o 'get_summary'."
        except Exception as e:
            return f"ERRORE conversation_summary_tool: {str(e)}"

    async def _summarize(self, conversation_id: str = "", messages: str = "",
                         key_points: str = "", **kwargs) -> str:
        """Riassume la conversazione in punti chiave."""
        if not conversation_id:
            conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if not messages:
            return "ERRORE: Parametro 'messages' richiesto per creare un riassunto."

        # Estrai punti chiave
        auto_points = _extract_key_points(messages)

        # Aggiungi punti chiave manuali se forniti
        if key_points:
            manual = [p.strip() for p in key_points.split(";") if p.strip()]
            auto_points.extend([f"MANUALE: {p}" for p in manual])

        # Crea/aggiorna il riassunto
        summaries = _load_summaries()

        existing = summaries["conversations"].get(conversation_id, {})
        prev_points = existing.get("key_points", [])

        # Merge: mantieni i vecchi punti + aggiungi i nuovi (dedup)
        all_points = prev_points + [p for p in auto_points if p not in prev_points]
        # Mantieni solo gli ultimi 20 punti
        all_points = all_points[-20:]

        summary_entry = {
            "conversation_id": conversation_id,
            "updated_at": datetime.now().isoformat(),
            "message_count": existing.get("message_count", 0) + len(messages.split("\n")),
            "key_points": all_points,
            "last_topic": auto_points[0] if auto_points else "non determinato"
        }

        summaries["conversations"][conversation_id] = summary_entry

        # Mantieni solo le ultime 50 conversazioni
        if len(summaries["conversations"]) > 50:
            sorted_convs = sorted(
                summaries["conversations"].items(),
                key=lambda x: x[1].get("updated_at", ""),
                reverse=True
            )
            summaries["conversations"] = dict(sorted_convs[:50])

        _save_summaries(summaries)

        # Output
        output = f"RIASSUNTO CONVERSAZIONE '{conversation_id}':\n"
        output += f"Messaggi processati: {summary_entry['message_count']}\n"
        output += f"Punti chiave ({len(all_points)}):\n"
        for i, point in enumerate(all_points, 1):
            output += f"  {i}. {point}\n"

        return output

    async def _get_summary(self, conversation_id: str = "", **kwargs) -> str:
        """Restituisce il riassunto di una conversazione."""
        summaries = _load_summaries()

        if not conversation_id:
            # Restituisci l'ultimo riassunto
            convs = summaries.get("conversations", {})
            if not convs:
                return "Nessun riassunto disponibile."
            # Prendi il più recente
            latest = max(convs.items(), key=lambda x: x[1].get("updated_at", ""))
            conversation_id = latest[0]

        entry = summaries.get("conversations", {}).get(conversation_id)
        if not entry:
            available = list(summaries.get("conversations", {}).keys())
            return f"Nessun riassunto per '{conversation_id}'. Disponibili: {available[:10]}"

        output = f"RIASSUNTO '{conversation_id}' (aggiornato: {entry.get('updated_at', 'N/A')[:16]}):\n"
        output += f"Messaggi totali: {entry.get('message_count', 0)}\n"
        output += f"Ultimo topic: {entry.get('last_topic', 'N/A')}\n"
        output += f"\nPUNTI CHIAVE:\n"
        for i, point in enumerate(entry.get("key_points", []), 1):
            output += f"  {i}. {point}\n"

        return output


# --- Helper per uso esterno ---
def get_summary_context(conversation_id: str = "") -> str:
    """Restituisce il riassunto per il contesto del coordinator."""
    summaries = _load_summaries()
    convs = summaries.get("conversations", {})

    if conversation_id and conversation_id in convs:
        entry = convs[conversation_id]
        points = entry.get("key_points", [])[-5:]
        if points:
            return "CONTESTO CONVERSAZIONE:\n" + "\n".join(f"- {p}" for p in points)

    return ""
