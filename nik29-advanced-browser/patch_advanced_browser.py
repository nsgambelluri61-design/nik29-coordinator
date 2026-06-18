#!/usr/bin/env python3
"""
patch_advanced_browser.py — Patches coordinator.py to integrate advanced browser capabilities
==============================================================================================
This script:
1. Adds imports for web_agent, screenshot_analyzer, and model_router
2. Adds tool definitions for web_agent and analyze_screenshot to TOOLS_DEFINITION
3. Adds dispatch cases for the new tools
4. Integrates the model router into the chat endpoint
5. Adds OPENAI_MODEL_LARGE=gpt-4.1 to .env

The script uses pattern-based search (not line numbers) to find insertion points.
It creates backups before modifying any file.

Usage:
    python3 patch_advanced_browser.py [--coordinator-path app/coordinator.py] [--env-path .env] [--dry-run]
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime


# ============================================================================
# PATCH CONTENT BLOCKS
# ============================================================================

IMPORT_BLOCK = '''
# --- Advanced Browser Capabilities (auto-patched) ---
from app.tools.web_agent import execute_web_agent, WEB_AGENT_TOOL_DEFINITION
from app.tools.screenshot_analyzer import execute_analyze_screenshot, ANALYZE_SCREENSHOT_TOOL_DEFINITION
from app.routing.model_router import route_model, get_router
# --- End Advanced Browser Imports ---
'''

TOOL_DEFINITIONS_BLOCK = '''
    # --- Advanced Browser Tool Definitions (auto-patched) ---
    {
        "type": "function",
        "function": {
            "name": "web_agent",
            "description": "Autonomous web navigation agent. Takes a goal and autonomously navigates web pages (opens, reads, clicks, fills forms) until it finds the answer or reaches max_steps. Use for complex multi-step web research tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "The navigation goal to achieve (what information to find or action to perform)"
                    },
                    "start_url": {
                        "type": "string",
                        "description": "Optional starting URL. If not provided, the agent will decide where to start."
                    },
                    "max_steps": {
                        "type": "integer",
                        "description": "Maximum navigation steps before stopping (default: 10)",
                        "default": 10
                    }
                },
                "required": ["goal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_screenshot",
            "description": "Analyze a browser screenshot visually using GPT-4.1 vision. Describes page layout, identifies buttons, reads text, analyzes colors, finds navigation elements. Use when you need to visually understand what is on a web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "What to analyze or look for in the screenshot (e.g., 'What products are shown?', 'Where is the search bar?')"
                    },
                    "screenshot_base64": {
                        "type": "string",
                        "description": "Base64-encoded screenshot image. If not provided, a fresh screenshot will be taken."
                    }
                },
                "required": ["question"]
            }
        }
    },
    # --- End Advanced Browser Tool Definitions ---
'''

DISPATCH_BLOCK = '''
            # --- Advanced Browser Dispatch (auto-patched) ---
            elif fn_name == "web_agent":
                goal = fn_args.get("goal", "")
                start_url = fn_args.get("start_url")
                max_steps = fn_args.get("max_steps", 10)
                # Build browser_tools dict from existing tool functions
                browser_tools_dict = {
                    "browser_navigate": browser_navigate,
                    "browser_click": browser_click,
                    "browser_fill": browser_fill,
                    "browser_screenshot": browser_screenshot,
                    "browser_evaluate": browser_evaluate,
                }
                from app.tools.screenshot_analyzer import execute_analyze_screenshot as _analyze_fn
                async def _screenshot_analyzer_fn(img_b64, question):
                    result = await _analyze_fn(
                        question=question,
                        screenshot_base64=img_b64,
                        model=os.getenv("OPENAI_MODEL_LARGE", "gpt-4.1"),
                        client=client,
                    )
                    return result.get("analysis", "Analysis failed")
                tool_result = await execute_web_agent(
                    goal=goal,
                    start_url=start_url,
                    max_steps=max_steps,
                    browser_tools=browser_tools_dict,
                    screenshot_analyzer_fn=_screenshot_analyzer_fn,
                    model=os.getenv("OPENAI_MODEL_LARGE", "gpt-4.1"),
                    client=client,
                )
                import json as _json
                tool_result_str = _json.dumps(tool_result, ensure_ascii=False, default=str)

            elif fn_name == "analyze_screenshot":
                question = fn_args.get("question", "Describe what you see")
                screenshot_b64 = fn_args.get("screenshot_base64")
                tool_result = await execute_analyze_screenshot(
                    question=question,
                    screenshot_base64=screenshot_b64,
                    browser_screenshot_fn=browser_screenshot,
                    model=os.getenv("OPENAI_MODEL_LARGE", "gpt-4.1"),
                    client=client,
                )
                import json as _json
                tool_result_str = _json.dumps(tool_result, ensure_ascii=False, default=str)
            # --- End Advanced Browser Dispatch ---
'''

MODEL_ROUTER_BLOCK = '''
        # --- Model Router Integration (auto-patched) ---
        # Determine the best model for this request
        _user_msg_text = ""
        for _m in reversed(messages):
            if _m.get("role") == "user":
                if isinstance(_m.get("content"), str):
                    _user_msg_text = _m["content"]
                elif isinstance(_m.get("content"), list):
                    _user_msg_text = " ".join(
                        part.get("text", "") for part in _m["content"] if part.get("type") == "text"
                    )
                break
        model_to_use = route_model(
            user_message=_user_msg_text,
            message_history=messages,
            force_model=None,  # Set to a model name to override routing
        )
        # --- End Model Router Integration ---
'''

ENV_ADDITIONS = """
# --- Advanced Browser Config (auto-patched) ---
OPENAI_MODEL_LARGE=gpt-4.1
OPENAI_MODEL_DEFAULT=gpt-4.1-mini
# OPENAI_MODEL_FORCE=  # Uncomment and set to force a specific model always
# --- End Advanced Browser Config ---
"""


# ============================================================================
# PATCHING LOGIC
# ============================================================================

class PatchError(Exception):
    """Raised when patching fails."""
    pass


def backup_file(filepath: Path) -> Path:
    """Create a timestamped backup of a file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.with_suffix(f".backup_{timestamp}{filepath.suffix}")
    shutil.copy2(filepath, backup_path)
    print(f"  [BACKUP] {filepath} -> {backup_path}")
    return backup_path


def is_already_patched(content: str) -> bool:
    """Check if the file has already been patched."""
    return "Advanced Browser Capabilities (auto-patched)" in content


def find_insertion_point(content: str, patterns: list, description: str) -> int:
    """
    Find the best insertion point by trying multiple patterns.
    Returns the character index for insertion.
    """
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            return match.end()
    raise PatchError(f"Could not find insertion point for: {description}\nTried patterns: {patterns}")


def find_line_insertion_point(content: str, patterns: list, description: str, before: bool = False) -> int:
    """
    Find insertion point at the beginning or end of a matched line.
    If before=True, inserts before the matched line.
    If before=False, inserts after the matched line.
    """
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            if before:
                # Find the start of the line
                line_start = content.rfind("\n", 0, match.start())
                return line_start + 1 if line_start != -1 else 0
            else:
                # Find the end of the line
                line_end = content.find("\n", match.end())
                return line_end + 1 if line_end != -1 else len(content)
    raise PatchError(f"Could not find line for: {description}\nTried patterns: {patterns}")


def patch_imports(content: str) -> str:
    """Add import statements to coordinator.py."""
    # Try to find existing imports section — insert after the last 'from' or 'import' at top level
    # Strategy: find the last import/from statement before any function/class definition
    patterns = [
        # After existing browser_tools import
        r"^from\s+.*browser_tools.*import.*$",
        # After any 'from app.' import
        r"^from\s+app\..*import.*$",
        # After openai import
        r"^from\s+openai\s+import.*$",
        # After any import block
        r"^import\s+\w+.*$",
    ]

    # Find the last import line before code starts
    import_lines = list(re.finditer(r"^(?:from|import)\s+.+$", content, re.MULTILINE))
    if import_lines:
        last_import = import_lines[-1]
        line_end = content.find("\n", last_import.end())
        insert_pos = line_end + 1 if line_end != -1 else last_import.end()
    else:
        # Fallback: insert at the very beginning after any shebang/docstring
        insert_pos = 0
        if content.startswith("#!"):
            first_newline = content.find("\n")
            insert_pos = first_newline + 1

    return content[:insert_pos] + IMPORT_BLOCK + content[insert_pos:]


def patch_tool_definitions(content: str) -> str:
    """Add tool definitions to TOOLS_DEFINITION list."""
    # Strategy: find the TOOLS_DEFINITION list and insert before its closing bracket
    # Pattern 1: Find the last tool definition entry before the list closes
    patterns_list_end = [
        # Look for the closing bracket of TOOLS_DEFINITION (could be TOOLS_DEFINITION or TOOLS or tools)
        r"(TOOLS_DEFINITION|TOOLS|tools)\s*=\s*\[",
    ]

    # Find the variable name
    list_match = None
    for pattern in patterns_list_end:
        list_match = re.search(pattern, content)
        if list_match:
            break

    if not list_match:
        raise PatchError(
            "Could not find TOOLS_DEFINITION (or TOOLS) list in coordinator.py. "
            "Please ensure a tools list variable exists."
        )

    # Find the matching closing bracket
    # Count brackets from the opening [
    start_bracket = content.find("[", list_match.start())
    if start_bracket == -1:
        raise PatchError("Could not find opening bracket of tools list")

    bracket_count = 0
    pos = start_bracket
    while pos < len(content):
        if content[pos] == "[":
            bracket_count += 1
        elif content[pos] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                # Found the closing bracket
                # Insert before it
                return content[:pos] + TOOL_DEFINITIONS_BLOCK + "\n" + content[pos:]
        pos += 1

    raise PatchError("Could not find closing bracket of tools list")


def patch_dispatch(content: str) -> str:
    """Add dispatch cases for new tools."""
    # Strategy: find existing tool dispatch (elif fn_name == "browser_...) and insert after the last one
    # Look for the last browser tool dispatch block
    patterns = [
        # After browser_evaluate dispatch
        r'elif\s+fn_name\s*==\s*["\']browser_evaluate["\'].*?(?=\n\s*elif|\n\s*else:)',
        # After browser_screenshot dispatch
        r'elif\s+fn_name\s*==\s*["\']browser_screenshot["\'].*?(?=\n\s*elif|\n\s*else:)',
        # After any browser_ dispatch
        r'elif\s+fn_name\s*==\s*["\']browser_\w+["\'].*?(?=\n\s*elif|\n\s*else:)',
        # After any elif fn_name dispatch (generic)
        r'elif\s+fn_name\s*==\s*["\'][^"\']+["\'].*?tool_result.*?\n',
    ]

    # Find all elif fn_name blocks
    dispatch_matches = list(re.finditer(
        r'(elif|if)\s+fn_name\s*==\s*["\'](\w+)["\']',
        content
    ))

    if not dispatch_matches:
        raise PatchError(
            "Could not find tool dispatch pattern (elif fn_name == '...') in coordinator.py"
        )

    # Find the last dispatch block — we'll insert after it
    # Look for the last browser-related dispatch, or the last dispatch before 'else:'
    last_browser_dispatch = None
    last_dispatch = None
    for match in dispatch_matches:
        tool_name = match.group(2)
        last_dispatch = match
        if tool_name.startswith("browser_"):
            last_browser_dispatch = match

    target_match = last_browser_dispatch or last_dispatch

    # Find the end of this elif block (next elif or else at same indentation)
    target_pos = target_match.start()
    # Get indentation
    line_start = content.rfind("\n", 0, target_pos) + 1
    indent = len(content[line_start:target_pos]) - len(content[line_start:target_pos].lstrip())

    # Find next elif/else at same or lesser indentation after this match
    search_start = target_pos + 1
    next_block = re.search(
        r"\n" + r" " * indent + r"(elif|else)",
        content[search_start:]
    )

    if next_block:
        insert_pos = search_start + next_block.start()
    else:
        # Insert before the next unindented line or end of function
        next_line = content.find("\n", search_start)
        insert_pos = next_line if next_line != -1 else len(content)

    return content[:insert_pos] + "\n" + DISPATCH_BLOCK + content[insert_pos:]


def patch_model_router(content: str) -> str:
    """Integrate model router into the chat completion call."""
    # Strategy: find where the model is used in the chat completion call
    # and replace it with the routed model

    # Pattern 1: Find model=MODEL_NAME or model=os.getenv("MODEL_NAME"...) or model=config["model"]
    model_patterns = [
        # model=MODEL_NAME variable
        r'(model\s*=\s*)(MODEL_NAME|model_name|MODEL)',
        # model=os.getenv(...)
        r'(model\s*=\s*)(os\.getenv\([^)]*\))',
        # model="gpt-4.1-mini"
        r'(model\s*=\s*)(["\']gpt-4\.1-mini["\'])',
        # model=config[...]
        r'(model\s*=\s*)(config\[.+?\])',
    ]

    # First, try to find and replace the model variable in the completion call
    replaced = False
    for pattern in model_patterns:
        match = re.search(pattern, content)
        if match:
            # Find the chat.completions.create call that contains this
            # Insert the router block before the completion call
            # Find the line with client.chat.completions.create (or similar)
            completion_patterns = [
                r"(await\s+)?client\.chat\.completions\.create\s*\(",
                r"(await\s+)?openai_client\.chat\.completions\.create\s*\(",
                r"(await\s+)?self\.client\.chat\.completions\.create\s*\(",
            ]

            for cp in completion_patterns:
                comp_match = re.search(cp, content)
                if comp_match:
                    # Insert router block before the completion call line
                    line_start = content.rfind("\n", 0, comp_match.start()) + 1
                    content = content[:line_start] + MODEL_ROUTER_BLOCK + "\n" + content[line_start:]

                    # Now replace model= with model=model_to_use
                    content = re.sub(pattern, r"\1model_to_use", content, count=1)
                    replaced = True
                    break

            if replaced:
                break

    if not replaced:
        # Fallback: just insert the router block before the first completion call
        completion_patterns = [
            r"(await\s+)?client\.chat\.completions\.create\s*\(",
            r"(await\s+)?openai_client\.chat\.completions\.create\s*\(",
            r"completion\s*=",
            r"response\s*=\s*(await\s+)?.*completions",
        ]

        for cp in completion_patterns:
            comp_match = re.search(cp, content)
            if comp_match:
                line_start = content.rfind("\n", 0, comp_match.start()) + 1
                content = content[:line_start] + MODEL_ROUTER_BLOCK + "\n" + content[line_start:]
                print("  [WARN] Could not auto-replace model= parameter. "
                      "Please manually change model= to model=model_to_use in the completion call.")
                replaced = True
                break

        if not replaced:
            print("  [WARN] Could not find chat completion call. "
                  "Model router block inserted at end of file — manual integration needed.")
            content += "\n\n# TODO: Integrate model_to_use into your chat completion call\n"
            content += MODEL_ROUTER_BLOCK

    return content


def patch_env_file(env_path: Path) -> None:
    """Add advanced browser config to .env file."""
    if env_path.exists():
        existing = env_path.read_text()
        if "OPENAI_MODEL_LARGE" in existing:
            print(f"  [SKIP] {env_path} already contains OPENAI_MODEL_LARGE")
            return
        backup_file(env_path)
        with open(env_path, "a") as f:
            f.write("\n" + ENV_ADDITIONS)
    else:
        with open(env_path, "w") as f:
            f.write(ENV_ADDITIONS)
    print(f"  [OK] Updated {env_path}")


def patch_coordinator(coordinator_path: Path, dry_run: bool = False) -> str:
    """
    Apply all patches to coordinator.py.

    Returns the patched content (writes to file unless dry_run).
    """
    if not coordinator_path.exists():
        raise PatchError(f"coordinator.py not found at: {coordinator_path}")

    content = coordinator_path.read_text()

    if is_already_patched(content):
        print(f"  [SKIP] {coordinator_path} is already patched")
        return content

    # Create backup
    if not dry_run:
        backup_file(coordinator_path)

    print("\n  [1/4] Patching imports...")
    content = patch_imports(content)

    print("  [2/4] Patching tool definitions...")
    content = patch_tool_definitions(content)

    print("  [3/4] Patching dispatch...")
    content = patch_dispatch(content)

    print("  [4/4] Patching model router...")
    content = patch_model_router(content)

    if not dry_run:
        coordinator_path.write_text(content)
        print(f"\n  [OK] Patched {coordinator_path} successfully!")
    else:
        print(f"\n  [DRY-RUN] Would patch {coordinator_path}")

    return content


# ============================================================================
# INIT FILES
# ============================================================================

def ensure_init_files(base_path: Path) -> None:
    """Ensure __init__.py files exist in the new module directories."""
    tools_init = base_path / "app" / "tools" / "__init__.py"
    routing_init = base_path / "app" / "routing" / "__init__.py"

    for init_path in [tools_init, routing_init]:
        init_path.parent.mkdir(parents=True, exist_ok=True)
        if not init_path.exists():
            init_path.write_text('"""Auto-generated __init__.py"""\n')
            print(f"  [OK] Created {init_path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Patch coordinator.py to integrate advanced browser capabilities"
    )
    parser.add_argument(
        "--coordinator-path",
        default="app/coordinator.py",
        help="Path to coordinator.py (default: app/coordinator.py)"
    )
    parser.add_argument(
        "--env-path",
        default=".env",
        help="Path to .env file (default: .env)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files"
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base project path (default: current directory)"
    )

    args = parser.parse_args()

    base_path = Path(args.base_path).resolve()
    coordinator_path = base_path / args.coordinator_path
    env_path = base_path / args.env_path

    print("=" * 60)
    print("  Advanced Browser Capabilities — Patch Script")
    print("=" * 60)
    print(f"\n  Base path:       {base_path}")
    print(f"  Coordinator:     {coordinator_path}")
    print(f"  .env:            {env_path}")
    print(f"  Dry run:         {args.dry_run}")
    print()

    # Step 1: Ensure directory structure and __init__.py files
    print("[STEP 1] Ensuring module structure...")
    ensure_init_files(base_path)

    # Step 2: Patch .env
    print("\n[STEP 2] Patching .env file...")
    if not args.dry_run:
        patch_env_file(env_path)
    else:
        print(f"  [DRY-RUN] Would update {env_path}")

    # Step 3: Patch coordinator.py
    print("\n[STEP 3] Patching coordinator.py...")
    try:
        patch_coordinator(coordinator_path, dry_run=args.dry_run)
    except PatchError as e:
        print(f"\n  [ERROR] {e}")
        print("\n  The patch script could not automatically patch coordinator.py.")
        print("  Please apply the changes manually following README_ADVANCED_BROWSER.md")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  PATCH COMPLETE!")
    print("=" * 60)
    print("\n  Next steps:")
    print("  1. Review the patched coordinator.py")
    print("  2. Rebuild Docker: docker-compose build")
    print("  3. Restart: docker-compose up -d")
    print("  4. Test: curl http://localhost:4001/health")
    print()


if __name__ == "__main__":
    main()
