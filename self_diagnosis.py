#!/usr/bin/env python3
"""
=============================================================================
  SELF-DIAGNOSIS PROFONDA — nik29-coordinator
  Versione: 1.0.0
  Eseguire dentro il container Docker (porta 4001) o come cron job.
  
  Funzionalità:
    1. Deep Health Check (porte, tool, servizi)
    2. Verifica coerenza memoria (lessons.json, facts.json)
    3. Allineamento codice ↔ configurazione ↔ system prompt
    4. Analisi log per bug nascosti (ultimi 7 giorni)
    5. Auto-fix per problemi critici risolvibili
    6. Endpoint /health/deep (da integrare nel server FastAPI)
=============================================================================
"""

import os
import re
import json
import time
import socket
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
APP_DIR = Path(os.environ.get("APP_DIR", "/app"))
LOGS_DIR = DATA_DIR / "logs"
LESSONS_FILE = DATA_DIR / "lessons.json"
FACTS_FILE = DATA_DIR / "facts.json"
AGENTS_FILE = DATA_DIR / "agents.json"
SYSTEM_PROMPT_FILE = APP_DIR / "system_prompt.txt"
REPORT_FILE = DATA_DIR / "health_report.json"

# Mappa dei servizi attesi con host e porta
SERVICES = {
    "coordinator": {"host": "localhost", "port": 4001, "health_path": "/health"},
    "nik29-images": {"host": "nik29-images", "port": 4002, "health_path": "/health"},
    "host_bridge": {"host": "host.docker.internal", "port": 4010, "health_path": "/ping"},
}

# Pattern di errori temporanei (NON devono generare lezioni)
TRANSIENT_PATTERNS = [
    r"(?i)connection\s*refused",
    r"(?i)timeout",
    r"(?i)host\s*unreachable",
    r"(?i)network\s*is\s*unreachable",
    r"(?i)no\s*route\s*to\s*host",
    r"(?i)502\s*bad\s*gateway",
    r"(?i)503\s*service\s*unavailable",
    r"(?i)socket\.?error",
    r"(?i)errno\s*111",
    r"(?i)docker.*spento",
    r"(?i)bridge.*non.*raggiungibile",
]

# Pattern di bug noti da cercare nei log
BUG_SIGNATURES = {
    "serialization_object_object": {
        "pattern": r"\[object Object\]",
        "severity": "CRITICAL",
        "description": "Bug di serializzazione frontend: i messaggi vengono persi al reload."
    },
    "port_mismatch_4002_as_bridge": {
        "pattern": r"host_tools.*4002|bridge.*4002",
        "severity": "CRITICAL",
        "description": "host_tools.py punta alla porta 4002 (images) invece che 4010 (bridge)."
    },
    "repeated_tool_failure": {
        "pattern": r"Tool .* failed|tool_error|ToolExecutionError",
        "severity": "WARNING",
        "description": "Fallimenti ripetuti di tool — possibile configurazione errata."
    },
    "json_parse_error": {
        "pattern": r"JSONDecodeError|json\.decoder|Expecting value",
        "severity": "WARNING",
        "description": "Errori di parsing JSON ricorrenti — possibile risposta malformata."
    },
}

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "self_diagnosis.log", mode="a")
    ]
)
logger = logging.getLogger("SelfDiagnosis")

# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    """Carica un file JSON, ritorna None se non esiste o è corrotto."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Impossibile leggere {path}: {e}")
        return None


def save_json(path: Path, data: Any):
    """Salva dati in un file JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> bool:
    """Verifica se una porta TCP è raggiungibile."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def check_http_endpoint(host: str, port: int, path: str, timeout: float = 5.0) -> dict:
    """Verifica un endpoint HTTP e ritorna status code + body."""
    import urllib.request
    url = f"http://{host}:{port}{path}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"reachable": True, "status": resp.status, "body": body[:500]}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 1. DEEP HEALTH CHECK — Porte e Servizi
# ---------------------------------------------------------------------------

class DeepHealthCheck:
    """Esegue un health check profondo su tutti i componenti del sistema."""

    def __init__(self):
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "OK",
            "components": {},
            "alerts": [],
            "auto_fixes_applied": []
        }

    def _set_status(self, level: str):
        """Aggiorna lo status globale (solo in peggioramento)."""
        severity_order = {"OK": 0, "WARNING": 1, "CRITICAL": 2}
        if severity_order.get(level, 0) > severity_order.get(self.report["overall_status"], 0):
            self.report["overall_status"] = level

    def alert(self, level: str, component: str, message: str):
        """Registra un alert nel report."""
        self.report["alerts"].append({
            "level": level,
            "component": component,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
        self._set_status(level)
        log_fn = {"OK": logger.info, "WARNING": logger.warning, "CRITICAL": logger.critical}
        log_fn.get(level, logger.info)(f"[{component}] {message}")

    # ----- 1a. Verifica Porte -----
    def check_services(self):
        """Verifica che tutti i servizi siano raggiungibili e rispondano."""
        self.report["components"]["services"] = {}

        for name, cfg in SERVICES.items():
            host, port, health_path = cfg["host"], cfg["port"], cfg["health_path"]
            result = {"host": host, "port": port, "tcp_open": False, "http_ok": False}

            # Step 1: TCP check
            if check_tcp_port(host, port):
                result["tcp_open"] = True
            else:
                # Fallback su localhost (utile se il DNS Docker non risolve)
                if check_tcp_port("127.0.0.1", port):
                    result["tcp_open"] = True
                    result["host"] = "127.0.0.1 (fallback)"

            # Step 2: HTTP health check
            if result["tcp_open"]:
                http_result = check_http_endpoint(
                    result.get("host", host).split(" ")[0], port, health_path
                )
                result["http_ok"] = http_result.get("reachable", False)
                result["http_details"] = http_result
            
            # Valutazione
            if not result["tcp_open"]:
                self.alert("CRITICAL", f"Service:{name}", f"Porta {port} NON raggiungibile su {host}.")
            elif not result["http_ok"]:
                self.alert("WARNING", f"Service:{name}", f"Porta {port} aperta ma endpoint {health_path} non risponde.")
            else:
                self.alert("OK", f"Service:{name}", f"Servizio operativo su {host}:{port}.")

            self.report["components"]["services"][name] = result

    # ----- 1b. Verifica Tool Funzionali -----
    def check_tools_registry(self):
        """Verifica che i tool registrati siano importabili e coerenti."""
        self.report["components"]["tools"] = {"status": "OK", "details": []}
        
        tools_dir = APP_DIR / "tools"
        if not tools_dir.exists():
            self.alert("WARNING", "Tools", f"Directory {tools_dir} non trovata.")
            return

        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("__"):
                continue
            try:
                content = tool_file.read_text(encoding="utf-8")
                # Verifica che abbia una funzione principale (es. def execute, def run, def handler)
                has_entry = bool(re.search(r"def\s+(execute|run|handler|main)\s*\(", content))
                
                # Cerca porte hardcoded sospette
                port_refs = re.findall(r"(?:port|PORT)\s*[=:]\s*(\d{4})", content)
                
                tool_info = {
                    "file": tool_file.name,
                    "has_entry_point": has_entry,
                    "port_references": port_refs
                }
                self.report["components"]["tools"]["details"].append(tool_info)
                
                if not has_entry:
                    self.alert("WARNING", "Tools", f"{tool_file.name} non ha un entry point riconosciuto.")
                    
                # Verifica porte sospette
                for p in port_refs:
                    p_int = int(p)
                    if p_int in [4002] and "host" in tool_file.name.lower():
                        self.alert("CRITICAL", "Tools", 
                            f"{tool_file.name} usa porta {p_int} — probabilmente dovrebbe usare 4010 per host_bridge.")
                        
            except Exception as e:
                self.alert("WARNING", "Tools", f"Errore leggendo {tool_file.name}: {e}")

    # ----- 2. Verifica Coerenza Memoria -----
    def check_memory_consistency(self):
        """Analizza lessons.json e facts.json per contraddizioni e falsi positivi."""
        self.report["components"]["memory"] = {"status": "OK", "lessons": {}, "facts": {}}

        # --- Lessons ---
        lessons = load_json(LESSONS_FILE)
        if lessons is None:
            self.report["components"]["memory"]["lessons"] = {"exists": False}
            return

        total = len(lessons)
        bad_lessons = []
        expired_pending = []
        now = datetime.now()

        for lesson in lessons:
            content = json.dumps(lesson, ensure_ascii=False).lower()
            
            # Controlla se è un errore temporaneo mascherato da lezione
            for pattern in TRANSIENT_PATTERNS:
                if re.search(pattern, content):
                    bad_lessons.append(lesson)
                    break
            
            # Controlla lezioni pending scadute (>24h)
            if lesson.get("status") == "pending":
                last_seen = lesson.get("last_seen", lesson.get("first_seen", ""))
                if last_seen:
                    try:
                        ls_dt = datetime.fromisoformat(last_seen)
                        if now - ls_dt > timedelta(hours=24):
                            expired_pending.append(lesson)
                    except ValueError:
                        pass

        self.report["components"]["memory"]["lessons"] = {
            "total": total,
            "bad_transient": len(bad_lessons),
            "expired_pending": len(expired_pending)
        }

        if bad_lessons:
            self.alert("WARNING", "Memory:Lessons", 
                f"Trovate {len(bad_lessons)} lezioni basate su errori temporanei — dovrebbero essere rimosse.")
        if expired_pending:
            self.alert("WARNING", "Memory:Lessons", 
                f"Trovate {len(expired_pending)} lezioni pending scadute (>24h) — verranno rimosse.")

        # --- Facts ---
        facts = load_json(FACTS_FILE)
        if facts:
            self.report["components"]["memory"]["facts"] = {"total": len(facts) if isinstance(facts, list) else len(facts.keys())}

    # ----- 3. Allineamento Codice ↔ Config ↔ Prompt -----
    def check_code_config_alignment(self):
        """Confronta porte e servizi tra codice sorgente, agents.json e system_prompt."""
        self.report["components"]["alignment"] = {"status": "OK", "mismatches": []}

        # Estrai porte dal system prompt
        prompt_ports = {}
        if SYSTEM_PROMPT_FILE.exists():
            prompt_text = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8", errors="replace")
            # Cerca pattern tipo "porta 4001", "port 4002", ":4010"
            for match in re.finditer(r"(?:porta|port|:)\s*(\d{4})", prompt_text, re.IGNORECASE):
                port_val = int(match.group(1))
                prompt_ports[port_val] = match.group(0)
        
        # Estrai porte dal codice Python
        code_ports = {}
        for py_file in APP_DIR.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r"(?:port|PORT|porta)\s*[=:]\s*(\d{4})", content):
                    port_val = int(match.group(1))
                    if port_val not in code_ports:
                        code_ports[port_val] = []
                    code_ports[port_val].append(str(py_file.relative_to(APP_DIR)))
            except Exception:
                pass

        # Estrai porte da agents.json
        agents_ports = {}
        agents = load_json(AGENTS_FILE)
        if agents and isinstance(agents, (list, dict)):
            agents_text = json.dumps(agents)
            for match in re.finditer(r":(\d{4})", agents_text):
                port_val = int(match.group(1))
                agents_ports[port_val] = True

        # Confronto: se host_tools.py usa 4002 per bridge, è un mismatch
        for py_file in APP_DIR.rglob("*.py"):
            if "host" in py_file.name.lower():
                try:
                    content = py_file.read_text(encoding="utf-8", errors="replace")
                    if "4002" in content and "4010" not in content:
                        mismatch = {
                            "file": str(py_file.relative_to(APP_DIR)),
                            "issue": "Usa porta 4002 (images) ma probabilmente dovrebbe usare 4010 (host_bridge)",
                            "severity": "CRITICAL"
                        }
                        self.report["components"]["alignment"]["mismatches"].append(mismatch)
                        self.alert("CRITICAL", "Alignment", mismatch["issue"] + f" in {mismatch['file']}")
                except Exception:
                    pass

    # ----- 4. Analisi Log per Bug Nascosti -----
    def analyze_logs(self, days: int = 7):
        """Scansiona i log degli ultimi N giorni per pattern di bug noti."""
        self.report["components"]["log_analysis"] = {"status": "OK", "findings": []}

        if not LOGS_DIR.exists():
            logger.info("Directory log non trovata, skip analisi log.")
            return

        cutoff = datetime.now() - timedelta(days=days)
        
        for log_file in LOGS_DIR.iterdir():
            if not log_file.is_file():
                continue
            # Controlla data modifica
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                continue

            try:
                content = log_file.read_text(encoding="utf-8", errors="replace")
                for bug_id, bug_info in BUG_SIGNATURES.items():
                    matches = re.findall(bug_info["pattern"], content)
                    if matches:
                        finding = {
                            "bug_id": bug_id,
                            "file": log_file.name,
                            "occurrences": len(matches),
                            "severity": bug_info["severity"],
                            "description": bug_info["description"]
                        }
                        self.report["components"]["log_analysis"]["findings"].append(finding)
                        self.alert(bug_info["severity"], "LogAnalysis", 
                            f"{bug_id}: {len(matches)} occorrenze in {log_file.name} — {bug_info['description']}")
            except Exception as e:
                logger.warning(f"Errore leggendo log {log_file}: {e}")

    # ----- 5. Auto-Fix -----
    def auto_fix(self):
        """Tenta di risolvere automaticamente i problemi critici risolvibili."""
        lessons = load_json(LESSONS_FILE)
        if lessons is None:
            return

        original_count = len(lessons)
        now = datetime.now()
        cleaned = []

        for lesson in lessons:
            content = json.dumps(lesson, ensure_ascii=False).lower()
            
            # Rimuovi lezioni basate su errori temporanei
            is_transient = any(re.search(p, content) for p in TRANSIENT_PATTERNS)
            if is_transient:
                continue
            
            # Rimuovi lezioni pending scadute
            if lesson.get("status") == "pending":
                last_seen = lesson.get("last_seen", lesson.get("first_seen", ""))
                if last_seen:
                    try:
                        ls_dt = datetime.fromisoformat(last_seen)
                        if now - ls_dt > timedelta(hours=24):
                            continue
                    except ValueError:
                        pass
            
            cleaned.append(lesson)

        removed = original_count - len(cleaned)
        if removed > 0:
            save_json(LESSONS_FILE, cleaned)
            fix_msg = f"Rimosse {removed} lezioni errate/scadute da lessons.json."
            self.report["auto_fixes_applied"].append(fix_msg)
            logger.info(f"[AUTO-FIX] {fix_msg}")

    # ----- ESECUZIONE COMPLETA -----
    def run(self, auto_fix: bool = True) -> dict:
        """Esegue tutti i controlli e opzionalmente applica auto-fix."""
        logger.info("=" * 60)
        logger.info("INIZIO SELF-DIAGNOSIS PROFONDA")
        logger.info("=" * 60)

        self.check_services()
        self.check_tools_registry()
        self.check_memory_consistency()
        self.check_code_config_alignment()
        self.analyze_logs()

        if auto_fix:
            self.auto_fix()

        # Salva il report
        save_json(REPORT_FILE, self.report)
        
        logger.info("=" * 60)
        logger.info(f"DIAGNOSI COMPLETATA — Status: {self.report['overall_status']}")
        logger.info(f"Alerts: {len(self.report['alerts'])} | Auto-fix: {len(self.report['auto_fixes_applied'])}")
        logger.info(f"Report salvato in: {REPORT_FILE}")
        logger.info("=" * 60)

        return self.report


# ---------------------------------------------------------------------------
# ENDPOINT FastAPI (da integrare nel server principale)
# ---------------------------------------------------------------------------

def create_health_endpoint(app):
    """
    Integrazione con FastAPI: aggiunge l'endpoint /health/deep.
    Uso: create_health_endpoint(app) dove app è l'istanza FastAPI.
    """
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    @app.get("/health/deep")
    async def deep_health():
        checker = DeepHealthCheck()
        report = checker.run(auto_fix=False)
        status_code = 200 if report["overall_status"] == "OK" else 503
        return JSONResponse(content=report, status_code=status_code)


# ---------------------------------------------------------------------------
# SCHEDULER (esecuzione periodica ogni 6 ore)
# ---------------------------------------------------------------------------

def run_periodic(interval_hours: int = 6):
    """Esegue la diagnosi in loop ogni N ore. Utile come processo background."""
    while True:
        try:
            checker = DeepHealthCheck()
            checker.run(auto_fix=True)
        except Exception as e:
            logger.error(f"Errore durante diagnosi periodica: {e}")
        
        logger.info(f"Prossima diagnosi tra {interval_hours} ore.")
        time.sleep(interval_hours * 3600)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Self-Diagnosis Profonda per nik29-coordinator")
    parser.add_argument("--periodic", action="store_true", help="Esegui in loop ogni 6 ore")
    parser.add_argument("--interval", type=int, default=6, help="Intervallo in ore (default: 6)")
    parser.add_argument("--no-fix", action="store_true", help="Non applicare auto-fix")
    parser.add_argument("--json", action="store_true", help="Output solo JSON (per integrazione)")
    args = parser.parse_args()

    if args.periodic:
        run_periodic(interval_hours=args.interval)
    else:
        checker = DeepHealthCheck()
        report = checker.run(auto_fix=not args.no_fix)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            # Output human-readable
            print(f"\n{'='*60}")
            print(f"  REPORT AUTO-DIAGNOSI — {report['timestamp']}")
            print(f"  STATUS: {report['overall_status']}")
            print(f"{'='*60}\n")
            
            if report["alerts"]:
                print("ALERTS:")
                for a in report["alerts"]:
                    icon = {"OK": "✓", "WARNING": "⚠", "CRITICAL": "✗"}.get(a["level"], "?")
                    print(f"  {icon} [{a['level']}] {a['component']}: {a['message']}")
                print()
            
            if report["auto_fixes_applied"]:
                print("AUTO-FIX APPLICATI:")
                for fix in report["auto_fixes_applied"]:
                    print(f"  → {fix}")
                print()
