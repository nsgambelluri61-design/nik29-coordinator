#!/usr/bin/env python3
"""
PATCH LEVEL 3 AUTONOMY — Auto-patcher per nik29-coordinator
Esegui dalla root del progetto: python3 patch_level3.py
Modifica automaticamente coordinator.py e docker-compose.yml
"""
import re
import sys
import shutil
from pathlib import Path

# ============================================================
# CONFIGURAZIONE
# ============================================================
COORDINATOR_FILE = Path("app/coordinator.py")
DOCKER_COMPOSE_FILE = Path("docker-compose.yml")

# ============================================================
# PATCH 1: coordinator.py — Aggiungi import Level 3
# ============================================================
LEVEL3_IMPORTS = """
# === Level 3 Autonomy Imports ===
from app.tools.monitoring_tools import (
    HealthCheckTool, AutoDebugTool, AlertTool,
    HEALTH_CHECK_TOOL_DEFINITION, AUTO_DEBUG_TOOL_DEFINITION, SEND_ALERT_TOOL_DEFINITION
)
from app.tools.scheduler_tools import (
    ScheduleTaskTool, RunTaskNowTool,
    SCHEDULE_TASK_TOOL_DEFINITION, RUN_TASK_NOW_TOOL_DEFINITION
)
from app.tools.web_tools import (
    BRAVE_SEARCH_TOOL_DEF, BROWSE_URL_TOOL_DEF, WEB_RESEARCH_TOOL_DEF,
    brave_search, browse_url, web_research
)
from app.monitoring.monitor import create_monitor_task
from app.scheduler.scheduler import start_scheduler
"""

# ============================================================
# PATCH 2: coordinator.py — Aggiungi tool definitions
# ============================================================
LEVEL3_TOOLS = """    # === Level 3 Autonomy Tools ===
    HEALTH_CHECK_TOOL_DEFINITION,
    AUTO_DEBUG_TOOL_DEFINITION,
    SEND_ALERT_TOOL_DEFINITION,
    SCHEDULE_TASK_TOOL_DEFINITION,
    RUN_TASK_NOW_TOOL_DEFINITION,
    BRAVE_SEARCH_TOOL_DEF,
    BROWSE_URL_TOOL_DEF,
    WEB_RESEARCH_TOOL_DEF,
"""

# ============================================================
# PATCH 3: coordinator.py — Aggiungi dispatch dei tool
# ============================================================
LEVEL3_DISPATCH = '''
            # === Level 3 Autonomy Tool Dispatch ===
            elif name == "health_check":
                return await self.health_check_tool.execute(
                    check_type=args.get("check_type", "all")
                )

            elif name == "auto_debug":
                return await self.auto_debug_tool.execute(
                    issue=args.get("issue", ""),
                    context=args.get("context", "")
                )

            elif name == "send_alert":
                return await self.alert_tool.execute(
                    message=args.get("message", ""),
                    level=args.get("level", "warning")
                )

            elif name == "schedule_task":
                return await self.schedule_task_tool.execute(
                    action=args.get("action", "list"),
                    task_id=args.get("task_id", ""),
                    name=args.get("name", ""),
                    cron_expression=args.get("cron_expression", ""),
                    task_action=args.get("task_action", "")
                )

            elif name == "run_task_now":
                return await self.run_task_now_tool.execute(
                    task_id=args.get("task_id", "")
                )

            elif name == "brave_search":
                result = await brave_search(
                    query=args.get("query", ""),
                    count=args.get("count", 5),
                    language=args.get("language", "it")
                )
                return str(result)

            elif name == "browse_url":
                result = await browse_url(
                    url=args.get("url", ""),
                    max_chars=args.get("max_chars", 4000)
                )
                return str(result)

            elif name == "web_research":
                result = await web_research(
                    query=args.get("query", ""),
                    num_results=args.get("num_results", 3)
                )
                return str(result)
'''

# ============================================================
# PATCH 4: coordinator.py — Init dei tool nella classe
# ============================================================
LEVEL3_INIT = """
        # === Level 3 Autonomy Tool Instances ===
        self.health_check_tool = HealthCheckTool()
        self.auto_debug_tool = AutoDebugTool()
        self.alert_tool = AlertTool()
        self.schedule_task_tool = ScheduleTaskTool()
        self.run_task_now_tool = RunTaskNowTool()
"""

# ============================================================
# PATCH 5: coordinator.py — Startup del monitor e scheduler
# ============================================================
LEVEL3_STARTUP = """
    # === Level 3 Autonomy Background Services ===
    async def start_level3_services(self):
        \"\"\"Avvia monitoring e scheduler in background.\"\"\"
        try:
            self._monitor_task = create_monitor_task()
            await start_scheduler()
            logger.info("Level 3 autonomy services started (monitor + scheduler)")
        except Exception as e:
            logger.error(f"Failed to start Level 3 services: {e}")
"""

# ============================================================
# FUNZIONI DI PATCH
# ============================================================

def backup_file(filepath):
    """Crea backup del file originale."""
    backup = filepath.with_suffix(filepath.suffix + ".bak_pre_level3")
    shutil.copy2(filepath, backup)
    print(f"  Backup creato: {backup}")
    return backup


def patch_coordinator():
    """Applica tutte le patch a coordinator.py."""
    if not COORDINATOR_FILE.exists():
        print(f"ERRORE: {COORDINATOR_FILE} non trovato!")
        print("Esegui questo script dalla root del progetto nik29-coordinator")
        return False

    print(f"\n{'='*60}")
    print(f"PATCH coordinator.py")
    print(f"{'='*60}")

    backup_file(COORDINATOR_FILE)
    content = COORDINATOR_FILE.read_text(encoding="utf-8")

    # Check se gia patchato
    if "Level 3 Autonomy" in content:
        print("  Il file sembra gia patchato con Level 3. Salto.")
        return True

    # --- PATCH IMPORTS ---
    # Inserisci dopo l'ultimo import esistente (from app.tools.host_tools import ...)
    import_marker = "from app.tools.host_tools import"
    if import_marker in content:
        # Trova la fine della riga (o del blocco multi-riga con parentesi)
        idx = content.find(import_marker)
        # Trova la fine dell'import (potrebbe essere multi-riga con parentesi)
        paren_start = content.find("(", idx)
        if paren_start != -1 and paren_start < content.find("\n", idx) + 5:
            # Multi-line import
            paren_end = content.find(")", paren_start)
            insert_pos = content.find("\n", paren_end) + 1
        else:
            insert_pos = content.find("\n", idx) + 1
        content = content[:insert_pos] + LEVEL3_IMPORTS + content[insert_pos:]
        print("  + Import Level 3 aggiunti")
    else:
        # Fallback: inserisci dopo "import logging" o prima di "logger ="
        marker = "logger = logging.getLogger"
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx] + LEVEL3_IMPORTS + "\n" + content[idx:]
            print("  + Import Level 3 aggiunti (fallback)")
        else:
            print("  ERRORE: non trovo dove inserire gli import!")
            return False

    # --- PATCH TOOLS_DEFINITION ---
    # Aggiungi i tool alla lista TOOLS_DEFINITION prima della chiusura ]
    tools_marker = "TOOLS_DEFINITION = ["
    if tools_marker in content:
        # Trova l'ultima ] che chiude TOOLS_DEFINITION
        idx_start = content.find(tools_marker)
        # Cerca la ] di chiusura — e' l'ultima ] prima di una riga vuota o commento
        # Strategia: trova tutte le occorrenze di "]" dopo tools_marker
        # e prendi quella al livello 0 di indentazione
        search_from = idx_start + len(tools_marker)
        bracket_count = 1
        pos = search_from
        closing_bracket_pos = -1
        while pos < len(content) and bracket_count > 0:
            if content[pos] == "[":
                bracket_count += 1
            elif content[pos] == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    closing_bracket_pos = pos
            pos += 1

        if closing_bracket_pos != -1:
            content = content[:closing_bracket_pos] + LEVEL3_TOOLS + content[closing_bracket_pos:]
            print("  + Tool definitions Level 3 aggiunti a TOOLS_DEFINITION")
        else:
            print("  ERRORE: non trovo la chiusura di TOOLS_DEFINITION!")
            return False
    else:
        print("  ERRORE: TOOLS_DEFINITION non trovato!")
        return False

    # --- PATCH TOOL DISPATCH ---
    # Inserisci prima del blocco "# CUSTOM TOOLS"
    custom_tools_marker = "# CUSTOM TOOLS"
    if custom_tools_marker in content:
        idx = content.find(custom_tools_marker)
        # Trova l'inizio della riga
        line_start = content.rfind("\n", 0, idx) + 1
        content = content[:line_start] + LEVEL3_DISPATCH + "\n" + content[line_start:]
        print("  + Tool dispatch Level 3 aggiunto")
    else:
        # Fallback: inserisci prima di "else: return f\"Tool '{name}' non riconosciuto.\""
        fallback_marker = "return f\"Tool '{name}' non riconosciuto.\""
        if fallback_marker in content:
            idx = content.find(fallback_marker)
            line_start = content.rfind("\n", 0, idx) + 1
            # Risali di una riga per trovare l'else:
            prev_line_start = content.rfind("\n", 0, line_start - 1) + 1
            content = content[:prev_line_start] + LEVEL3_DISPATCH + "\n" + content[prev_line_start:]
            print("  + Tool dispatch Level 3 aggiunto (fallback)")
        else:
            print("  ATTENZIONE: non trovo dove inserire il dispatch. Aggiungilo manualmente.")

    # --- PATCH INIT (istanze tool) ---
    # Inserisci dopo self.git_auto_tool o self.host_shell_tool
    init_markers = ["self.git_auto_tool", "self.docker_manage_tool", "self.host_shell_tool"]
    inserted_init = False
    for marker in init_markers:
        if marker in content:
            # Trova l'ultima occorrenza di assegnazione con questo marker
            idx = content.rfind(marker)
            # Vai alla fine della riga
            line_end = content.find("\n", idx)
            if line_end != -1:
                content = content[:line_end + 1] + LEVEL3_INIT + content[line_end + 1:]
                print(f"  + Init tool Level 3 aggiunto dopo {marker}")
                inserted_init = True
                break
    if not inserted_init:
        # Fallback: inserisci dopo "def __init__" + qualche riga
        print("  ATTENZIONE: non trovo dove inserire init tool. Aggiungilo manualmente nel __init__.")

    # --- PATCH STARTUP METHOD ---
    # Aggiungi il metodo start_level3_services alla fine della classe
    # Inseriscilo prima di "# Singleton"
    singleton_marker = "# Singleton"
    if singleton_marker in content:
        idx = content.find(singleton_marker)
        content = content[:idx] + LEVEL3_STARTUP + "\n" + content[idx:]
        print("  + Metodo start_level3_services aggiunto")
    else:
        # Aggiungi alla fine del file
        content += LEVEL3_STARTUP
        print("  + Metodo start_level3_services aggiunto (fine file)")

    # Scrivi il file
    COORDINATOR_FILE.write_text(content, encoding="utf-8")
    print(f"\n  coordinator.py patchato con successo!")
    return True


def patch_docker_compose():
    """Applica le patch a docker-compose.yml."""
    if not DOCKER_COMPOSE_FILE.exists():
        print(f"ERRORE: {DOCKER_COMPOSE_FILE} non trovato!")
        return False

    print(f"\n{'='*60}")
    print(f"PATCH docker-compose.yml")
    print(f"{'='*60}")

    backup_file(DOCKER_COMPOSE_FILE)
    content = DOCKER_COMPOSE_FILE.read_text(encoding="utf-8")

    # Check se gia patchato
    if "BRAVE_API_KEY" in content:
        print("  Il file sembra gia patchato con Level 3. Salto.")
        return True

    # Aggiungi variabili ambiente
    env_additions = [
        "      - BRAVE_API_KEY=${BRAVE_API_KEY:-}",
        "      - MONITOR_SITE_URL=https://ildormire.com",
    ]

    # Trova la sezione environment e aggiungi dopo l'ultima variabile
    # Cerchiamo HOST_PROJECT_DIR che dovrebbe essere l'ultima
    env_marker = "HOST_PROJECT_DIR="
    if env_marker in content:
        idx = content.find(env_marker)
        line_end = content.find("\n", idx)
        insert_text = "\n" + "\n".join(env_additions)
        content = content[:line_end] + insert_text + content[line_end:]
        print("  + Variabili ambiente aggiunte (BRAVE_API_KEY, MONITOR_SITE_URL)")
    else:
        # Fallback: cerca HOST_BRIDGE_URL
        env_marker2 = "HOST_BRIDGE_URL="
        if env_marker2 in content:
            idx = content.find(env_marker2)
            line_end = content.find("\n", idx)
            insert_text = "\n" + "\n".join(env_additions)
            content = content[:line_end] + insert_text + content[line_end:]
            print("  + Variabili ambiente aggiunte (BRAVE_API_KEY, MONITOR_SITE_URL)")
        else:
            print("  ATTENZIONE: non trovo la sezione environment. Aggiungi manualmente.")

    # Aggiungi volumi per monitoring e scheduler
    vol_additions = [
        "      - ./data/monitoring:/data/monitoring",
        "      - ./data/scheduler:/data/scheduler",
    ]

    # Cerca l'ultimo volume montato (./config:/app/config)
    vol_marker = "./config:"
    if vol_marker in content:
        idx = content.find(vol_marker)
        line_end = content.find("\n", idx)
        insert_text = "\n" + "\n".join(vol_additions)
        content = content[:line_end] + insert_text + content[line_end:]
        print("  + Volumi aggiunti (monitoring, scheduler)")
    else:
        # Fallback: cerca ./data/workspace
        vol_marker2 = "./data/workspace:"
        if vol_marker2 in content:
            idx = content.find(vol_marker2)
            line_end = content.find("\n", idx)
            insert_text = "\n" + "\n".join(vol_additions)
            content = content[:line_end] + insert_text + content[line_end:]
            print("  + Volumi aggiunti (monitoring, scheduler)")
        else:
            print("  ATTENZIONE: non trovo la sezione volumes. Aggiungi manualmente.")

    DOCKER_COMPOSE_FILE.write_text(content, encoding="utf-8")
    print(f"\n  docker-compose.yml patchato con successo!")
    return True


def patch_env():
    """Aggiungi BRAVE_API_KEY al .env se non presente."""
    env_file = Path(".env")
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if "BRAVE_API_KEY" not in content:
            with open(env_file, "a") as f:
                f.write("\n# Level 3 — Brave Search (ottieni chiave gratis: https://brave.com/search/api/)\nBRAVE_API_KEY=\n")
            print("\n  + BRAVE_API_KEY aggiunto al .env (da compilare)")
        else:
            print("\n  BRAVE_API_KEY gia presente nel .env")
    else:
        print("\n  ATTENZIONE: .env non trovato")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  NIK29-COORDINATOR — Level 3 Autonomy Auto-Patcher")
    print("=" * 60)

    # Verifica di essere nella directory giusta
    if not COORDINATOR_FILE.exists():
        print(f"\nERRORE: Non trovo {COORDINATOR_FILE}")
        print("Esegui questo script dalla root del progetto:")
        print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
        print("  python3 patch_level3.py")
        sys.exit(1)

    ok1 = patch_coordinator()
    ok2 = patch_docker_compose()
    patch_env()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("  TUTTO PATCHATO CON SUCCESSO!")
        print("=" * 60)
        print("\n  Prossimi passi:")
        print("  1. Aggiungi la tua Brave API key nel .env")
        print("     (gratis: https://brave.com/search/api/)")
        print("  2. Rebuild e restart:")
        print("     docker compose build && docker compose up -d")
        print("  3. Testa: apri http://localhost:4001 e chiedi")
        print("     'fai un health check' o 'cerca materassi memory foam'")
    else:
        print("  PATCH PARZIALE — controlla gli errori sopra")
        print("=" * 60)
    print()
