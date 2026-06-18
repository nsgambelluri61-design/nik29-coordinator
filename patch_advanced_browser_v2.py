#!/usr/bin/env python3
"""
PATCH ADVANCED BROWSER — Auto-patcher per nik29-coordinator v2
Aggiunge: web_agent, analyze_screenshot, model routing

Esegui dalla root del progetto: python3 patch_advanced_browser_v2.py
"""
import sys
import shutil
from pathlib import Path

COORDINATOR_FILE = Path("app/coordinator.py")
ENV_FILE = Path(".env")


def patch_coordinator():
    if not COORDINATOR_FILE.exists():
        print(f"ERRORE: {COORDINATOR_FILE} non trovato!")
        return False

    print("\nPATCH coordinator.py")
    content = COORDINATOR_FILE.read_text(encoding="utf-8")

    if "web_agent" in content and "execute_web_agent" in content:
        print("  Gia patchato. Salto.")
        return True

    shutil.copy2(COORDINATOR_FILE, COORDINATOR_FILE.with_suffix(".py.bak_pre_advanced_browser"))
    lines = content.split("\n")

    # === 1. AGGIUNGI IMPORTS ===
    import_lines = [
        "from app.tools.web_agent import WEB_AGENT_TOOL_DEFINITION, execute_web_agent",
        "from app.tools.screenshot_analyzer import ANALYZE_SCREENSHOT_TOOL_DEFINITION, execute_analyze_screenshot",
        "from app.routing.model_router import route_model",
    ]

    # Inserisci dopo l'ultimo import "from app.tools"
    last_app_import_idx = -1
    for i, line in enumerate(lines):
        if "from app.tools" in line or "from app.routing" in line:
            last_app_import_idx = i
    # Fallback: cerca BROWSER_TOOL_HANDLERS import
    if last_app_import_idx == -1:
        for i, line in enumerate(lines):
            if "BROWSER_TOOL" in line and "import" in line:
                last_app_import_idx = i
    if last_app_import_idx == -1:
        for i, line in enumerate(lines):
            if "import" in line and "from" in line:
                last_app_import_idx = i

    if last_app_import_idx != -1:
        for idx, imp in enumerate(import_lines):
            if imp not in content:
                lines.insert(last_app_import_idx + 1 + idx, imp)
        print("  + Import aggiunti")
    else:
        print("  ERRORE: non trovo dove inserire import!")
        return False

    # === 2. AGGIUNGI TOOL DEFINITIONS ===
    # Cerca *BROWSER_TOOLS o *MONITORING_TOOLS nella lista TOOLS_DEFINITION
    tool_def_inserted = False
    tool_def_lines = [
        "    WEB_AGENT_TOOL_DEFINITION,",
        "    ANALYZE_SCREENSHOT_TOOL_DEFINITION,",
    ]
    for i, line in enumerate(lines):
        if "*BROWSER_TOOLS," in line:
            for idx, td in enumerate(tool_def_lines):
                lines.insert(i + 1 + idx, td)
            tool_def_inserted = True
            print("  + Tool definitions aggiunti a TOOLS_DEFINITION")
            break
    if not tool_def_inserted:
        for i, line in enumerate(lines):
            if "*MONITORING_TOOLS," in line or "*WEB_TOOLS," in line:
                for idx, td in enumerate(tool_def_lines):
                    lines.insert(i + 1 + idx, td)
                tool_def_inserted = True
                print("  + Tool definitions aggiunti (fallback)")
                break
    if not tool_def_inserted:
        # Ultimo fallback: cerca la ] di chiusura di TOOLS_DEFINITION
        in_tools_def = False
        for i, line in enumerate(lines):
            if "TOOLS_DEFINITION" in line and "=" in line:
                in_tools_def = True
            if in_tools_def and line.strip() == "]":
                for idx, td in enumerate(tool_def_lines):
                    lines.insert(i + idx, td)
                tool_def_inserted = True
                print("  + Tool definitions aggiunti (prima di ])")
                break
    if not tool_def_inserted:
        print("  ATTENZIONE: tool definitions non aggiunti!")

    # === 3. AGGIUNGI PROGRESS MAP ENTRIES ===
    progress_entries = [
        '        "web_agent": lambda a: f"Navigazione autonoma: {a.get(\'goal\', \'\')}...",',
        '        "analyze_screenshot": lambda a: "Analizzo screenshot visivamente...",',
    ]
    for i, line in enumerate(lines):
        if "progress_map" in line and "{" in line:
            # Trova la prima riga dopo l'apertura del dict
            for j in range(i + 1, min(i + 30, len(lines))):
                if "}" in lines[j] and "lambda" not in lines[j]:
                    # Inserisci prima della }
                    for idx, pe in enumerate(progress_entries):
                        lines.insert(j + idx, pe)
                    print("  + Progress map entries aggiunti")
                    break
            break

    # === 4. AGGIUNGI DISPATCH (elif nel _execute_tool) ===
    dispatch_block = [
        "",
        "            # === Advanced Browser Tools ===",
        "            elif name == \"web_agent\":",
        "                from app.tools.browser_tools import BROWSER_TOOL_HANDLERS as _bt_handlers",
        "                import base64, os",
        "                async def _screenshot_base64():",
        "                    page = await browser_manager.get_new_page()",
        "                    img_bytes = await page.screenshot(full_page=False)",
        "                    await page.close()",
        "                    return base64.b64encode(img_bytes).decode('utf-8')",
        "                browser_fns = {",
        "                    'browser_navigate': lambda url, **kw: _bt_handlers['browser_navigate'](url),",
        "                    'browser_click': lambda selector, **kw: _bt_handlers['browser_click'](selector),",
        "                    'browser_fill': lambda selector, text, **kw: _bt_handlers['browser_fill'](selector, text),",
        "                    'browser_screenshot': _screenshot_base64,",
        "                    'browser_evaluate': lambda expression, **kw: _bt_handlers['browser_evaluate'](expression),",
        "                }",
        "                result = await execute_web_agent(",
        "                    goal=args.get('goal', ''),",
        "                    start_url=args.get('start_url'),",
        "                    max_steps=args.get('max_steps', 10),",
        "                    browser_tools=browser_fns,",
        "                    screenshot_analyzer_fn=lambda img, q: execute_analyze_screenshot(question=q, screenshot_base64=img),",
        "                )",
        "                return json.dumps(result, ensure_ascii=False)",
        "",
        "            elif name == \"analyze_screenshot\":",
        "                from app.tools.browser_tools import browser_manager",
        "                import base64",
        "                async def _take_screenshot_b64():",
        "                    page = await browser_manager.get_new_page()",
        "                    img_bytes = await page.screenshot(full_page=False)",
        "                    await page.close()",
        "                    return base64.b64encode(img_bytes).decode('utf-8')",
        "                result = await execute_analyze_screenshot(",
        "                    question=args.get('question', ''),",
        "                    screenshot_base64=args.get('screenshot_base64'),",
        "                    browser_screenshot_fn=_take_screenshot_b64,",
        "                )",
        "                return json.dumps(result, ensure_ascii=False)",
    ]

    # Cerca dove inserire: dopo BROWSER_TOOL_HANDLERS dispatch
    dispatch_inserted = False
    for i, line in enumerate(lines):
        if "BROWSER_TOOL_HANDLERS" in line and "elif" in line:
            # Trova la fine di questo blocco (la riga con "return str")
            for j in range(i + 1, min(i + 5, len(lines))):
                if "return str" in lines[j]:
                    for idx, d_line in enumerate(dispatch_block):
                        lines.insert(j + 1 + idx, d_line)
                    dispatch_inserted = True
                    print("  + Dispatch web_agent e analyze_screenshot aggiunti")
                    break
            break

    if not dispatch_inserted:
        # Fallback: cerca "non riconosciuto" o "# CUSTOM TOOLS"
        for i, line in enumerate(lines):
            if "non riconosciuto" in line or "# CUSTOM TOOLS" in line:
                insert_at = i - 1 if "non riconosciuto" in line else i
                for idx, d_line in enumerate(dispatch_block):
                    lines.insert(insert_at + idx, d_line)
                dispatch_inserted = True
                print("  + Dispatch aggiunto (fallback)")
                break

    if not dispatch_inserted:
        print("  ATTENZIONE: dispatch non aggiunto! Aggiungilo manualmente.")

    # === 5. AGGIUNGI MODEL ROUTING ===
    # Cerca model="gpt-4.1-mini" nella chiamata OpenAI e sostituisci
    model_routing_done = False
    for i, line in enumerate(lines):
        if 'model="gpt-4.1-mini"' in line or "model='gpt-4.1-mini'" in line:
            # Inserisci la riga di routing PRIMA della chiamata
            # Cerca indietro per trovare "response = " o "await self.client"
            # Sostituisci la riga del model con routing
            new_line = line.replace(
                'model="gpt-4.1-mini"',
                'model=route_model(user_message=user_message, message_history=messages),'
            ).replace(
                "model='gpt-4.1-mini'",
                "model=route_model(user_message=user_message, message_history=messages),"
            )
            # Rimuovi la virgola doppia se presente
            new_line = new_line.replace(",,", ",")
            lines[i] = new_line
            model_routing_done = True
            print("  + Model routing integrato")
            break

    if not model_routing_done:
        # Fallback: cerca qualsiasi model= nella chiamata chat.completions.create
        for i, line in enumerate(lines):
            if "model=" in line and "completions" not in line and "gpt" in line:
                new_line = line.replace(
                    'model="gpt-4.1-mini"',
                    'model=route_model(user_message=user_message, message_history=messages)'
                )
                if new_line != line:
                    lines[i] = new_line
                    model_routing_done = True
                    print("  + Model routing integrato (fallback)")
                    break

    if not model_routing_done:
        print("  NOTA: model routing non inserito automaticamente.")
        print("        Sostituisci manualmente model=\"gpt-4.1-mini\" con:")
        print("        model=route_model(user_message=user_message, message_history=messages)")

    # === 6. AGGIUNGI user_message extraction ===
    # Cerca dove si prepara api_messages e aggiungi user_message extraction
    for i, line in enumerate(lines):
        if "api_messages" in line and "=" in line and "messages" in line:
            # Controlla se user_message e' gia' definito
            if "user_message" not in "\n".join(lines[max(0, i-5):i]):
                lines.insert(i, "            user_message = message  # Per model routing")
                print("  + user_message extraction aggiunto")
            break

    # Scrivi il file
    COORDINATOR_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  coordinator.py patchato con successo!")
    return True


def patch_env():
    print("\nPATCH .env")
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
    else:
        content = ""

    additions = []
    if "OPENAI_MODEL_DEFAULT" not in content:
        additions.append("OPENAI_MODEL_DEFAULT=gpt-4.1-mini")
    if "OPENAI_MODEL_LARGE" not in content:
        additions.append("OPENAI_MODEL_LARGE=gpt-4.1")

    if additions:
        with open(ENV_FILE, "a") as f:
            f.write("\n# Model routing\n")
            for a in additions:
                f.write(a + "\n")
        print("  + Variabili model routing aggiunte al .env")
    else:
        print("  Gia presente. Salto.")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("  NIK29 — Advanced Browser (web_agent + vision + routing)")
    print("=" * 60)

    if not COORDINATOR_FILE.exists():
        print(f"\nERRORE: esegui dalla root del progetto!")
        print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
        print("  python3 patch_advanced_browser_v2.py")
        sys.exit(1)

    ok1 = patch_coordinator()
    ok2 = patch_env()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("  TUTTO OK! Ora fai:")
        print("  docker compose build && docker compose up -d")
        print("")
        print("  Test: chiedi a nik29 'cerca su internet quanto costano")
        print("  i materassi memory foam dei concorrenti'")
    else:
        print("  ERRORI — controlla sopra")
    print("=" * 60 + "\n")
