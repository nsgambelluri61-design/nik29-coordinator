"""
Modulo: self_evolution.py
Descrizione: Permette a nik29-coordinator di creare tool autonomamente,
             testarli e deployarli su GitHub.
Autore: Generato per nik29-coordinator
Versione: 1.0.0
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

from openai import AsyncOpenAI

# === CONFIGURAZIONE ===

TOOLS_DIR = Path("/app/app/tools")
COORDINATOR_PATH = Path("/app/app/coordinator.py")
REGISTRY_PATH = TOOLS_DIR / "custom_tools_registry.json"
MEMORY_DIR = Path("/data/memory")
EVOLUTION_LOG = MEMORY_DIR / "self_evolution_log.json"

MAX_FIX_ATTEMPTS = 3

PROTECTED_FILES = [
    "main.py",
    "coordinator.py",
    "persistent_memory.py",
    "semantic_memory.py",
]

# Template per i tool generati
TOOL_TEMPLATE = '''"""
Tool: {name}
Descrizione: {description}
Generato automaticamente da self_evolution
Data: {date}
"""

{imports}

async def {name}({parameters}) -> dict:
    """
    {description}
    """
    {implementation}
'''

# === CLIENT OPENAI ===

def get_openai_client() -> AsyncOpenAI:
    """Inizializza il client OpenAI con le variabili d'ambiente."""
    return AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_API_BASE"),
    )


# === REGISTRY MANAGEMENT ===

def load_registry() -> list:
    """Carica il registry dei tool custom."""
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_registry(registry: list):
    """Salva il registry dei tool custom."""
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def register_tool(name: str, description: str, parameters: str, file_path: str):
    """Registra un nuovo tool nel registry."""
    registry = load_registry()

    # Evita duplicati
    registry = [t for t in registry if t["name"] != name]

    registry.append({
        "name": name,
        "description": description,
        "parameters": parameters,
        "file_path": file_path,
        "created_at": datetime.now().isoformat(),
        "active": True,
    })

    save_registry(registry)
    print(f"[self_evolution] Tool '{name}' registrato nel registry.")


# === EVOLUTION LOG ===

def log_evolution(event: dict):
    """Logga un evento di evoluzione nella memoria."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    log = []
    if EVOLUTION_LOG.exists():
        try:
            with open(EVOLUTION_LOG, "r") as f:
                log = json.load(f)
        except (json.JSONDecodeError, IOError):
            log = []

    event["timestamp"] = datetime.now().isoformat()
    log.append(event)

    # Mantieni solo gli ultimi 100 eventi
    log = log[-100:]

    with open(EVOLUTION_LOG, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


# === INSTALLAZIONE DIPENDENZE ===

def install_dependencies(code: str) -> list:
    """
    Analizza il codice per trovare import non standard e li installa.
    Ritorna la lista delle librerie installate.
    """
    import ast

    installed = []
    stdlib_modules = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()

    # Aggiungi moduli comuni che sono sicuramente disponibili
    always_available = {"os", "sys", "json", "asyncio", "pathlib", "datetime",
                        "typing", "re", "math", "random", "hashlib", "base64",
                        "urllib", "collections", "itertools", "functools",
                        "subprocess", "shutil", "tempfile", "io", "time",
                        "traceback", "importlib", "inspect", "copy", "uuid"}
    stdlib_modules.update(always_available)

    # Librerie già installate nel container
    known_installed = {"openai", "requests", "aiohttp", "httpx", "fastapi",
                       "uvicorn", "pydantic", "beautifulsoup4", "bs4",
                       "pillow", "PIL", "numpy", "pandas"}

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return installed

    imports_to_check = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                imports_to_check.add(module_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split(".")[0]
                imports_to_check.add(module_name)

    for module_name in imports_to_check:
        if module_name in stdlib_modules or module_name in known_installed:
            continue

        # Prova a importare
        try:
            importlib.import_module(module_name)
        except ImportError:
            # Installa con pip
            print(f"[self_evolution] Installazione dipendenza: {module_name}")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", module_name],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    installed.append(module_name)
                    print(f"[self_evolution] ✓ Installato: {module_name}")
                else:
                    print(f"[self_evolution] ✗ Errore installazione {module_name}: {result.stderr}")
            except subprocess.TimeoutExpired:
                print(f"[self_evolution] ✗ Timeout installazione {module_name}")

    return installed


# === GENERAZIONE TOOL ===

async def generate_tool(name: str, description: str, parameters: str = "") -> dict:
    """
    Genera il codice Python di un nuovo tool usando GPT-4.1.

    Args:
        name: Nome del tool (snake_case)
        description: Descrizione di cosa deve fare il tool
        parameters: Parametri del tool (es. "url: str, timeout: int = 30")

    Returns:
        dict con "success", "code", "file_path", "error"
    """
    print(f"[self_evolution] Generazione tool: {name}")

    # Validazione nome
    if not name.isidentifier():
        return {"success": False, "code": "", "file_path": "", "error": f"Nome '{name}' non è un identificatore Python valido"}

    # Verifica che non sia un file protetto
    if f"{name}.py" in PROTECTED_FILES or name in [p.replace(".py", "") for p in PROTECTED_FILES]:
        return {"success": False, "code": "", "file_path": "", "error": f"Il tool '{name}' è nella lista dei file protetti"}

    # Verifica che non esista già
    tool_path = TOOLS_DIR / f"{name}.py"
    if tool_path.exists():
        return {"success": False, "code": "", "file_path": str(tool_path), "error": f"Il tool '{name}' esiste già. Non è possibile sovrascrivere tool esistenti."}

    client = get_openai_client()

    # Carica esempi di tool esistenti per contesto
    existing_tools_info = ""
    try:
        tool_files = list(TOOLS_DIR.glob("*.py"))[:3]
        for tf in tool_files:
            if tf.name not in PROTECTED_FILES:
                content = tf.read_text()[:500]
                existing_tools_info += f"\n--- Esempio ({tf.name}) ---\n{content}\n"
    except Exception:
        pass

    prompt = f"""Genera il codice Python completo per un tool chiamato '{name}'.

DESCRIZIONE: {description}

PARAMETRI RICHIESTI: {parameters if parameters else "Deduci i parametri appropriati dalla descrizione"}

REGOLE:
1. Il tool DEVE essere una funzione async
2. DEVE avere type hints per tutti i parametri
3. DEVE avere una docstring chiara
4. DEVE ritornare un dict con almeno la chiave "result"
5. DEVE gestire le eccezioni con try/except
6. NON usare librerie esotiche se non necessario
7. Usa requests/httpx per HTTP, beautifulsoup4 per parsing HTML
8. Il codice deve essere production-ready e robusto
9. Includi import necessari all'inizio del file
10. Aggiungi commenti esplicativi dove utile

STRUTTURA OBBLIGATORIA:
```python
\"\"\"
Tool: {name}
Descrizione: {description}
Generato automaticamente da self_evolution
\"\"\"

import ...  # import necessari

async def {name}(...) -> dict:
    \"\"\"
    {description}
    \"\"\"
    try:
        # implementazione
        return {{"result": ..., "success": True}}
    except Exception as e:
        return {{"result": None, "success": False, "error": str(e)}}
```

{f"CONTESTO - Tool esistenti nel progetto:{existing_tools_info}" if existing_tools_info else ""}

Genera SOLO il codice Python, senza markdown o spiegazioni aggiuntive."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Sei un esperto sviluppatore Python. Generi codice pulito, robusto e ben documentato. Rispondi SOLO con codice Python puro, senza blocchi markdown."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000,
        )

        code = response.choices[0].message.content.strip()

        # Rimuovi eventuali blocchi markdown
        if code.startswith("```python"):
            code = code[len("```python"):].strip()
        if code.startswith("```"):
            code = code[3:].strip()
        if code.endswith("```"):
            code = code[:-3].strip()

        # Verifica sintassi base
        try:
            compile(code, f"{name}.py", "exec")
        except SyntaxError as e:
            return {"success": False, "code": code, "file_path": "", "error": f"Errore di sintassi nel codice generato: {e}"}

        # Installa dipendenze se necessario
        installed_deps = install_dependencies(code)

        # Salva il file
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        tool_path.write_text(code, encoding="utf-8")
        print(f"[self_evolution] ✓ Tool salvato: {tool_path}")

        # Registra nel registry
        register_tool(name, description, parameters, str(tool_path))

        # Log
        log_evolution({
            "event": "tool_generated",
            "name": name,
            "description": description,
            "parameters": parameters,
            "file_path": str(tool_path),
            "installed_deps": installed_deps,
        })

        return {
            "success": True,
            "code": code,
            "file_path": str(tool_path),
            "error": "",
            "installed_deps": installed_deps,
        }

    except Exception as e:
        error_msg = f"Errore nella generazione: {traceback.format_exc()}"
        print(f"[self_evolution] ✗ {error_msg}")
        return {"success": False, "code": "", "file_path": "", "error": error_msg}


# === TEST DEL TOOL ===

async def self_test(tool_name: str) -> dict:
    """
    Testa un tool appena generato.

    1. Verifica sintassi con compile()
    2. Importa il modulo
    3. Genera parametri di test con GPT-4.1
    4. Esegue il tool
    5. Se fallisce, tenta fix automatico (max 3 tentativi)

    Returns:
        dict con "success", "error", "attempts", "test_output"
    """
    print(f"[self_evolution] Test del tool: {tool_name}")

    tool_path = TOOLS_DIR / f"{tool_name}.py"
    if not tool_path.exists():
        return {"success": False, "error": f"File {tool_path} non trovato", "attempts": 0, "test_output": None}

    attempts = 0
    last_error = ""

    while attempts < MAX_FIX_ATTEMPTS:
        attempts += 1
        print(f"[self_evolution] Tentativo {attempts}/{MAX_FIX_ATTEMPTS}")

        # 1. Verifica sintassi
        code = tool_path.read_text(encoding="utf-8")
        try:
            compile(code, str(tool_path), "exec")
        except SyntaxError as e:
            last_error = f"Errore di sintassi: {e}"
            print(f"[self_evolution] ✗ {last_error}")
            fix_result = await _attempt_fix(tool_name, code, last_error)
            if not fix_result:
                continue
            code = fix_result
            continue

        # 2. Installa dipendenze
        install_dependencies(code)

        # 3. Importa il modulo
        try:
            spec = importlib.util.spec_from_file_location(tool_name, str(tool_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            last_error = f"Errore di import: {traceback.format_exc()}"
            print(f"[self_evolution] ✗ {last_error}")
            fix_result = await _attempt_fix(tool_name, code, last_error)
            if not fix_result:
                continue
            continue

        # 4. Verifica che la funzione esista
        if not hasattr(module, tool_name):
            last_error = f"Funzione '{tool_name}' non trovata nel modulo"
            print(f"[self_evolution] ✗ {last_error}")
            fix_result = await _attempt_fix(tool_name, code, last_error)
            if not fix_result:
                continue
            continue

        func = getattr(module, tool_name)

        # 5. Genera parametri di test
        test_params = await _generate_test_params(tool_name, code)

        # 6. Esegui il tool
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**test_params), timeout=30)
            else:
                result = func(**test_params)

            print(f"[self_evolution] ✓ Test superato! Output: {str(result)[:200]}")

            log_evolution({
                "event": "tool_tested",
                "name": tool_name,
                "success": True,
                "attempts": attempts,
                "test_params": str(test_params)[:200],
                "test_output": str(result)[:200],
            })

            return {
                "success": True,
                "error": "",
                "attempts": attempts,
                "test_output": result,
            }

        except asyncio.TimeoutError:
            last_error = "Timeout: il tool ha impiegato più di 30 secondi"
            print(f"[self_evolution] ✗ {last_error}")
        except Exception as e:
            last_error = f"Errore di esecuzione: {traceback.format_exc()}"
            print(f"[self_evolution] ✗ {last_error}")

        # Tenta fix
        if attempts < MAX_FIX_ATTEMPTS:
            fix_result = await _attempt_fix(tool_name, code, last_error)

    # Tutti i tentativi falliti
    log_evolution({
        "event": "tool_tested",
        "name": tool_name,
        "success": False,
        "attempts": attempts,
        "last_error": last_error[:500],
    })

    return {
        "success": False,
        "error": last_error,
        "attempts": attempts,
        "test_output": None,
    }


async def _generate_test_params(tool_name: str, code: str) -> dict:
    """Genera parametri di test appropriati usando GPT-4.1."""
    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Genera parametri di test per una funzione Python. Rispondi SOLO con un JSON valido (dict) con i parametri. Usa valori realistici ma sicuri (no URL reali pericolosi, no file system critici). Per stringhe usa esempi innocui, per numeri usa valori piccoli."},
                {"role": "user", "content": f"Genera parametri di test per questa funzione:\n\n{code}\n\nRispondi SOLO con il JSON dei parametri (es: {{\"param1\": \"valore\", \"param2\": 42}})"}
            ],
            temperature=0.2,
            max_tokens=500,
        )

        params_str = response.choices[0].message.content.strip()

        # Pulizia
        if params_str.startswith("```json"):
            params_str = params_str[7:]
        if params_str.startswith("```"):
            params_str = params_str[3:]
        if params_str.endswith("```"):
            params_str = params_str[:-3]
        params_str = params_str.strip()

        params = json.loads(params_str)
        print(f"[self_evolution] Parametri di test generati: {params}")
        return params

    except Exception as e:
        print(f"[self_evolution] Errore generazione parametri test: {e}")
        return {}


async def _attempt_fix(tool_name: str, current_code: str, error: str) -> Optional[str]:
    """Tenta di fixare il codice del tool usando GPT-4.1."""
    print(f"[self_evolution] Tentativo di fix automatico per '{tool_name}'...")

    client = get_openai_client()

    try:
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": "Sei un debugger Python esperto. Correggi il codice fornito basandoti sull'errore. Rispondi SOLO con il codice Python corretto completo, senza markdown o spiegazioni."},
                {"role": "user", "content": f"Questo codice ha un errore:\n\n```python\n{current_code}\n```\n\nERRORE:\n{error}\n\nCorreggi il codice e rispondi SOLO con il codice Python completo corretto."}
            ],
            temperature=0.2,
            max_tokens=4000,
        )

        fixed_code = response.choices[0].message.content.strip()

        # Pulizia markdown
        if fixed_code.startswith("```python"):
            fixed_code = fixed_code[len("```python"):].strip()
        if fixed_code.startswith("```"):
            fixed_code = fixed_code[3:].strip()
        if fixed_code.endswith("```"):
            fixed_code = fixed_code[:-3].strip()

        # Verifica sintassi del fix
        try:
            compile(fixed_code, f"{tool_name}.py", "exec")
        except SyntaxError:
            print("[self_evolution] ✗ Il fix ha ancora errori di sintassi")
            return None

        # Salva il fix
        tool_path = TOOLS_DIR / f"{tool_name}.py"
        tool_path.write_text(fixed_code, encoding="utf-8")
        print(f"[self_evolution] ✓ Fix applicato a {tool_path}")

        return fixed_code

    except Exception as e:
        print(f"[self_evolution] ✗ Errore nel fix: {e}")
        return None


# === DEPLOY ===

async def safe_deploy() -> dict:
    """
    Esegue git add, commit e push per deployare le modifiche.

    Returns:
        dict con "success", "commit_hash", "error"
    """
    print("[self_evolution] Deploy in corso...")

    try:
        # Git add
        result = subprocess.run(
            ["git", "add", "-A"],
            cwd="/app",
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return {"success": False, "commit_hash": "", "error": f"git add fallito: {result.stderr}"}

        # Git commit
        commit_msg = f"[self_evolution] Nuovo tool aggiunto - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd="/app",
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # Se non c'è nulla da committare, non è un errore
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return {"success": True, "commit_hash": "no_changes", "error": ""}
            return {"success": False, "commit_hash": "", "error": f"git commit fallito: {result.stderr}"}

        # Estrai commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd="/app",
            capture_output=True, text=True, timeout=10
        )
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else "unknown"

        # Git push (con retry)
        for push_attempt in range(2):
            result = subprocess.run(
                ["git", "push"],
                cwd="/app",
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                print(f"[self_evolution] ✓ Push riuscito! Commit: {commit_hash[:8]}")

                log_evolution({
                    "event": "deploy",
                    "success": True,
                    "commit_hash": commit_hash,
                })

                return {"success": True, "commit_hash": commit_hash, "error": ""}

            print(f"[self_evolution] Push tentativo {push_attempt + 1} fallito: {result.stderr}")

            if push_attempt == 0:
                # Prima di riprovare, fai pull --rebase
                subprocess.run(
                    ["git", "pull", "--rebase"],
                    cwd="/app",
                    capture_output=True, text=True, timeout=30
                )

        return {"success": False, "commit_hash": commit_hash, "error": f"git push fallito dopo 2 tentativi: {result.stderr}"}

    except subprocess.TimeoutExpired:
        return {"success": False, "commit_hash": "", "error": "Timeout durante le operazioni git"}
    except Exception as e:
        return {"success": False, "commit_hash": "", "error": f"Errore imprevisto: {traceback.format_exc()}"}


# === WRAPPER PRINCIPALE ===

async def create_and_deploy_tool(name: str, description: str, parameters: str = "") -> dict:
    """
    Workflow completo: genera → testa → deploya un nuovo tool.

    Args:
        name: Nome del tool (snake_case)
        description: Descrizione completa di cosa deve fare
        parameters: Parametri opzionali (es. "url: str, timeout: int = 30")

    Returns:
        dict con tutti i dettagli dell'operazione
    """
    print(f"\n{'='*60}")
    print(f"[self_evolution] CREAZIONE TOOL: {name}")
    print(f"{'='*60}\n")

    result = {
        "name": name,
        "description": description,
        "steps": {},
        "success": False,
    }

    # Step 1: Genera il tool
    print("[self_evolution] Step 1/3: Generazione codice...")
    gen_result = await generate_tool(name, description, parameters)
    result["steps"]["generate"] = gen_result

    if not gen_result["success"]:
        result["error"] = f"Generazione fallita: {gen_result['error']}"
        print(f"[self_evolution] ✗ {result['error']}")
        return result

    # Step 2: Testa il tool
    print("\n[self_evolution] Step 2/3: Testing...")
    test_result = await self_test(name)
    result["steps"]["test"] = test_result

    if not test_result["success"]:
        # Cancella il tool fallito
        tool_path = TOOLS_DIR / f"{name}.py"
        if tool_path.exists():
            tool_path.unlink()
            print(f"[self_evolution] Tool fallito rimosso: {tool_path}")

        # Rimuovi dal registry
        registry = load_registry()
        registry = [t for t in registry if t["name"] != name]
        save_registry(registry)

        result["error"] = f"Test fallito dopo {test_result['attempts']} tentativi: {test_result['error']}"
        print(f"[self_evolution] ✗ {result['error']}")

        log_evolution({
            "event": "tool_creation_failed",
            "name": name,
            "reason": result["error"],
        })

        return result

    # Step 3: Deploy
    print("\n[self_evolution] Step 3/3: Deploy su GitHub...")
    deploy_result = await safe_deploy()
    result["steps"]["deploy"] = deploy_result

    if not deploy_result["success"]:
        result["error"] = f"Deploy fallito: {deploy_result['error']}"
        result["success"] = False  # Il tool è creato ma non deployato
        result["partial_success"] = True
        print(f"[self_evolution] ⚠ Tool creato e testato ma deploy fallito: {deploy_result['error']}")
    else:
        result["success"] = True
        result["commit_hash"] = deploy_result["commit_hash"]
        print(f"\n[self_evolution] ✓ TOOL '{name}' CREATO CON SUCCESSO!")
        print(f"[self_evolution]   File: {gen_result['file_path']}")
        print(f"[self_evolution]   Commit: {deploy_result['commit_hash'][:8]}")

    log_evolution({
        "event": "tool_creation_complete",
        "name": name,
        "success": result["success"],
        "commit_hash": deploy_result.get("commit_hash", ""),
    })

    return result


# === TOOL ESPOSTO AL COORDINATOR (invocabile dalla chat) ===

async def create_tool(name: str, description: str) -> dict:
    """
    Crea un nuovo tool per nik29-coordinator.
    Genera il codice, lo testa e lo deploya automaticamente su GitHub.

    Args:
        name: Nome del tool in snake_case (es. "scrape_website")
        description: Descrizione dettagliata di cosa deve fare il tool

    Returns:
        dict con il risultato dell'operazione
    """
    # Sanitizza il nome
    name = name.strip().lower().replace(" ", "_").replace("-", "_")

    # Rimuovi caratteri non validi
    name = "".join(c for c in name if c.isalnum() or c == "_")

    if not name:
        return {"success": False, "error": "Nome tool non valido"}

    if name.startswith("_") or name[0].isdigit():
        name = f"tool_{name}"

    result = await create_and_deploy_tool(name, description)

    # Formatta risposta user-friendly
    if result["success"]:
        return {
            "result": f"✓ Tool '{name}' creato con successo e deployato su GitHub!",
            "success": True,
            "details": {
                "name": name,
                "file": result["steps"]["generate"]["file_path"],
                "commit": result.get("commit_hash", "")[:8],
                "test_attempts": result["steps"]["test"]["attempts"],
            }
        }
    elif result.get("partial_success"):
        return {
            "result": f"⚠ Tool '{name}' creato e testato, ma il deploy su GitHub è fallito. Il tool è comunque attivo localmente.",
            "success": True,
            "deploy_failed": True,
            "details": {
                "name": name,
                "file": result["steps"]["generate"]["file_path"],
                "error": result.get("error", ""),
            }
        }
    else:
        return {
            "result": f"✗ Creazione del tool '{name}' fallita: {result.get('error', 'errore sconosciuto')}",
            "success": False,
            "error": result.get("error", ""),
        }


# === UTILITY: Lista tool custom ===

async def list_custom_tools() -> dict:
    """Elenca tutti i tool custom creati da self_evolution."""
    registry = load_registry()
    active_tools = [t for t in registry if t.get("active", True)]

    return {
        "result": active_tools,
        "success": True,
        "count": len(active_tools),
    }


# === UTILITY: Rimuovi tool custom ===

async def remove_custom_tool(name: str) -> dict:
    """Rimuove un tool custom (lo disattiva e cancella il file)."""
    tool_path = TOOLS_DIR / f"{name}.py"

    if not tool_path.exists():
        return {"success": False, "error": f"Tool '{name}' non trovato"}

    # Verifica che non sia protetto
    if f"{name}.py" in PROTECTED_FILES:
        return {"success": False, "error": f"Tool '{name}' è protetto e non può essere rimosso"}

    # Rimuovi file
    tool_path.unlink()

    # Aggiorna registry
    registry = load_registry()
    registry = [t for t in registry if t["name"] != name]
    save_registry(registry)

    log_evolution({
        "event": "tool_removed",
        "name": name,
    })

    return {"success": True, "result": f"Tool '{name}' rimosso con successo"}


# === LOADER PER IL COORDINATOR ===

def get_custom_tools_definitions() -> list:
    """
    Ritorna le definizioni dei tool custom per il coordinator.
    Questo viene chiamato all'avvio per registrare i tool.
    """
    registry = load_registry()
    definitions = []

    for tool in registry:
        if not tool.get("active", True):
            continue

        definitions.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": {},  # Sarà popolato dal codice del tool
                }
            }
        })

    # Aggiungi sempre il tool create_tool
    definitions.append({
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": "Crea un nuovo tool per nik29. Genera il codice automaticamente, lo testa e lo deploya su GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome del tool in snake_case (es. 'scrape_website', 'generate_report')"
                    },
                    "description": {
                        "type": "string",
                        "description": "Descrizione dettagliata di cosa deve fare il tool"
                    }
                },
                "required": ["name", "description"]
            }
        }
    })

    # Tool per listare i tool custom
    definitions.append({
        "type": "function",
        "function": {
            "name": "list_custom_tools",
            "description": "Elenca tutti i tool custom creati da self_evolution",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    })

    # Tool per rimuovere tool custom
    definitions.append({
        "type": "function",
        "function": {
            "name": "remove_custom_tool",
            "description": "Rimuove un tool custom creato da self_evolution",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nome del tool da rimuovere"
                    }
                },
                "required": ["name"]
            }
        }
    })

    return definitions


async def execute_custom_tool(tool_name: str, params: dict) -> dict:
    """
    Esegue un tool custom dato il nome e i parametri.
    Usato dal coordinator per chiamare i tool registrati.
    """
    # Tool built-in di self_evolution
    builtin_tools = {
        "create_tool": create_tool,
        "list_custom_tools": list_custom_tools,
        "remove_custom_tool": remove_custom_tool,
    }

    if tool_name in builtin_tools:
        return await builtin_tools[tool_name](**params)

    # Tool custom dal registry
    tool_path = TOOLS_DIR / f"{tool_name}.py"
    if not tool_path.exists():
        return {"success": False, "error": f"Tool '{tool_name}' non trovato"}

    try:
        spec = importlib.util.spec_from_file_location(tool_name, str(tool_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, tool_name):
            return {"success": False, "error": f"Funzione '{tool_name}' non trovata nel modulo"}

        func = getattr(module, tool_name)

        if asyncio.iscoroutinefunction(func):
            result = await asyncio.wait_for(func(**params), timeout=60)
        else:
            result = func(**params)

        return result

    except asyncio.TimeoutError:
        return {"success": False, "error": f"Timeout: il tool '{tool_name}' ha impiegato più di 60 secondi"}
    except Exception as e:
        return {"success": False, "error": f"Errore esecuzione '{tool_name}': {traceback.format_exc()}"}


# === MAIN (per test standalone) ===

if __name__ == "__main__":
    async def _test():
        print("=== Test self_evolution ===")
        result = await create_tool(
            name="hello_world",
            description="Un tool di test che ritorna un saluto personalizzato dato un nome"
        )
        print(f"\nRisultato: {json.dumps(result, indent=2, ensure_ascii=False)}")

    asyncio.run(_test())
