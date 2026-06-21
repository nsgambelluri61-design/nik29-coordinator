"""
PATCH DEEP RESEARCH — Auto-patcher per nik29-coordinator
=========================================================
Aggiunge il tool deep_research al coordinator.

Esegui dalla ROOT del progetto nik29-coordinator:
    python3 patch_deep_research.py

Prerequisito: deep_research.py deve essere già in app/tools/
"""

import re
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Configurazione percorsi
# ---------------------------------------------------------------------------
COORDINATOR_FILE = Path("app/coordinator.py")
REQUIREMENTS_FILE = Path("requirements.txt")
DEEP_RESEARCH_FILE = Path("app/tools/deep_research.py")

# ---------------------------------------------------------------------------
# Snippet da iniettare
# ---------------------------------------------------------------------------

# 1. Import da aggiungere dopo l'ultimo import del progetto
IMPORT_SNIPPET = """
# === Deep Research Tool ===
from app.tools.deep_research import DEEP_RESEARCH_TOOL_DEF, DEEP_RESEARCH_TOOL_HANDLERS
"""

# 2. Riga da aggiungere dopo le ultime TOOLS_DEFINITION.append(...)
APPEND_SNIPPET = """TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF)
"""

# 3. Dispatch da aggiungere prima del blocco "# CUSTOM TOOLS"
DISPATCH_SNIPPET = """
            # === Deep Research Tool Dispatch ===
            elif name in DEEP_RESEARCH_TOOL_HANDLERS:
                handler = DEEP_RESEARCH_TOOL_HANDLERS[name]
                return str(await handler(**args))
"""

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def backup_file(filepath: Path) -> Path:
    """Crea backup del file originale."""
    backup = filepath.with_suffix(filepath.suffix + ".bak_pre_deep_research")
    shutil.copy2(filepath, backup)
    print(f"  Backup creato: {backup}")
    return backup


def already_patched(content: str) -> bool:
    return "DEEP_RESEARCH_TOOL_DEF" in content or "deep_research" in content


# ---------------------------------------------------------------------------
# Patch coordinator.py
# ---------------------------------------------------------------------------

def patch_coordinator() -> bool:
    if not COORDINATOR_FILE.exists():
        print(f"ERRORE: {COORDINATOR_FILE} non trovato!")
        print("Esegui questo script dalla root del progetto nik29-coordinator.")
        return False

    print(f"\n{'='*60}")
    print("PATCH coordinator.py")
    print(f"{'='*60}")

    backup_file(COORDINATOR_FILE)
    content = COORDINATOR_FILE.read_text(encoding="utf-8")

    if already_patched(content):
        print("  Il file sembra gia patchato con Deep Research. Salto.")
        return True

    # ------------------------------------------------------------------
    # PATCH 1: Import
    # Inserisci dopo l'ultimo blocco di import (cerca l'ultimo "from app.tools")
    # ------------------------------------------------------------------
    # Strategia: trova l'ultima riga che inizia con "from app.tools" o "from app."
    import_pattern = re.compile(r"^from app\.", re.MULTILINE)
    matches = list(import_pattern.finditer(content))
    if matches:
        last_match = matches[-1]
        # Trova la fine della riga (gestisce import multi-riga con parentesi)
        pos = last_match.start()
        if "(" in content[pos:pos+200].split("\n")[0]:
            # Import multi-riga: trova la parentesi chiusa
            paren_end = content.find(")", pos)
            insert_pos = content.find("\n", paren_end) + 1
        else:
            insert_pos = content.find("\n", pos) + 1
        content = content[:insert_pos] + IMPORT_SNIPPET + content[insert_pos:]
        print("  + Import Deep Research aggiunto")
    else:
        # Fallback: inserisci prima di "logger = logging"
        marker = "logger = logging.getLogger"
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx] + IMPORT_SNIPPET + "\n" + content[idx:]
            print("  + Import Deep Research aggiunto (fallback)")
        else:
            print("  ERRORE: non trovo dove inserire l'import!")
            return False

    # ------------------------------------------------------------------
    # PATCH 2: TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF)
    # Inserisci dopo l'ultimo TOOLS_DEFINITION.append(...)
    # ------------------------------------------------------------------
    append_pattern = re.compile(r"^TOOLS_DEFINITION\.append\(", re.MULTILINE)
    append_matches = list(append_pattern.finditer(content))
    if append_matches:
        last_append = append_matches[-1]
        insert_pos = content.find("\n", last_append.start()) + 1
        content = content[:insert_pos] + APPEND_SNIPPET + content[insert_pos:]
        print("  + TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF) aggiunto")
    else:
        # Fallback: aggiungi dopo la chiusura di TOOLS_DEFINITION = [...]
        tools_marker = "TOOLS_DEFINITION = ["
        if tools_marker in content:
            idx_start = content.find(tools_marker)
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
                insert_pos = content.find("\n", closing_bracket_pos) + 1
                content = content[:insert_pos] + APPEND_SNIPPET + content[insert_pos:]
                print("  + TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF) aggiunto (fallback)")
            else:
                print("  ATTENZIONE: non trovo dove aggiungere il tool alla lista. Aggiungilo manualmente.")
        else:
            print("  ATTENZIONE: TOOLS_DEFINITION non trovato. Aggiungilo manualmente.")

    # ------------------------------------------------------------------
    # PATCH 3: Dispatch nel metodo _execute_tool
    # Inserisci prima del blocco "# CUSTOM TOOLS"
    # ------------------------------------------------------------------
    custom_tools_marker = "# CUSTOM TOOLS"
    if custom_tools_marker in content:
        idx = content.find(custom_tools_marker)
        line_start = content.rfind("\n", 0, idx) + 1
        content = content[:line_start] + DISPATCH_SNIPPET + "\n" + content[line_start:]
        print("  + Dispatch Deep Research aggiunto in _execute_tool")
    else:
        # Fallback: prima di "return f\"Tool '{name}' non riconosciuto.\""
        fallback_marker = "return f\"Tool '{name}' non riconosciuto.\""
        if fallback_marker in content:
            idx = content.find(fallback_marker)
            line_start = content.rfind("\n", 0, idx) + 1
            prev_line_start = content.rfind("\n", 0, line_start - 1) + 1
            content = content[:prev_line_start] + DISPATCH_SNIPPET + "\n" + content[prev_line_start:]
            print("  + Dispatch Deep Research aggiunto (fallback)")
        else:
            print("  ATTENZIONE: non trovo dove inserire il dispatch. Aggiungilo manualmente.")

    COORDINATOR_FILE.write_text(content, encoding="utf-8")
    print("  => coordinator.py aggiornato con successo!")
    return True


# ---------------------------------------------------------------------------
# Patch requirements.txt
# ---------------------------------------------------------------------------

def patch_requirements():
    if not REQUIREMENTS_FILE.exists():
        print(f"\nATTENZIONE: {REQUIREMENTS_FILE} non trovato. Ignoro.")
        return

    content = REQUIREMENTS_FILE.read_text(encoding="utf-8")
    added = []

    if "lxml" not in content.lower():
        content += "\nlxml>=4.9.0\n"
        added.append("lxml>=4.9.0")

    if added:
        REQUIREMENTS_FILE.write_text(content, encoding="utf-8")
        print(f"\n  + Aggiunte dipendenze a requirements.txt: {', '.join(added)}")
    else:
        print("\n  requirements.txt gia aggiornato.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("PATCH DEEP RESEARCH per nik29-coordinator")
    print("=" * 60)

    # Verifica directory corrente
    if not Path("app").is_dir() or not Path("app/tools").is_dir():
        print("\nERRORE: Esegui questo script dalla ROOT del progetto nik29-coordinator!")
        print("Esempio: cd /path/to/nik29-coordinator && python3 patch_deep_research.py")
        return

    # Verifica che deep_research.py sia gia nella directory tools
    if not DEEP_RESEARCH_FILE.exists():
        print(f"\nERRORE: {DEEP_RESEARCH_FILE} non trovato!")
        print("Prima di eseguire la patch, copia deep_research.py in app/tools/:")
        print("  cp deep_research.py app/tools/")
        return

    ok = patch_coordinator()
    if ok:
        patch_requirements()

    print("\n" + "=" * 60)
    if ok:
        print("PATCH COMPLETATA!")
        print("\nProssimi passi:")
        print("  1. Ricostruisci il container: docker-compose build")
        print("  2. Riavvia:                   docker-compose up -d")
        print("  3. Verifica i log:            docker-compose logs -f nik29")
    else:
        print("PATCH FALLITA. Controlla gli errori sopra.")
    print("=" * 60)


if __name__ == "__main__":
    main()
