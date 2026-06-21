#!/usr/bin/env python3
"""
PATCH BROWSER TOOLS — Auto-patcher per nik29-coordinator
Esegui dalla root del progetto: python3 patch_browser.py
"""
import sys
import shutil
from pathlib import Path

COORDINATOR_FILE = Path("app/coordinator.py")
DOCKERFILE = Path("Dockerfile")

def patch_coordinator():
    if not COORDINATOR_FILE.exists():
        print(f"ERRORE: {COORDINATOR_FILE} non trovato!")
        return False

    print("\nPATCH coordinator.py")
    content = COORDINATOR_FILE.read_text(encoding="utf-8")

    if "BROWSER_TOOLS" in content:
        print("  Gia patchato. Salto.")
        return True

    shutil.copy2(COORDINATOR_FILE, COORDINATOR_FILE.with_suffix(".py.bak_pre_browser"))
    lines = content.split("\n")

    # 1. Aggiungi import dopo Level 3 imports (o dopo monitoring_tools import)
    import_line = "from app.tools.browser_tools import BROWSER_TOOLS, BROWSER_TOOL_HANDLERS"
    insert_idx = -1
    for i, line in enumerate(lines):
        if "from app.tools.web_tools" in line or "from app.monitoring.monitor" in line:
            insert_idx = i
    if insert_idx == -1:
        for i, line in enumerate(lines):
            if "from app.tools" in line:
                insert_idx = i
    if insert_idx != -1:
        lines.insert(insert_idx + 1, import_line)
        print("  + Import aggiunto")
    else:
        print("  ERRORE: non trovo dove inserire import!")
        return False

    # 2. Aggiungi *BROWSER_TOOLS a TOOLS_DEFINITION
    for i, line in enumerate(lines):
        if "*WEB_TOOLS," in line:
            lines.insert(i + 1, "    *BROWSER_TOOLS,")
            print("  + BROWSER_TOOLS aggiunto a TOOLS_DEFINITION")
            break
    else:
        # Fallback: cerca la ] di chiusura di TOOLS_DEFINITION
        for i, line in enumerate(lines):
            if "*MONITORING_TOOLS," in line:
                lines.insert(i + 1, "    *BROWSER_TOOLS,")
                print("  + BROWSER_TOOLS aggiunto (fallback)")
                break

    # 3. Aggiungi dispatch dopo WEB_TOOL_HANDLERS dispatch
    dispatch_block = [
        "",
        "            elif name in BROWSER_TOOL_HANDLERS:",
        "                handler = BROWSER_TOOL_HANDLERS[name]",
        "                return str(await handler(**args))",
    ]
    for i, line in enumerate(lines):
        if "WEB_TOOL_HANDLERS" in line and "elif" in line:
            # Trova la fine di questo blocco (la riga con "return str")
            for j in range(i+1, min(i+5, len(lines))):
                if "return str" in lines[j]:
                    for idx, d_line in enumerate(dispatch_block):
                        lines.insert(j + 1 + idx, d_line)
                    print("  + Dispatch browser aggiunto")
                    break
            break
    else:
        print("  ATTENZIONE: dispatch non aggiunto automaticamente. Aggiungilo manualmente.")

    COORDINATOR_FILE.write_text("\n".join(lines), encoding="utf-8")
    print("  coordinator.py patchato!")
    return True


def patch_dockerfile():
    if not DOCKERFILE.exists():
        print(f"\nERRORE: {DOCKERFILE} non trovato!")
        return False

    print("\nPATCH Dockerfile")
    content = DOCKERFILE.read_text(encoding="utf-8")

    if "playwright" in content:
        print("  Gia patchato. Salto.")
        return True

    shutil.copy2(DOCKERFILE, DOCKERFILE.with_suffix(".bak_pre_browser"))

    # Inserisci dopo "RUN pip install" (requirements)
    lines = content.split("\n")
    insert_idx = -1
    for i, line in enumerate(lines):
        if "pip install" in line and "requirements" in line:
            insert_idx = i

    if insert_idx != -1:
        playwright_line = "RUN pip install playwright && playwright install chromium --with-deps"
        lines.insert(insert_idx + 1, playwright_line)
        print("  + Playwright install aggiunto al Dockerfile")
    else:
        print("  ERRORE: non trovo dove inserire nel Dockerfile!")
        return False

    DOCKERFILE.write_text("\n".join(lines), encoding="utf-8")
    print("  Dockerfile patchato!")
    return True


def patch_requirements():
    req_file = Path("requirements.txt")
    if req_file.exists():
        content = req_file.read_text(encoding="utf-8")
        if "playwright" not in content:
            with open(req_file, "a") as f:
                f.write("playwright\n")
            print("\n  + playwright aggiunto a requirements.txt")
    return True


if __name__ == "__main__":
    print("="*60)
    print("  NIK29 — Browser Tools (Playwright) Patcher")
    print("="*60)

    if not COORDINATOR_FILE.exists():
        print(f"\nERRORE: esegui dalla root del progetto!")
        print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
        print("  python3 patch_browser.py")
        sys.exit(1)

    ok1 = patch_coordinator()
    ok2 = patch_dockerfile()
    patch_requirements()

    print("\n" + "="*60)
    if ok1 and ok2:
        print("  TUTTO OK! Ora fai:")
        print("  docker compose build && docker compose up -d")
        print("")
        print("  NOTA: il primo build sara piu lento (~2-3 min)")
        print("  perche installa Chromium nel container.")
    else:
        print("  ERRORI — controlla sopra")
    print("="*60 + "\n")
