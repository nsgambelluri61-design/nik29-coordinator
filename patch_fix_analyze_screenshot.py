#!/usr/bin/env python3
"""
FIX analyze_screenshot — Patch per nik29-coordinator
=====================================================
Problema: il tool analyze_screenshot non ha il parametro 'url', quindi il modello
non può specificare quale pagina analizzare visivamente. Il dispatch inoltre apre
una pagina vuota senza navigare.

Fix:
1. Aggiunge parametro 'url' alla TOOL_DEFINITION in screenshot_analyzer.py
2. Aggiorna il dispatch in coordinator.py per navigare all'URL prima dello screenshot
3. Fixa l'import di browser_manager nel blocco web_agent

Esegui dalla root del progetto:
  cd ~/Downloads/nik29-coordinator-v0.6.0
  python3 patch_fix_analyze_screenshot.py
"""
import sys
import shutil
from pathlib import Path

COORDINATOR_FILE = Path("app/coordinator.py")
SCREENSHOT_ANALYZER_FILE = Path("app/tools/screenshot_analyzer.py")


def fix_screenshot_analyzer():
    """Fix 1: Aggiunge parametro 'url' alla tool definition."""
    if not SCREENSHOT_ANALYZER_FILE.exists():
        print(f"  ERRORE: {SCREENSHOT_ANALYZER_FILE} non trovato!")
        return False

    content = SCREENSHOT_ANALYZER_FILE.read_text(encoding="utf-8")

    # Check if already fixed
    if '"url"' in content and "URL della pagina" in content:
        print("  screenshot_analyzer.py gia' fixato. Salto.")
        return True

    # Backup
    shutil.copy2(SCREENSHOT_ANALYZER_FILE, SCREENSHOT_ANALYZER_FILE.with_suffix(".py.bak_pre_fix"))

    # Replace the TOOL_DEFINITION to add 'url' parameter
    old_definition = '''ANALYZE_SCREENSHOT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "analyze_screenshot",
        "description": (
            "Analyze a browser screenshot visually using GPT-4.1 vision. "
            "Can describe page layout, identify buttons, read text, analyze colors, "
            "find navigation elements, and answer questions about what's visible on the page. "
            "Use this when you need to visually understand a web page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "What to analyze or look for in the screenshot. "
                        "Examples: 'What products are shown?', 'Where is the search bar?', "
                        "'What is the main heading?', 'Describe the page layout'"
                    )
                },
                "screenshot_base64": {
                    "type": "string",
                    "description": (
                        "Base64-encoded screenshot image. If not provided, "
                        "a fresh screenshot will be taken automatically."
                    )
                }
            },
            "required": ["question"]
        }
    }
}'''

    new_definition = '''ANALYZE_SCREENSHOT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "analyze_screenshot",
        "description": (
            "Fa uno screenshot di una pagina web e lo analizza visivamente con GPT-4.1 vision. "
            "Descrive layout, contenuti, colori, bottoni, testi, struttura della pagina. "
            "Usa questo tool quando devi VEDERE visivamente una pagina web e descriverne l'aspetto."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL della pagina da analizzare visivamente (es. https://ildormire.com)"
                },
                "question": {
                    "type": "string",
                    "description": (
                        "Cosa analizzare o cercare nello screenshot. "
                        "Esempi: 'Che prodotti sono mostrati?', 'Descrivi il layout', "
                        "'Che colori usa?', 'Come e strutturata la homepage?'. "
                        "Se non specificato, fara una descrizione generale della pagina."
                    )
                }
            },
            "required": ["url"]
        }
    }
}'''

    if old_definition in content:
        content = content.replace(old_definition, new_definition)
        print("  + Tool definition aggiornata con parametro 'url'")
    else:
        # Fallback: try to find and replace just the properties section
        # Look for the definition start and replace the whole block
        start_marker = "ANALYZE_SCREENSHOT_TOOL_DEFINITION = {"
        if start_marker in content:
            start_idx = content.find(start_marker)
            # Find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(content)):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            content = content[:start_idx] + new_definition + content[end_idx:]
            print("  + Tool definition sostituita (fallback)")
        else:
            print("  ERRORE: non trovo ANALYZE_SCREENSHOT_TOOL_DEFINITION!")
            return False

    # Also update execute_analyze_screenshot to accept url parameter
    old_execute_sig = '''async def execute_analyze_screenshot(
    question: str,
    screenshot_base64: Optional[str] = None,
    browser_screenshot_fn=None,
    context: Optional[str] = None,
    model: str = "gpt-4.1",
    client: Optional[AsyncOpenAI] = None,
) -> dict:'''

    new_execute_sig = '''async def execute_analyze_screenshot(
    url: Optional[str] = None,
    question: str = "Descrivi questa pagina web in dettaglio: layout, contenuti, colori, navigazione",
    screenshot_base64: Optional[str] = None,
    browser_screenshot_fn=None,
    context: Optional[str] = None,
    model: str = "gpt-4.1",
    client: Optional[AsyncOpenAI] = None,
) -> dict:'''

    if old_execute_sig in content:
        content = content.replace(old_execute_sig, new_execute_sig)
        print("  + Signature execute_analyze_screenshot aggiornata con 'url'")

    SCREENSHOT_ANALYZER_FILE.write_text(content, encoding="utf-8")
    print("  screenshot_analyzer.py fixato!")
    return True


def fix_coordinator_dispatch():
    """Fix 2: Aggiorna il dispatch per navigare all'URL prima dello screenshot."""
    if not COORDINATOR_FILE.exists():
        print(f"  ERRORE: {COORDINATOR_FILE} non trovato!")
        return False

    content = COORDINATOR_FILE.read_text(encoding="utf-8")

    # Backup
    shutil.copy2(COORDINATOR_FILE, COORDINATOR_FILE.with_suffix(".py.bak_pre_screenshot_fix"))

    # Fix the analyze_screenshot dispatch block
    old_dispatch = '''            elif name == "analyze_screenshot":
                from app.tools.browser_tools import browser_manager
                import base64
                async def _take_screenshot_b64():
                    page = await browser_manager.get_new_page()
                    img_bytes = await page.screenshot(full_page=False)
                    await page.close()
                    return base64.b64encode(img_bytes).decode('utf-8')
                result = await execute_analyze_screenshot(
                    question=args.get('question', ''),
                    screenshot_base64=args.get('screenshot_base64'),
                    browser_screenshot_fn=_take_screenshot_b64,
                )
                return json.dumps(result, ensure_ascii=False)'''

    new_dispatch = '''            elif name == "analyze_screenshot":
                from app.tools.browser_tools import browser_manager
                import base64
                target_url = args.get('url', '')
                question = args.get('question', 'Descrivi questa pagina web in dettaglio: layout, contenuti, colori, navigazione')
                # Naviga all'URL e fai screenshot
                page = await browser_manager.get_new_page()
                try:
                    if target_url:
                        await page.goto(target_url, wait_until="networkidle", timeout=15000)
                        import asyncio
                        await asyncio.sleep(2)
                    img_bytes = await page.screenshot(full_page=False)
                    screenshot_b64 = base64.b64encode(img_bytes).decode('utf-8')
                finally:
                    await page.close()
                result = await execute_analyze_screenshot(
                    url=target_url,
                    question=question,
                    screenshot_base64=screenshot_b64,
                )
                return json.dumps(result, ensure_ascii=False)'''

    if old_dispatch in content:
        content = content.replace(old_dispatch, new_dispatch)
        print("  + Dispatch analyze_screenshot fixato (naviga all'URL)")
    else:
        # Try a more flexible approach
        lines = content.split('\n')
        found = False
        for i, line in enumerate(lines):
            if 'elif name == "analyze_screenshot":' in line:
                # Find the end of this block (next elif or else or end of indent)
                end_idx = i + 1
                for j in range(i + 1, min(i + 20, len(lines))):
                    if lines[j].strip().startswith('elif ') or lines[j].strip().startswith('else:') or lines[j].strip().startswith('# CUSTOM'):
                        end_idx = j
                        break
                # Replace the block
                new_block_lines = new_dispatch.split('\n')
                lines = lines[:i] + new_block_lines + lines[end_idx:]
                content = '\n'.join(lines)
                found = True
                print("  + Dispatch analyze_screenshot fixato (fallback)")
                break
        if not found:
            print("  ERRORE: non trovo il dispatch di analyze_screenshot!")
            return False

    # Fix 3: Add browser_manager import to web_agent block
    # The web_agent block uses browser_manager at line 837 but doesn't import it
    old_web_agent_start = '''            elif name == "web_agent":
                from app.tools.browser_tools import BROWSER_TOOL_HANDLERS as _bt_handlers
                import base64, os
                async def _screenshot_base64():
                    page = await browser_manager.get_new_page()'''

    new_web_agent_start = '''            elif name == "web_agent":
                from app.tools.browser_tools import BROWSER_TOOL_HANDLERS as _bt_handlers, browser_manager
                import base64, os
                async def _screenshot_base64():
                    page = await browser_manager.get_new_page()'''

    if old_web_agent_start in content:
        content = content.replace(old_web_agent_start, new_web_agent_start)
        print("  + Import browser_manager aggiunto al blocco web_agent")
    else:
        print("  NOTA: import browser_manager nel web_agent non trovato (potrebbe essere gia' ok)")

    COORDINATOR_FILE.write_text(content, encoding="utf-8")
    print("  coordinator.py fixato!")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  FIX analyze_screenshot — nik29-coordinator")
    print("=" * 60)

    if not COORDINATOR_FILE.exists():
        print(f"\nERRORE: esegui dalla root del progetto!")
        print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
        print("  python3 patch_fix_analyze_screenshot.py")
        sys.exit(1)

    print("\n[1/2] Fix screenshot_analyzer.py...")
    ok1 = fix_screenshot_analyzer()

    print("\n[2/2] Fix coordinator.py dispatch...")
    ok2 = fix_coordinator_dispatch()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("  TUTTO FIXATO! Ora fai:")
        print("")
        print("  docker compose build && docker compose up -d")
        print("")
        print("  Poi testa con:")
        print('  "fai uno screenshot di https://ildormire.com e analizzalo visivamente"')
        print("")
        print("  Il tool ora:")
        print("  1. Naviga all'URL specificato")
        print("  2. Aspetta il caricamento completo")
        print("  3. Fa lo screenshot")
        print("  4. Lo invia a GPT-4.1 vision per l'analisi")
        print("  5. Ti restituisce la descrizione visiva")
    else:
        print("  CI SONO ERRORI — controlla sopra")
    print("=" * 60 + "\n")
