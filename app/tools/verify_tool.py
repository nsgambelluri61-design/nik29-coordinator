"""
verify_tool.py - Tool cognitivo di auto-verifica per nik29-coordinator.

Verifica se un'azione eseguita ha prodotto il risultato atteso.
Analizza output cercando pattern di errore e genera report di verifica.

Azioni:
  - check: Verifica se un'azione è stata eseguita correttamente
  - report: Genera un report di verifica con statistiche
"""

import json
import os
import re
from datetime import datetime

# Path persistenza
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
VERIFY_STATS_FILE = os.path.join(MEMORY_DIR, "verify_stats.json")

# Pattern di errore da cercare (conservativo: meglio un falso WARNING che un falso OK)
ERROR_PATTERNS = [
    (r"traceback|Traceback", "FAILED", "Traceback Python rilevato"),
    (r"Error:|ERROR:|error:", "WARNING", "Pattern 'error' trovato nell'output"),
    (r"Exception:|exception:", "WARNING", "Eccezione rilevata"),
    (r"failed|FAILED|Failed", "WARNING", "Pattern 'failed' trovato"),
    (r"Permission denied|EACCES", "FAILED", "Errore di permessi"),
    (r"No such file|FileNotFoundError|ENOENT", "FAILED", "File non trovato"),
    (r"Connection refused|ECONNREFUSED", "FAILED", "Connessione rifiutata"),
    (r"Timeout|ETIMEDOUT|timeout", "WARNING", "Timeout rilevato"),
    (r"404|Not Found", "WARNING", "Risorsa non trovata (404)"),
    (r"500|Internal Server Error", "FAILED", "Errore server (500)"),
    (r"syntax error|SyntaxError", "FAILED", "Errore di sintassi"),
    (r"MemoryError|OOM|Out of memory", "FAILED", "Memoria esaurita"),
    (r"killed|SIGKILL|SIGTERM", "WARNING", "Processo terminato"),
    (r"null|None.*unexpected|undefined is not", "WARNING", "Valore null/undefined inatteso"),
]

# Pattern di successo
SUCCESS_PATTERNS = [
    r"success|SUCCESS|completato|done|OK|completed",
    r"created|updated|saved|uploaded",
    r"200|201|204",
]

# --- TOOL DEFINITION (OpenAI function calling) ---
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "verify",
        "description": "Tool cognitivo di auto-verifica. Analizza il risultato di un'azione per verificare se è corretto. Conservativo: preferisce WARNING a falsi OK.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check", "report"],
                    "description": "Azione: 'check' per verificare un risultato, 'report' per statistiche"
                },
                "tool_name": {
                    "type": "string",
                    "description": "Nome del tool che ha prodotto il risultato (per action=check)"
                },
                "result": {
                    "type": "string",
                    "description": "Output/risultato dell'azione da verificare (per action=check)"
                },
                "expected": {
                    "type": "string",
                    "description": "Risultato atteso, se noto (per action=check)"
                }
            },
            "required": ["action"]
        }
    }
}


def _load_stats() -> dict:
    """Carica le statistiche di verifica."""
    try:
        if os.path.exists(VERIFY_STATS_FILE):
            with open(VERIFY_STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"checks": [], "summary": {"ok": 0, "warning": 0, "failed": 0}}


def _save_stats(data: dict):
    """Salva le statistiche."""
    os.makedirs(os.path.dirname(VERIFY_STATS_FILE), exist_ok=True)
    with open(VERIFY_STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _analyze_result(result: str, expected: str = "") -> tuple:
    """
    Analizza il risultato cercando pattern di errore.
    Restituisce (status, reason).
    Conservativo: in caso di dubbio, WARNING.
    """
    if not result or not result.strip():
        return ("WARNING", "Risultato vuoto — potrebbe indicare un problema")

    # Controlla pattern di errore (dal più grave al meno grave)
    worst_status = "OK"
    worst_reason = "Nessun pattern di errore rilevato"

    for pattern, severity, reason in ERROR_PATTERNS:
        if re.search(pattern, result):
            if severity == "FAILED":
                return ("FAILED", reason)
            elif severity == "WARNING" and worst_status != "FAILED":
                worst_status = "WARNING"
                worst_reason = reason

    # Se c'è un expected, verifica che sia presente nel risultato
    if expected and expected.strip():
        if expected.lower() not in result.lower():
            if worst_status == "OK":
                worst_status = "WARNING"
                worst_reason = f"Risultato atteso '{expected[:50]}...' non trovato nell'output"

    # Controlla pattern di successo (solo se non ci sono errori)
    if worst_status == "OK":
        has_success = any(re.search(p, result, re.IGNORECASE) for p in SUCCESS_PATTERNS)
        if has_success:
            worst_reason = "Pattern di successo rilevato"

    return (worst_status, worst_reason)


class VerifyTool:
    """Tool cognitivo di auto-verifica."""

    def __init__(self):
        self.name = "verify"

    async def execute(self, action: str, **kwargs) -> str:
        """Esegue l'azione richiesta."""
        try:
            if action == "check":
                return await self._check(**kwargs)
            elif action == "report":
                return await self._report(**kwargs)
            else:
                return f"ERRORE: Azione '{action}' non supportata. Usa 'check' o 'report'."
        except Exception as e:
            return f"ERRORE verify_tool: {str(e)}"

    async def _check(self, tool_name: str = "", result: str = "", expected: str = "", **kwargs) -> str:
        """Verifica il risultato di un'azione."""
        if not result:
            return "WARNING: Nessun risultato fornito da verificare."

        # Analizza
        status, reason = _analyze_result(result, expected)

        # Registra nelle statistiche
        stats = _load_stats()
        check_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name or "unknown",
            "status": status,
            "reason": reason,
            "result_preview": result[:200]
        }
        stats["checks"].append(check_entry)

        # Mantieni solo gli ultimi 100 check
        if len(stats["checks"]) > 100:
            stats["checks"] = stats["checks"][-100:]

        # Aggiorna summary
        stats["summary"][status.lower()] = stats["summary"].get(status.lower(), 0) + 1
        _save_stats(stats)

        # Formatta output
        if status == "OK":
            return f"OK: {reason}"
        elif status == "WARNING":
            return f"WARNING: {reason}"
        else:
            return f"FAILED: {reason}"

    async def _report(self, **kwargs) -> str:
        """Genera un report di verifica."""
        stats = _load_stats()
        summary = stats.get("summary", {})
        checks = stats.get("checks", [])

        total = summary.get("ok", 0) + summary.get("warning", 0) + summary.get("failed", 0)

        report = "=== REPORT VERIFICA ===\n"
        report += f"Totale verifiche: {total}\n"
        report += f"  OK: {summary.get('ok', 0)}\n"
        report += f"  WARNING: {summary.get('warning', 0)}\n"
        report += f"  FAILED: {summary.get('failed', 0)}\n"

        if total > 0:
            success_rate = (summary.get("ok", 0) / total) * 100
            report += f"  Tasso successo: {success_rate:.1f}%\n"

        # Ultimi 5 check
        if checks:
            report += "\nULTIMI 5 CHECK:\n"
            for check in checks[-5:]:
                report += f"  [{check['status']}] {check['tool_name']} - {check['reason']} ({check['timestamp'][:16]})\n"

        # Tool problematici
        if checks:
            tool_failures = {}
            for check in checks:
                if check["status"] in ("WARNING", "FAILED"):
                    tn = check["tool_name"]
                    tool_failures[tn] = tool_failures.get(tn, 0) + 1
            if tool_failures:
                report += "\nTOOL PROBLEMATICI:\n"
                for tn, count in sorted(tool_failures.items(), key=lambda x: -x[1])[:5]:
                    report += f"  {tn}: {count} problemi\n"

        return report


# --- Helper per uso esterno ---
def get_verify_context() -> str:
    """Restituisce un riassunto delle verifiche recenti per il contesto."""
    stats = _load_stats()
    summary = stats.get("summary", {})
    total = summary.get("ok", 0) + summary.get("warning", 0) + summary.get("failed", 0)

    if total == 0:
        return ""

    failed = summary.get("failed", 0)
    warning = summary.get("warning", 0)

    if failed > 0 or warning > 0:
        return f"[VERIFY] Ultimi check: {failed} FAILED, {warning} WARNING su {total} totali."
    return ""
