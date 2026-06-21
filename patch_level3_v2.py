#!/usr/bin/env python3
"""
PATCH LEVEL 3 AUTONOMY v2 — Auto-patcher CORRETTO per nik29-coordinator
Esegui dalla root del progetto: python3 patch_level3_v2.py
"""
import sys
import shutil
from pathlib import Path

COORDINATOR_FILE = Path("app/coordinator.py")
DOCKER_COMPOSE_FILE = Path("docker-compose.yml")

def backup_file(filepath):
    backup = filepath.with_suffix(filepath.suffix + ".bak2")
    shutil.copy2(filepath, backup)
    print(f"  Backup: {backup}")

def patch_coordinator():
    if not COORDINATOR_FILE.exists():
        print(f"ERRORE: {COORDINATOR_FILE} non trovato!")
        return False

    print("\n" + "="*60)
    print("PATCH coordinator.py")
    print("="*60)

    backup_file(COORDINATOR_FILE)
    lines = COORDINATOR_FILE.read_text(encoding="utf-8").split("\n")

    if "MONITORING_TOOLS" in "\n".join(lines):
        print("  Gia patchato. Salto.")
        return True

    # === 1. AGGIUNGI IMPORT dopo l'ultimo import (from app.tools.host_tools) ===
    import_block = [
        "",
        "# === Level 3 Autonomy Imports ===",
        "from app.tools.monitoring_tools import MONITORING_TOOLS, MONITORING_TOOL_HANDLERS",
        "from app.tools.scheduler_tools import SCHEDULER_TOOLS, SCHEDULER_TOOL_HANDLERS",
        "from app.tools.web_tools import WEB_TOOLS, WEB_TOOL_HANDLERS",
        "from app.monitoring.monitor import create_monitor_task",
        "from app.scheduler.scheduler import start_scheduler",
    ]

    # Trova l'ultima riga di import (cerca "from app.tools.host_tools")
    insert_after_import = -1
    for i, line in enumerate(lines):
        if "from app.tools.host_tools" in line:
            # Potrebbe essere multi-riga, cerca la chiusura )
            if ")" not in line:
                for j in range(i+1, min(i+10, len(lines))):
                    if ")" in lines[j]:
                        insert_after_import = j
                        break
            else:
                insert_after_import = i
            break

    if insert_after_import == -1:
        # Fallback: inserisci prima di "logger ="
        for i, line in enumerate(lines):
            if line.startswith("logger = logging"):
                insert_after_import = i - 1
                break

    if insert_after_import == -1:
        print("  ERRORE: non trovo dove inserire gli import!")
        return False

    for idx, imp_line in enumerate(import_block):
        lines.insert(insert_after_import + 1 + idx, imp_line)
    print("  + Import aggiunti")

    # === 2. AGGIUNGI TOOL DEFINITIONS alla lista TOOLS_DEFINITION ===
    # Cerca la ] di chiusura di TOOLS_DEFINITION
    tools_start = -1
    bracket_depth = 0
    tools_end = -1

    for i, line in enumerate(lines):
        if "TOOLS_DEFINITION" in line and "=" in line and "[" in line:
            tools_start = i
            bracket_depth = line.count("[") - line.count("]")
            if bracket_depth == 0:
                tools_end = i
            continue
        if tools_start != -1 and tools_end == -1:
            bracket_depth += line.count("[") - line.count("]")
            if bracket_depth <= 0:
                tools_end = i
                break

    if tools_end == -1:
        print("  ERRORE: non trovo la fine di TOOLS_DEFINITION!")
        return False

    # Inserisci prima della ] di chiusura
    tool_additions = [
        "    # === Level 3 Autonomy Tools ===",
        "    *MONITORING_TOOLS,",
        "    *SCHEDULER_TOOLS,",
        "    *WEB_TOOLS,",
    ]
    for idx, t_line in enumerate(tool_additions):
        lines.insert(tools_end + idx, t_line)
    print("  + Tool definitions aggiunti a TOOLS_DEFINITION")

    # === 3. AGGIUNGI DISPATCH nel metodo execute_tool ===
    # Cerca "# CUSTOM TOOLS" e inserisci prima
    dispatch_block = [
        "",
        "            # === Level 3 Autonomy Tool Dispatch ===",
        "            elif name in MONITORING_TOOL_HANDLERS:",
        "                handler = MONITORING_TOOL_HANDLERS[name]",
        "                return str(await handler(**args))",
        "",
        "            elif name in SCHEDULER_TOOL_HANDLERS:",
        "                handler = SCHEDULER_TOOL_HANDLERS[name]",
        "                return str(await handler(**args))",
        "",
        "            elif name in WEB_TOOL_HANDLERS:",
        "                handler = WEB_TOOL_HANDLERS[name]",
        "                return str(await handler(**args))",
    ]

    custom_tools_idx = -1
    for i, line in enumerate(lines):
        if "# CUSTOM TOOLS" in line:
            custom_tools_idx = i
            break

    if custom_tools_idx == -1:
        # Fallback: cerca "return f\"Tool '{name}' non riconosciuto.\""
        for i, line in enumerate(lines):
            if "non riconosciuto" in line:
                # Risali di 2 righe (else:)
                custom_tools_idx = i - 1
                break

    if custom_tools_idx == -1:
        print("  ATTENZIONE: non trovo dove inserire il dispatch!")
    else:
        for idx, d_line in enumerate(dispatch_block):
            lines.insert(custom_tools_idx + idx, d_line)
        print("  + Tool dispatch aggiunto")

    # === 4. AGGIUNGI STARTUP del monitor e scheduler ===
    # Cerca "# Singleton" e inserisci prima
    startup_block = [
        "",
        "    # === Level 3: Avvia monitoring e scheduler ===",
        "    async def start_level3_services(self):",
        "        try:",
        "            self._monitor_task = create_monitor_task()",
        "            await start_scheduler()",
        "            logger.info('Level 3 services started (monitor + scheduler)')",
        "        except Exception as e:",
        "            logger.error(f'Failed to start Level 3 services: {e}')",
        "",
    ]

    singleton_idx = -1
    for i, line in enumerate(lines):
        if "# Singleton" in line:
            singleton_idx = i
            break

    if singleton_idx != -1:
        for idx, s_line in enumerate(startup_block):
            lines.insert(singleton_idx + idx, s_line)
        print("  + Metodo start_level3_services aggiunto")
    else:
        lines.extend(startup_block)
        print("  + Metodo start_level3_services aggiunto (fine file)")

    # Scrivi il file
    COORDINATOR_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  coordinator.py patchato con successo!")
    return True


def patch_docker_compose():
    if not DOCKER_COMPOSE_FILE.exists():
        print(f"ERRORE: {DOCKER_COMPOSE_FILE} non trovato!")
        return False

    print("\n" + "="*60)
    print("PATCH docker-compose.yml")
    print("="*60)

    backup_file(DOCKER_COMPOSE_FILE)
    content = DOCKER_COMPOSE_FILE.read_text(encoding="utf-8")

    if "BRAVE_API_KEY" in content:
        print("  Gia patchato. Salto.")
        return True

    # Aggiungi env vars dopo HOST_BRIDGE_URL o HOST_PROJECT_DIR
    for marker in ["HOST_PROJECT_DIR=", "HOST_BRIDGE_URL="]:
        if marker in content:
            idx = content.find(marker)
            line_end = content.find("\n", idx)
            additions = "\n      - BRAVE_API_KEY=${BRAVE_API_KEY:-}\n      - MONITOR_SITE_URL=https://ildormire.com"
            content = content[:line_end] + additions + content[line_end:]
            print("  + Variabili ambiente aggiunte")
            break

    # Aggiungi volumi dopo ./config:
    for marker in ["./config:", "./data/workspace:"]:
        if marker in content:
            idx = content.find(marker)
            line_end = content.find("\n", idx)
            additions = "\n      - ./data/monitoring:/data/monitoring\n      - ./data/scheduler:/data/scheduler"
            content = content[:line_end] + additions + content[line_end:]
            print("  + Volumi aggiunti")
            break

    DOCKER_COMPOSE_FILE.write_text(content, encoding="utf-8")
    print(f"\n  docker-compose.yml patchato!")
    return True


def patch_env():
    env_file = Path(".env")
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        if "BRAVE_API_KEY" not in content:
            with open(env_file, "a") as f:
                f.write("\n# Level 3 - Brave Search (gratis: https://brave.com/search/api/)\nBRAVE_API_KEY=\n")
            print("\n  + BRAVE_API_KEY aggiunto al .env")
        else:
            print("\n  BRAVE_API_KEY gia presente")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  NIK29 — Level 3 Autonomy Patcher v2 (CORRETTO)")
    print("="*60)

    if not COORDINATOR_FILE.exists():
        print(f"\nERRORE: esegui dalla root del progetto!")
        print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
        print("  python3 patch_level3_v2.py")
        sys.exit(1)

    ok1 = patch_coordinator()
    ok2 = patch_docker_compose()
    patch_env()

    print("\n" + "="*60)
    if ok1 and ok2:
        print("  TUTTO OK! Ora fai:")
        print("  docker compose build && docker compose up -d")
    else:
        print("  ERRORI — controlla sopra")
    print("="*60 + "\n")
