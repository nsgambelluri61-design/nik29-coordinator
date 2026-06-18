# Advanced Browser Capabilities for nik29-coordinator

This upgrade package adds advanced, autonomous browser capabilities and intelligent model routing to the `nik29-coordinator` service.

## 🚀 Features

1. **Autonomous Multi-Step Navigation Loop (`web_agent`)**
   - Takes a high-level goal (e.g., "find the price of memory foam mattresses")
   - Autonomously navigates pages, reads content, decides what to click, and explores until the goal is met
   - Uses the existing `browser_tools` (navigate, click, fill, evaluate) under the hood
   - Prevents infinite loops with a `max_steps` limit

2. **Visual Screenshot Analysis (`analyze_screenshot`)**
   - Takes a screenshot using the browser and sends it to GPT-4.1 with vision capabilities
   - Can answer questions about page layout, colors, buttons, text positioning, and structure
   - Used internally by `web_agent` when pages are too complex to read via DOM

3. **Intelligent Model Routing (`model_router`)**
   - Automatically routes simple requests to `gpt-4.1-mini` (fast, cheap)
   - Automatically routes complex requests (web agent, vision, deep analysis, code gen) to `gpt-4.1` (powerful)
   - Configurable via `.env` overrides

## 📁 Package Contents

```text
nik29-advanced-browser/
├── app/
│   ├── tools/
│   │   ├── web_agent.py             # Autonomous navigation loop
│   │   └── screenshot_analyzer.py   # Visual analysis with GPT-4.1 vision
│   └── routing/
│       └── model_router.py          # Intelligent model routing logic
├── patch_advanced_browser.py        # Robust auto-patching script
└── README_ADVANCED_BROWSER.md       # This file
```

## 🛠️ Installation

### Method 1: Automatic Patching (Recommended)

The provided patch script uses robust regex pattern matching to inject the new capabilities into your existing `coordinator.py` without relying on exact line numbers.

1. Copy the package contents into your `nik29-coordinator` project root:
   ```bash
   cp -r nik29-advanced-browser/* /path/to/your/nik29-coordinator/
   ```

2. Run the patch script in dry-run mode to see what it will do:
   ```bash
   cd /path/to/your/nik29-coordinator
   python3 patch_advanced_browser.py --dry-run
   ```

3. If everything looks good, apply the patch:
   ```bash
   python3 patch_advanced_browser.py
   ```
   *(Note: The script automatically creates timestamped backups of `coordinator.py` and `.env` before modifying them.)*

4. Rebuild and restart the Docker container:
   ```bash
   docker-compose build coordinator
   docker-compose up -d coordinator
   ```

### Method 2: Manual Integration

If the auto-patch script fails (or you prefer manual control), follow these steps:

1. **Copy the files**
   Copy `app/tools/web_agent.py`, `app/tools/screenshot_analyzer.py`, and `app/routing/model_router.py` into your project.

2. **Update `.env`**
   Add these variables:
   ```env
   OPENAI_MODEL_LARGE=gpt-4.1
   OPENAI_MODEL_DEFAULT=gpt-4.1-mini
   ```

3. **Update `app/coordinator.py`**
   - Import the new modules at the top.
   - Add `WEB_AGENT_TOOL_DEFINITION` and `ANALYZE_SCREENSHOT_TOOL_DEFINITION` to your `TOOLS_DEFINITION` list.
   - In your tool dispatch loop (`elif fn_name == ...`), add cases for `web_agent` and `analyze_screenshot` (see the patch script source for the exact implementation).
   - In your chat completion call, replace the static `model="gpt-4.1-mini"` with the dynamic model returned by `route_model(user_message, messages)`.

## 🧪 Testing

Test the new capabilities via the chat endpoint:

**Test 1: Intelligent Routing (Simple)**
Send a simple message: `"Ciao, come stai?"`
*Expected: The coordinator uses `gpt-4.1-mini`.*

**Test 2: Intelligent Routing (Complex)**
Send a complex message: `"Fai un'analisi approfondita e step-by-step dell'architettura."`
*Expected: The coordinator automatically switches to `gpt-4.1`.*

**Test 3: Web Agent**
Send a goal: `"Usa il web_agent per trovare il prezzo del materasso memory foam su ildormire.com"`
*Expected: The agent will autonomously open the site, search/click, and return a structured summary.*

**Test 4: Screenshot Analyzer**
Send a request: `"Vai su google.com e usa analyze_screenshot per dirmi di che colore è il logo principale."`
*Expected: The agent takes a screenshot and GPT-4.1 vision describes it.*
