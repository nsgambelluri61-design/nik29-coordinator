"""
self_evolution_service.py
=========================
Servizio standalone per la self-evolution di nik29-coordinator.
Gira come processo separato sulla porta 4005 dentro il container.
NON modifica coordinator.py, main.py, né alcun file critico.

Il coordinator può chiamarlo via:
  curl -X POST http://localhost:4005/create_tool -H "Content-Type: application/json" \
       -d '{"name":"meteo","description":"Recupera il meteo di una città"}'

Se questo servizio crasha, il coordinator continua a funzionare normalmente.
"""

import os
import sys
import json
import shutil
import asyncio
import subprocess
import importlib
import importlib.util
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# === CONFIGURAZIONE ===

CUSTOM_TOOLS_DIR = Path("/app/app/tools/custom")
REGISTRY_PATH = CUSTOM_TOOLS_DIR / "registry.json"
MEMORY_DIR = Path("/data/memory")
EVOLUTION_LOG = MEMORY_DIR / "self_evolution_log.json"
APP_ROOT = Path("/app")

MAX_FIX_ATTEMPTS = 3
SERVICE_PORT = 4005

# File che NON possono essere toccati per nessun motivo
PROTECTED_FILES = [
    "main.py",
    "coordinator.py",
    "persistent_memory.py",
    "semantic_memory.py",
    "config.py",
    "__init__.py",
]

# === OPENAI CLIENT ===

_openai_client = None


def get_openai_client():
    """Lazy init del client OpenAI."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_API_BASE"),
        )
    return _openai_client


# === MODELLI PYDANTIC ===

class CreateToolRequest(BaseModel):
    name: str = Field(..., description="Nome del tool in snake_case")
    description: str = Field(..., description="Descrizione di cosa deve fare il tool")
    parameters: str = Field(default="", description="Parametri opzionali (es. 'url: str, timeout: int = 30')")


class ToolResponse(BaseModel):
    success: bool
    message: str = ""
    data: dict = {}


# === REGISTRY ===

def load_registry() -> list:
    """Carica il registry dei tool custom."""
    try:
        if REGISTRY_PATH.exists():
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"[self_evolution] Errore lettura registry: {e}")
    return []


def save_registry(registry: list):
    """Salva il registry in modo atomico."""
    try:
        CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = REGISTRY_PATH.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        tmp_path.replace(REGISTRY_PATH)
    except (IOError, OSError) as e:
        print(f"[self_evolution] Errore salvataggio registry: {e}")


def register_tool_entry(name: str, description: str, parameters: str, file_path: str):
    """Aggiunge un tool al registry (evita duplicati)."""
    registry = load_registry()
    registry = [t for t in registry if t.get("name") != name]
    registry.append({
        "name": name,
        "description": description,
        "parameters": parameters,
        "file_path": file_path,
        "created_at": datetime.now().isoformat(),
        "active": True,
    })
    save_registry(registry)


def unregister_tool_entry(name: str):
    """Rimuove un tool dal registry."""
    registry = load_registry()
    registry = [t for t in registry if t.get("name") != name]
    save_registry(registry)


# === EVOLUTION LOG ===

def log_event(event: dict):
    """Logga un evento nel file di evoluzione."""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        log = []
        if EVOLUTION_LOG.exists():
            try:
                with open(EVOLUTION_LOG, "r", encoding="utf-8") as f:
                    log = json.load(f)
            except (json.JSONDecodeError, IOError):
                log = []

        event["timestamp"] = datetime.now().isoformat()
        log.append(event)
        log = log[-200:]  # Mantieni ultimi 200 eventi

        with open(EVOLUTION_LOG, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[self_evolution] Errore log: {e}")


# === INSTALLAZIONE DIPENDENZE ===

def install_missing_deps(code: str) -> list:
    """Analizza il codice, trova import non disponibili e li installa."""
    import ast

    installed = []
    # Moduli standard Python 3.11+
    stdlib = {
        "os", "sys", "json", "asyncio", "pathlib", "datetime", "typing",
        "re", "math", "random", "hashlib", "base64", "urllib", "collections",
        "itertools", "functools", "subprocess", "shutil", "tempfile", "io",
        "time", "traceback", "importlib", "inspect", "copy", "uuid", "string",
        "textwrap", "struct", "socket", "ssl", "http", "email", "html",
        "xml", "csv", "configparser", "logging", "threading", "multiprocessing",
        "concurrent", "contextlib", "abc", "dataclasses", "enum", "secrets",
        "statistics", "decimal", "fractions", "operator", "glob", "fnmatch",
        "zipfile", "tarfile", "gzip", "bz2", "lzma", "platform", "signal",
        "weakref", "array", "queue", "heapq", "bisect", "pprint",
    }
    # Librerie già nel container
    known_installed = {
        "openai", "fastapi", "uvicorn", "pydantic", "requests", "aiohttp",
        "httpx", "beautifulsoup4", "bs4", "PIL", "pillow", "numpy", "pandas",
        "starlette",
    }

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return installed

    needed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                needed.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                needed.add(node.module.split(".")[0])

    for mod in needed:
        if mod in stdlib or mod in known_installed:
            continue
        # Prova a importare
        try:
            importlib.import_module(mod)
        except ImportError:
            print(f"[self_evolution] Installo dipendenza mancante: {mod}")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", mod],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    installed.append(mod)
                    print(f"[self_evolution] ✓ {mod} installato")
                else:
                    print(f"[self_evolution] ✗ pip install {mod} fallito: {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                print(f"[self_evolution] ✗ Timeout installazione {mod}")

    return installed


# === GENERAZIONE CODICE ===

async def generate_tool_code(name: str, description: str, parameters: str) -> dict:
    """
    Usa GPT-4.1 per generare il codice di un tool.
    Ritorna {"success": bool, "code": str, "error": str}
    """
    client = get_openai_client()

    # Carica un esempio di tool esistente per contesto
    example_code = ""
    try:
        existing = list(Path("/app/app/tools").glob("*.py"))
        for f in existing[:2]:
            if f.name not in PROTECTED_FILES and f.stat().st_size < 3000:
                example_code += f"\n# --- Esempio: {f.name} ---\n"
                example_code += f.read_text(encoding="utf-8")[:1500]
                break
    except Exception:
        pass

    system_prompt = """Sei un esperto sviluppatore Python. Generi tool per un sistema multi-agente.
REGOLE TASSATIVE:
1. Rispondi SOLO con codice Python puro — NIENTE blocchi markdown, niente spiegazioni
2. La funzione principale DEVE essere async e chiamarsi esattamente come il nome del tool
3. DEVE avere type hints completi
4. DEVE ritornare un dict con almeno "result" e "success"
5. DEVE avere try/except per gestire errori
6. DEVE avere una docstring
7. Includi tutti gli import necessari all'inizio
8. Il codice deve essere production-ready"""

    user_prompt = f"""Genera il codice Python per un tool chiamato '{name}'.

DESCRIZIONE: {description}
PARAMETRI: {parameters if parameters else "Deduci i parametri appropriati dalla descrizione"}

STRUTTURA OBBLIGATORIA:
\"\"\"
Tool: {name}
Descrizione: {description}
Generato da self_evolution
\"\"\"

import ...

async def {name}(...) -> dict:
    \"\"\"
    {description}
    \"\"\"
    try:
        # implementazione
        return {{"result": ..., "success": True}}
    except Exception as e:
        return {{"result": None, "success": False, "error": str(e)}}

{f"CONTESTO — esempio di tool nel progetto:{example_code}" if example_code else ""}

Genera SOLO il codice Python."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        code = response.choices[0].message.content.strip()

        # Pulizia markdown residuo
        for prefix in ("```python\n", "```python", "```\n", "```"):
            if code.startswith(prefix):
                code = code[len(prefix):]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        # Verifica sintassi
        try:
            compile(code, f"{name}.py", "exec")
        except SyntaxError as e:
            return {"success": False, "code": code, "error": f"Sintassi non valida: {e}"}

        return {"success": True, "code": code, "error": ""}

    except Exception as e:
        return {"success": False, "code": "", "error": f"Errore GPT-4.1: {traceback.format_exc()}"}


# === FIX AUTOMATICO ===

async def attempt_fix(code: str, error: str) -> Optional[str]:
    """Tenta di fixare il codice usando GPT-4.1. Ritorna il codice corretto o None."""
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Sei un debugger Python. Correggi il codice. Rispondi SOLO con il codice Python corretto completo, NIENTE markdown."},
                {"role": "user", "content": f"Codice con errore:\n\n{code}\n\nERRORE:\n{error}\n\nRispondi SOLO con il codice corretto."},
            ],
            temperature=0.2,
            max_tokens=4000,
        )

        fixed = response.choices[0].message.content.strip()
        for prefix in ("```python\n", "```python", "```\n", "```"):
            if fixed.startswith(prefix):
                fixed = fixed[len(prefix):]
        if fixed.endswith("```"):
            fixed = fixed[:-3]
        fixed = fixed.strip()

        compile(fixed, "fix.py", "exec")
        return fixed

    except Exception:
        return None


# === GENERAZIONE PARAMETRI TEST ===

async def generate_test_params(name: str, code: str) -> dict:
    """Genera parametri di test sicuri per un tool."""
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Genera parametri di test SICURI per una funzione Python. Rispondi SOLO con un JSON valido. Usa valori innocui: stringhe brevi, numeri piccoli, URL di esempio come 'https://example.com'. NON usare file system critici."},
                {"role": "user", "content": f"Parametri di test per:\n\n{code}\n\nJSON:"},
            ],
            temperature=0.2,
            max_tokens=300,
        )

        text = response.choices[0].message.content.strip()
        for prefix in ("```json\n", "```json", "```\n", "```"):
            if text.startswith(prefix):
                text = text[len(prefix):]
        if text.endswith("```"):
            text = text[:-3]

        return json.loads(text.strip())

    except Exception as e:
        print(f"[self_evolution] Errore generazione test params: {e}")
        return {}


# === SELF TEST ===

async def run_self_test(tool_name: str) -> dict:
    """
    Testa un tool: verifica sintassi, importa, esegue con parametri generati.
    Se fallisce, tenta fix automatico (max 3 tentativi).
    """
    tool_path = CUSTOM_TOOLS_DIR / f"{tool_name}.py"
    if not tool_path.exists():
        return {"success": False, "error": f"File non trovato: {tool_path}", "attempts": 0}

    attempts = 0
    last_error = ""

    while attempts < MAX_FIX_ATTEMPTS:
        attempts += 1
        print(f"[self_evolution] Test '{tool_name}' — tentativo {attempts}/{MAX_FIX_ATTEMPTS}")

        code = tool_path.read_text(encoding="utf-8")

        # 1. Verifica sintassi
        try:
            compile(code, str(tool_path), "exec")
        except SyntaxError as e:
            last_error = f"SyntaxError: {e}"
            print(f"[self_evolution] ✗ {last_error}")
            fixed = await attempt_fix(code, last_error)
            if fixed:
                tool_path.write_text(fixed, encoding="utf-8")
                print("[self_evolution] Fix applicato, riprovo...")
            continue

        # 2. Installa dipendenze
        install_missing_deps(code)

        # 3. Importa modulo
        try:
            spec = importlib.util.spec_from_file_location(tool_name, str(tool_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            last_error = f"ImportError: {traceback.format_exc()}"
            print(f"[self_evolution] ✗ Import fallito: {e}")
            fixed = await attempt_fix(code, last_error)
            if fixed:
                tool_path.write_text(fixed, encoding="utf-8")
            continue

        # 4. Verifica funzione
        if not hasattr(module, tool_name):
            last_error = f"Funzione '{tool_name}' non trovata nel modulo"
            print(f"[self_evolution] ✗ {last_error}")
            fixed = await attempt_fix(code, last_error)
            if fixed:
                tool_path.write_text(fixed, encoding="utf-8")
            continue

        func = getattr(module, tool_name)

        # 5. Genera parametri di test
        test_params = await generate_test_params(tool_name, code)

        # 5b. Fallback: se test_params è vuoto, usa introspezione
        if not test_params:
            import inspect
            sig = inspect.signature(func)
            for param_name, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    test_params[param_name] = param.default
                elif param.annotation == str or 'str' in str(param.annotation):
                    test_params[param_name] = "Roma"
                elif param.annotation == int or 'int' in str(param.annotation):
                    test_params[param_name] = 1
                elif param.annotation == float or 'float' in str(param.annotation):
                    test_params[param_name] = 1.0
                elif param.annotation == bool or 'bool' in str(param.annotation):
                    test_params[param_name] = True
                elif param.annotation == list or 'list' in str(param.annotation):
                    test_params[param_name] = []
                elif param.annotation == dict or 'dict' in str(param.annotation):
                    test_params[param_name] = {}
                else:
                    test_params[param_name] = "test"
            print(f"[self_evolution] Fallback params: {test_params}")

        # 6. Esegui
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**test_params), timeout=30)
            else:
                result = func(**test_params)

            print(f"[self_evolution] ✓ Test superato! Output: {str(result)[:200]}")
            return {
                "success": True,
                "error": "",
                "attempts": attempts,
                "test_output": str(result)[:500],
            }

        except asyncio.TimeoutError:
            last_error = "Timeout (>30s)"
        except Exception as e:
            last_error = f"RuntimeError: {traceback.format_exc()}"

        print(f"[self_evolution] ✗ Esecuzione fallita: {last_error[:200]}")

        if attempts < MAX_FIX_ATTEMPTS:
            fixed = await attempt_fix(code, last_error)
            if fixed:
                tool_path.write_text(fixed, encoding="utf-8")
                print("[self_evolution] Fix applicato, riprovo...")

    return {"success": False, "error": last_error, "attempts": attempts}


# === GIT DEPLOY ===

async def git_deploy(message: str = "") -> dict:
    """Esegue git add + commit + push. Retry una volta se push fallisce."""
    if not message:
        message = f"[self_evolution] Update {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    try:
        # git add
        r = subprocess.run(["git", "add", "-A"], cwd=str(APP_ROOT),
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return {"success": False, "commit_hash": "", "error": f"git add: {r.stderr}"}

        # git commit
        r = subprocess.run(["git", "commit", "-m", message], cwd=str(APP_ROOT),
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            if "nothing to commit" in (r.stdout + r.stderr):
                return {"success": True, "commit_hash": "no_changes", "error": ""}
            return {"success": False, "commit_hash": "", "error": f"git commit: {r.stderr}"}

        # commit hash
        r_hash = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(APP_ROOT),
                                capture_output=True, text=True, timeout=5)
        commit_hash = r_hash.stdout.strip() if r_hash.returncode == 0 else "unknown"

        # git push (2 tentativi)
        for attempt in range(2):
            r = subprocess.run(["git", "push"], cwd=str(APP_ROOT),
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                print(f"[self_evolution] ✓ Push OK — commit {commit_hash}")
                return {"success": True, "commit_hash": commit_hash, "error": ""}

            if attempt == 0:
                # pull --rebase prima di riprovare
                subprocess.run(["git", "pull", "--rebase"], cwd=str(APP_ROOT),
                               capture_output=True, text=True, timeout=30)

        return {"success": False, "commit_hash": commit_hash, "error": f"push fallito: {r.stderr}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "commit_hash": "", "error": "Timeout git"}
    except Exception as e:
        return {"success": False, "commit_hash": "", "error": str(e)}


# === WORKFLOW COMPLETO ===

async def full_create_tool(name: str, description: str, parameters: str = "") -> dict:
    """Workflow: genera → salva → testa → deploya."""
    print(f"\n{'='*60}")
    print(f"[self_evolution] CREAZIONE TOOL: {name}")
    print(f"{'='*60}")

    # Validazione
    clean_name = name.strip().lower().replace(" ", "_").replace("-", "_")
    clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
    if not clean_name or not clean_name.isidentifier():
        return {"success": False, "message": f"Nome '{name}' non valido come identificatore Python", "data": {}}
    if clean_name[0].isdigit():
        clean_name = f"tool_{clean_name}"

    # Protezione
    if f"{clean_name}.py" in PROTECTED_FILES:
        return {"success": False, "message": f"'{clean_name}' è un file protetto", "data": {}}

    tool_path = CUSTOM_TOOLS_DIR / f"{clean_name}.py"
    if tool_path.exists():
        return {"success": False, "message": f"Tool '{clean_name}' esiste già", "data": {}}

    # Step 1: Genera
    print("[self_evolution] Step 1/3 — Generazione codice...")
    gen = await generate_tool_code(clean_name, description, parameters)
    if not gen["success"]:
        return {"success": False, "message": f"Generazione fallita: {gen['error']}", "data": {}}

    # Salva
    CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    tool_path.write_text(gen["code"], encoding="utf-8")
    print(f"[self_evolution] Salvato: {tool_path}")

    # Step 2: Test
    print("[self_evolution] Step 2/3 — Testing...")
    test = await run_self_test(clean_name)

    if not test["success"]:
        # Pulizia
        if tool_path.exists():
            tool_path.unlink()
        log_event({"event": "create_failed", "name": clean_name, "error": test["error"]})
        return {
            "success": False,
            "message": f"Test fallito dopo {test['attempts']} tentativi: {test['error'][:300]}",
            "data": {"attempts": test["attempts"]},
        }

    # Registra
    register_tool_entry(clean_name, description, parameters, str(tool_path))

    # Step 3: Deploy
    print("[self_evolution] Step 3/3 — Deploy...")
    deploy = await git_deploy(f"[self_evolution] Nuovo tool: {clean_name}")

    log_event({
        "event": "tool_created",
        "name": clean_name,
        "description": description,
        "test_attempts": test["attempts"],
        "deployed": deploy["success"],
        "commit": deploy.get("commit_hash", ""),
    })

    if deploy["success"]:
        print(f"[self_evolution] ✓ COMPLETATO — '{clean_name}' creato e deployato ({deploy['commit_hash']})")
    else:
        print(f"[self_evolution] ⚠ Tool creato e testato ma deploy fallito: {deploy['error']}")

    return {
        "success": True,
        "message": f"Tool '{clean_name}' creato con successo!" + (f" Commit: {deploy['commit_hash']}" if deploy["success"] else " (deploy fallito, tool attivo localmente)"),
        "data": {
            "name": clean_name,
            "file": str(tool_path),
            "test_attempts": test["attempts"],
            "deployed": deploy["success"],
            "commit": deploy.get("commit_hash", ""),
            "code_preview": gen["code"][:500],
        },
    }


# === FASTAPI APP ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown del servizio."""
    print(f"[self_evolution] Servizio avviato sulla porta {SERVICE_PORT}")
    print(f"[self_evolution] Tools dir: {CUSTOM_TOOLS_DIR}")
    CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        save_registry([])
    yield
    print("[self_evolution] Servizio in arresto")


app = FastAPI(
    title="nik29 Self Evolution Service",
    description="Servizio per la creazione autonoma di tool",
    version="2.0.0",
    lifespan=lifespan,
)


# --- Endpoints ---

@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": "self_evolution", "port": SERVICE_PORT}


@app.post("/create_tool")
async def api_create_tool(req: CreateToolRequest):
    """Crea un nuovo tool: genera, testa, deploya."""
    try:
        result = await full_create_tool(req.name, req.description, req.parameters)
        return JSONResponse(
            status_code=200 if result["success"] else 422,
            content=result,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "success": False,
            "message": f"Errore interno: {str(e)}",
            "data": {"traceback": traceback.format_exc()},
        })


@app.get("/list_tools")
async def api_list_tools():
    """Lista tutti i tool custom."""
    try:
        registry = load_registry()
        active = [t for t in registry if t.get("active", True)]
        return {"success": True, "tools": active, "count": len(active)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.delete("/remove_tool/{name}")
async def api_remove_tool(name: str):
    """Rimuove un tool custom."""
    try:
        if f"{name}.py" in PROTECTED_FILES:
            raise HTTPException(status_code=403, detail=f"'{name}' è protetto")

        tool_path = CUSTOM_TOOLS_DIR / f"{name}.py"
        if not tool_path.exists():
            raise HTTPException(status_code=404, detail=f"Tool '{name}' non trovato")

        tool_path.unlink()
        unregister_tool_entry(name)
        log_event({"event": "tool_removed", "name": name})

        return {"success": True, "message": f"Tool '{name}' rimosso"}

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/self_test/{name}")
async def api_self_test(name: str):
    """Testa un tool esistente."""
    try:
        result = await run_self_test(name)
        return JSONResponse(
            status_code=200 if result["success"] else 422,
            content=result,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/deploy")
async def api_deploy():
    """Esegue git push delle modifiche."""
    try:
        result = await git_deploy()
        return JSONResponse(
            status_code=200 if result["success"] else 422,
            content=result,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/logs")
async def api_logs():
    """Ritorna gli ultimi eventi di evoluzione."""
    try:
        if EVOLUTION_LOG.exists():
            with open(EVOLUTION_LOG, "r", encoding="utf-8") as f:
                log = json.load(f)
            return {"success": True, "events": log[-20:]}
        return {"success": True, "events": []}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/tool_code/{name}")
async def api_tool_code(name: str):
    """Ritorna il codice sorgente di un tool custom."""
    tool_path = CUSTOM_TOOLS_DIR / f"{name}.py"
    if not tool_path.exists():
        raise HTTPException(status_code=404, detail=f"Tool '{name}' non trovato")
    code = tool_path.read_text(encoding="utf-8")
    return {"success": True, "name": name, "code": code}


# === MAIN ===

if __name__ == "__main__":
    print(f"[self_evolution] Avvio servizio su 0.0.0.0:{SERVICE_PORT}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SERVICE_PORT,
        log_level="info",
        access_log=False,
    )
