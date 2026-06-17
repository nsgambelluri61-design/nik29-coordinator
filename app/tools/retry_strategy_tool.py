"""
retry_strategy_tool.py - Tool cognitivo di gestione errori per nik29-coordinator.

Analizza errori e suggerisce approcci alternativi basandosi su un registro
di errori noti e soluzioni. Impara dai fallimenti passati.

Azioni:
  - analyze_error: Dato un errore, suggerisce approcci alternativi
  - log_failure: Registra un fallimento per evitarlo in futuro
"""

import json
import os
import re
from datetime import datetime
from difflib import SequenceMatcher

# Path persistenza
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
ERROR_REGISTRY_FILE = os.path.join(MEMORY_DIR, "error_registry.json")

# Strategie generiche per tipi di errore comuni
GENERIC_STRATEGIES = {
    "timeout": [
        "Aumenta il timeout",
        "Riprova con backoff esponenziale",
        "Verifica che il servizio sia raggiungibile"
    ],
    "permission": [
        "Verifica i permessi del file/directory",
        "Esegui con sudo se appropriato",
        "Controlla l'ownership del file"
    ],
    "connection": [
        "Verifica che il servizio sia attivo",
        "Controlla la configurazione di rete",
        "Riprova dopo qualche secondo"
    ],
    "not_found": [
        "Verifica il path/URL",
        "Controlla che la risorsa esista",
        "Verifica la configurazione"
    ],
    "memory": [
        "Riduci la dimensione dell'operazione",
        "Libera memoria prima di riprovare",
        "Processa in batch più piccoli"
    ],
    "syntax": [
        "Verifica la sintassi del codice/comando",
        "Controlla encoding e caratteri speciali",
        "Valida l'input prima dell'esecuzione"
    ],
}

# --- TOOL DEFINITION (OpenAI function calling) ---
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "retry_strategy",
        "description": "Tool cognitivo di gestione errori. Analizza errori e suggerisce approcci alternativi basandosi su errori passati. Impara dai fallimenti.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["analyze_error", "log_failure"],
                    "description": "Azione: 'analyze_error' per suggerimenti, 'log_failure' per registrare"
                },
                "error_message": {
                    "type": "string",
                    "description": "Messaggio di errore da analizzare"
                },
                "tool_name": {
                    "type": "string",
                    "description": "Nome del tool che ha generato l'errore"
                },
                "context": {
                    "type": "string",
                    "description": "Contesto in cui è avvenuto l'errore"
                },
                "solution": {
                    "type": "string",
                    "description": "Soluzione trovata (per action=log_failure, se nota)"
                }
            },
            "required": ["action"]
        }
    }
}


def _load_registry() -> dict:
    """Carica il registro errori."""
    try:
        if os.path.exists(ERROR_REGISTRY_FILE):
            with open(ERROR_REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"errors": [], "solutions": {}}


def _save_registry(data: dict):
    """Salva il registro errori."""
    os.makedirs(os.path.dirname(ERROR_REGISTRY_FILE), exist_ok=True)
    with open(ERROR_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _classify_error(error_message: str) -> str:
    """Classifica l'errore in una categoria."""
    error_lower = error_message.lower()

    if any(w in error_lower for w in ["timeout", "timed out", "etimedout"]):
        return "timeout"
    elif any(w in error_lower for w in ["permission", "eacces", "denied", "forbidden"]):
        return "permission"
    elif any(w in error_lower for w in ["connection", "econnrefused", "unreachable", "network"]):
        return "connection"
    elif any(w in error_lower for w in ["not found", "enoent", "no such", "404"]):
        return "not_found"
    elif any(w in error_lower for w in ["memory", "oom", "out of memory"]):
        return "memory"
    elif any(w in error_lower for w in ["syntax", "parse", "unexpected token"]):
        return "syntax"
    else:
        return "unknown"


def _find_similar_errors(error_message: str, registry: dict, threshold: float = 0.5) -> list:
    """Trova errori simili nel registro usando similarità testuale."""
    similar = []
    for entry in registry.get("errors", []):
        prev_error = entry.get("error_message", "")
        ratio = SequenceMatcher(None, error_message[:200].lower(), prev_error[:200].lower()).ratio()
        if ratio >= threshold:
            similar.append((entry, ratio))

    # Ordina per similarità decrescente
    similar.sort(key=lambda x: -x[1])
    return similar[:5]


class RetryStrategyTool:
    """Tool cognitivo di gestione errori intelligente."""

    def __init__(self):
        self.name = "retry_strategy"

    async def execute(self, action: str, **kwargs) -> str:
        """Esegue l'azione richiesta."""
        try:
            if action == "analyze_error":
                return await self._analyze_error(**kwargs)
            elif action == "log_failure":
                return await self._log_failure(**kwargs)
            else:
                return f"ERRORE: Azione '{action}' non supportata. Usa 'analyze_error' o 'log_failure'."
        except Exception as e:
            return f"ERRORE retry_strategy_tool: {str(e)}"

    async def _analyze_error(self, error_message: str = "", tool_name: str = "", context: str = "", **kwargs) -> str:
        """Analizza un errore e suggerisce approcci alternativi."""
        if not error_message:
            return "ERRORE: Parametro 'error_message' richiesto."

        registry = _load_registry()

        # Classifica l'errore
        error_type = _classify_error(error_message)

        # Cerca errori simili nel registro
        similar = _find_similar_errors(error_message, registry)

        # Costruisci suggerimenti
        output = f"ANALISI ERRORE:\n"
        output += f"- Tipo: {error_type}\n"
        output += f"- Tool: {tool_name or 'non specificato'}\n"
        output += f"- Errore: {error_message[:200]}\n\n"

        # Soluzioni da errori simili passati
        if similar:
            output += "SOLUZIONI DA ERRORI SIMILI:\n"
            for entry, ratio in similar[:3]:
                sol = entry.get("solution", "nessuna soluzione registrata")
                output += f"  - [{ratio:.0%} simile] {entry.get('error_message', '')[:80]}\n"
                output += f"    Soluzione: {sol}\n"
            output += "\n"

        # Strategie generiche
        strategies = GENERIC_STRATEGIES.get(error_type, [])
        if strategies:
            output += "STRATEGIE SUGGERITE:\n"
            for i, strategy in enumerate(strategies, 1):
                output += f"  {i}. {strategy}\n"
        else:
            output += "STRATEGIE GENERICHE:\n"
            output += "  1. Riprova l'operazione\n"
            output += "  2. Verifica i parametri di input\n"
            output += "  3. Controlla i log per dettagli\n"
            output += "  4. Prova un approccio alternativo\n"

        # Suggerimento retry
        output += f"\nRETRY CONSIGLIATO: "
        if error_type in ("timeout", "connection"):
            output += "Sì, con backoff (attendi 2-5 secondi)"
        elif error_type in ("permission", "not_found", "syntax"):
            output += "No, risolvi prima il problema sottostante"
        else:
            output += "Sì, max 2 tentativi"

        return output

    async def _log_failure(self, error_message: str = "", tool_name: str = "",
                           context: str = "", solution: str = "", **kwargs) -> str:
        """Registra un fallimento nel registro."""
        if not error_message:
            return "ERRORE: Parametro 'error_message' richiesto."

        registry = _load_registry()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "error_message": error_message[:500],
            "tool_name": tool_name or "unknown",
            "context": context[:200] if context else "",
            "solution": solution or "",
            "error_type": _classify_error(error_message)
        }

        registry["errors"].append(entry)

        # Mantieni solo gli ultimi 200 errori
        if len(registry["errors"]) > 200:
            registry["errors"] = registry["errors"][-200:]

        _save_registry(registry)

        return f"REGISTRATO: Errore di tipo '{entry['error_type']}' per tool '{entry['tool_name']}' salvato nel registro." + \
               (f" Soluzione annotata: {solution[:100]}" if solution else " Nessuna soluzione annotata.")


# --- Helper per uso esterno ---
def get_retry_context() -> str:
    """Restituisce info sugli errori recenti per il contesto."""
    registry = _load_registry()
    errors = registry.get("errors", [])

    if not errors:
        return ""

    recent = errors[-5:]
    recurring_types = {}
    for e in errors[-20:]:
        t = e.get("error_type", "unknown")
        recurring_types[t] = recurring_types.get(t, 0) + 1

    # Segnala solo se ci sono errori ricorrenti
    problematic = {k: v for k, v in recurring_types.items() if v >= 3}
    if problematic:
        return f"[RETRY] Errori ricorrenti: {problematic}"
    return ""
