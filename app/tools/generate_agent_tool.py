"""
╔══════════════════════════════════════════════════════════════════╗
║  NIK29 GENERATE AGENT TOOL - Level 4 Self-Evolution             ║
║  Crea, lista e rimuove agenti Docker esterni autonomamente      ║
╚══════════════════════════════════════════════════════════════════╝

Questo modulo permette al coordinator di creare NUOVI container Docker
con agenti specializzati, buildarli, avviarli e registrarli nel sistema.

TOOL DISPONIBILI:
  1. generate_agent       - Genera codice, builda e avvia un nuovo agente Docker
  2. list_docker_agents   - Lista agenti Docker registrati con stato running/stopped
  3. remove_docker_agent  - Ferma, rimuove container e deregistra un agente

ARCHITETTURA:
  - Il coordinator comunica col Mac host via Host Bridge (HTTP)
  - I file dell'agente vengono scritti su {PROJECT_DIR}/agents/{name}/
  - L'immagine Docker viene buildata e il container avviato sulla stessa rete
  - L'agente viene registrato in /data/memory/agents.json

AUTORE: nik29-coordinator Level 4 Self-Evolution
VERSIONE: 1.0.0
"""

import ast
import asyncio
import json
import logging
import os
import re
import time
from typing import Optional

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger("generate_agent")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════════════

BRIDGE_URL = os.environ.get("HOST_BRIDGE_URL", "http://host.docker.internal:4003")
PROJECT_DIR = os.environ.get(
    "HOST_PROJECT_DIR",
    "/Users/nicolasgambelluri/Downloads/nik29-coordinator-v0.6.0"
)
AGENTS_CONFIG = os.environ.get("AGENTS_CONFIG", "/data/memory/agents.json")
HTTP_TIMEOUT = 90.0

# Vincoli di sicurezza
MAX_EXTERNAL_AGENTS = 5
PROTECTED_NAMES = {"coordinator", "images", "bridge", "immagini"}
RESERVED_PORTS = {4000, 4001, 4002, 4003, 4004, 4005}
PORT_RANGE_START = 4006
PORT_RANGE_END = 4020
DOCKER_NETWORK = "nik29-network"

# Modello per generazione codice
CODE_GEN_MODEL = "gpt-4.1"


# ═══════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS (OpenAI function calling format)
# ═══════════════════════════════════════════════════════════════════

GENERATE_AGENT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "generate_agent",
        "description": (
            "Crea un nuovo agente Docker specializzato. Genera il codice, "
            "builda l'immagine, avvia il container e lo registra. "
            "L'agente sarà raggiungibile via HTTP e potrà ricevere task dal coordinator."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome dell'agente (snake_case, es. 'video_editor')"
                },
                "description": {
                    "type": "string",
                    "description": "Descrizione di cosa fa l'agente"
                },
                "capabilities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista delle capacità (es. ['transcode', 'trim', 'merge'])"
                },
                "tech_stack": {
                    "type": "string",
                    "description": (
                        "Tecnologie/librerie necessarie (es. 'ffmpeg, moviepy'). Opzionale."
                    )
                }
            },
            "required": ["name", "description", "capabilities"]
        }
    }
}

LIST_DOCKER_AGENTS_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "list_docker_agents",
        "description": (
            "Lista tutti gli agenti Docker esterni registrati con il loro stato "
            "(running/stopped), URL, porta e capacità."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

REMOVE_DOCKER_AGENT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "remove_docker_agent",
        "description": (
            "Ferma e rimuove un agente Docker esterno. Stoppa il container, "
            "rimuove l'immagine e deregistra l'agente dal sistema. "
            "NON può rimuovere agenti protetti (immagini, coordinator, bridge)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nome dell'agente da rimuovere"
                },
                "remove_files": {
                    "type": "boolean",
                    "description": "Se true, rimuove anche i file sorgente dell'agente dal disco (default: false)"
                }
            },
            "required": ["name"]
        }
    }
}

ALL_DOCKER_AGENT_TOOL_DEFINITIONS = [
    GENERATE_AGENT_TOOL_DEFINITION,
    LIST_DOCKER_AGENTS_TOOL_DEFINITION,
    REMOVE_DOCKER_AGENT_TOOL_DEFINITION,
]


# ═══════════════════════════════════════════════════════════════════
# BRIDGE CLIENT (comunicazione con Mac host)
# ═══════════════════════════════════════════════════════════════════

async def _call_bridge(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None
) -> dict:
    """
    Chiama il Host Bridge per eseguire un comando sul Mac.

    Returns:
        dict con stdout, stderr, exit_code
    """
    payload = {"command": command, "timeout": timeout}
    if cwd:
        payload["cwd"] = cwd

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(f"{BRIDGE_URL}/exec", json=payload)
            result = response.json()
            if result.get("exit_code", 0) != 0:
                logger.warning(
                    f"Bridge cmd '{command[:80]}' exit={result.get('exit_code')} "
                    f"stderr={result.get('stderr', '')[:200]}"
                )
            return result
    except httpx.ConnectError:
        msg = "Host Bridge non raggiungibile. Verifica che sia attivo."
        logger.error(msg)
        return {"stdout": "", "stderr": msg, "exit_code": -99}
    except httpx.TimeoutException:
        msg = f"Timeout bridge (>{HTTP_TIMEOUT}s)"
        logger.error(msg)
        return {"stdout": "", "stderr": msg, "exit_code": -98}
    except Exception as e:
        msg = f"Errore bridge: {e}"
        logger.error(msg)
        return {"stdout": "", "stderr": msg, "exit_code": -97}


# ═══════════════════════════════════════════════════════════════════
# REGISTRY HELPERS (agents.json)
# ═══════════════════════════════════════════════════════════════════

def _load_agents_registry() -> list:
    """Carica il registro agenti da disco."""
    if os.path.exists(AGENTS_CONFIG):
        try:
            with open(AGENTS_CONFIG, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("agents", [])
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return []


def _save_agents_registry(agents: list) -> None:
    """Salva il registro agenti su disco."""
    os.makedirs(os.path.dirname(AGENTS_CONFIG), exist_ok=True)
    with open(AGENTS_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"agents": agents}, f, ensure_ascii=False, indent=2)


def _agent_exists(name: str) -> bool:
    """Verifica se un agente con questo nome è già registrato."""
    agents = _load_agents_registry()
    return any(a["name"] == name for a in agents)


def _count_docker_agents() -> int:
    """Conta gli agenti Docker (esclude il default 'immagini' se non ha porta)."""
    agents = _load_agents_registry()
    return len([a for a in agents if a.get("port")])


# ═══════════════════════════════════════════════════════════════════
# PORT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def _get_used_ports() -> set:
    """Recupera le porte già in uso dagli agenti registrati."""
    agents = _load_agents_registry()
    used = set(RESERVED_PORTS)
    for agent in agents:
        if agent.get("port"):
            used.add(agent["port"])
    return used


def _next_available_port() -> Optional[int]:
    """Trova la prossima porta disponibile per un nuovo agente."""
    used = _get_used_ports()
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if port not in used:
            return port
    return None


# ═══════════════════════════════════════════════════════════════════
# CODE GENERATION (GPT-4.1)
# ═══════════════════════════════════════════════════════════════════

def _build_code_gen_prompt(
    name: str,
    description: str,
    capabilities: list,
    tech_stack: str,
    port: int
) -> str:
    """Costruisce il prompt per GPT-4.1 per generare il codice dell'agente."""
    caps_str = ", ".join(capabilities)
    return f"""Genera il codice per un microservizio Docker Python (FastAPI) chiamato "nik29-{name}".

SPECIFICHE:
- Nome: nik29-{name}
- Descrizione: {description}
- Capacità: {caps_str}
- Tech stack aggiuntivo: {tech_stack or "nessuno"}
- Porta interna: {port}

CONTRATTO API OBBLIGATORIO:
1. GET /health → {{"status": "ok", "agent": "{name}"}}
2. POST /task → accetta {{"instruction": "...", "files": [...]}} → restituisce {{"result": "...", "output_files": [...]}}

REGOLE:
- Il main.py DEVE essere un'app FastAPI completa e funzionante
- Usa uvicorn come server (porta {port}, host 0.0.0.0)
- Il Dockerfile DEVE usare python:3.11-slim come base
- Il requirements.txt DEVE includere tutte le dipendenze
- L'endpoint /task deve analizzare l'instruction e smistare alle capacità corrette
- Ogni capacità deve avere una funzione dedicata
- Se una capacità richiede librerie di sistema (es. ffmpeg), installale nel Dockerfile con apt-get
- Gestisci errori con try/except e restituisci messaggi chiari
- NON usare database, NON usare autenticazione
- Il codice deve essere SEMPLICE e focalizzato — niente framework complessi
- Usa httpx per eventuali chiamate HTTP esterne
- Aggiungi logging basico con il modulo logging di Python

FORMATO RISPOSTA (JSON puro, nessun markdown):
{{
  "dockerfile": "contenuto completo del Dockerfile",
  "main_py": "contenuto completo di main.py",
  "requirements_txt": "contenuto completo di requirements.txt"
}}

Rispondi SOLO con il JSON, senza spiegazioni o markdown fence."""


async def _generate_agent_code(
    name: str,
    description: str,
    capabilities: list,
    tech_stack: str,
    port: int
) -> dict:
    """
    Usa GPT-4.1 per generare il codice dell'agente.

    Returns:
        dict con chiavi: dockerfile, main_py, requirements_txt
    Raises:
        RuntimeError se la generazione fallisce
    """
    client = AsyncOpenAI()

    prompt = _build_code_gen_prompt(name, description, capabilities, tech_stack, port)

    try:
        response = await client.chat.completions.create(
            model=CODE_GEN_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei un esperto sviluppatore Python/Docker. "
                        "Generi codice pulito, funzionante e minimale. "
                        "Rispondi SOLO in JSON valido senza markdown fence."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content.strip()
        code_data = json.loads(content)

        # Validazione chiavi obbligatorie
        required_keys = {"dockerfile", "main_py", "requirements_txt"}
        missing = required_keys - set(code_data.keys())
        if missing:
            raise RuntimeError(f"Codice generato incompleto, mancano: {missing}")

        return code_data

    except json.JSONDecodeError as e:
        raise RuntimeError(f"GPT ha restituito JSON non valido: {e}")
    except Exception as e:
        raise RuntimeError(f"Errore nella generazione codice: {e}")


# ═══════════════════════════════════════════════════════════════════
# CODE VALIDATION
# ═══════════════════════════════════════════════════════════════════

def _validate_python_syntax(code: str, filename: str = "main.py") -> Optional[str]:
    """
    Valida la sintassi Python del codice generato.

    Returns:
        None se valido, stringa di errore se non valido
    """
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"Errore di sintassi in {filename} alla riga {e.lineno}: {e.msg}"


def _validate_dockerfile(content: str) -> Optional[str]:
    """
    Validazione basica del Dockerfile.

    Returns:
        None se valido, stringa di errore se non valido
    """
    if "FROM" not in content:
        return "Dockerfile mancante di istruzione FROM"
    if "python" not in content.lower():
        return "Dockerfile non usa un'immagine Python"
    return None


# ═══════════════════════════════════════════════════════════════════
# DOCKER NETWORK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

async def _ensure_docker_network() -> str:
    """
    Verifica che la rete Docker esista, altrimenti la crea.

    Returns:
        Nome della rete Docker da usare
    """
    # Controlla se la rete esiste già
    result = await _call_bridge(
        f"docker network ls --filter name={DOCKER_NETWORK} --format '{{{{.Name}}}}'",
        timeout=10
    )

    if DOCKER_NETWORK in result.get("stdout", ""):
        return DOCKER_NETWORK

    # Crea la rete
    create_result = await _call_bridge(
        f"docker network create {DOCKER_NETWORK}",
        timeout=10
    )

    if create_result.get("exit_code", -1) == 0:
        logger.info(f"Rete Docker '{DOCKER_NETWORK}' creata.")
        # Connetti il coordinator alla rete
        await _call_bridge(
            f"docker network connect {DOCKER_NETWORK} nik29-coordinator",
            timeout=10
        )
        return DOCKER_NETWORK

    # Fallback: usa la rete del coordinator
    fallback_result = await _call_bridge(
        "docker inspect nik29-coordinator --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'",
        timeout=10
    )
    networks = fallback_result.get("stdout", "").strip().split()
    if networks:
        return networks[0]

    return "bridge"  # Default Docker network


# ═══════════════════════════════════════════════════════════════════
# MAIN TOOL: GENERATE AGENT
# ═══════════════════════════════════════════════════════════════════

async def execute_generate_agent(args: dict) -> str:
    """
    Handler principale per il tool generate_agent.

    Flusso:
    1. Validazione input
    2. Generazione codice con GPT-4.1
    3. Validazione sintassi
    4. Scrittura file su host via bridge
    5. Build immagine Docker
    6. Avvio container
    7. Health check
    8. Registrazione in agents.json
    """
    name = args.get("name", "").strip().lower().replace(" ", "_").replace("-", "_")
    description = args.get("description", "").strip()
    capabilities = args.get("capabilities", [])
    tech_stack = args.get("tech_stack", "").strip()

    # ─── STEP 1: Validazione input ───────────────────────────────
    if not name:
        return "❌ Errore: 'name' è obbligatorio."
    if not description:
        return "❌ Errore: 'description' è obbligatorio."
    if not capabilities:
        return "❌ Errore: 'capabilities' deve contenere almeno una capacità."

    # Validazione nome
    if not re.match(r'^[a-z][a-z0-9_]{1,30}$', name):
        return (
            "❌ Errore: il nome deve essere snake_case, iniziare con lettera, "
            "2-31 caratteri (solo a-z, 0-9, _)."
        )

    # Nomi protetti
    if name in PROTECTED_NAMES:
        return f"❌ Errore: '{name}' è un nome protetto e non può essere usato."

    # Agente già esistente
    if _agent_exists(name):
        return (
            f"❌ Errore: l'agente '{name}' esiste già. "
            f"Usa remove_docker_agent per rimuoverlo prima di ricrearlo."
        )

    # Limite agenti
    if _count_docker_agents() >= MAX_EXTERNAL_AGENTS:
        return (
            f"❌ Errore: raggiunto il limite massimo di {MAX_EXTERNAL_AGENTS} agenti Docker. "
            f"Rimuovine uno prima di crearne un altro."
        )

    # Porta disponibile
    port = _next_available_port()
    if port is None:
        return "❌ Errore: nessuna porta disponibile nel range 4006-4020."

    container_name = f"nik29-{name}"
    agent_dir = f"{PROJECT_DIR}/agents/{name}"

    steps_log = [f"🔧 Creazione agente Docker: **{name}**"]
    steps_log.append(f"   Porta: {port} | Container: {container_name}")

    # ─── STEP 2: Generazione codice ─────────────────────────────
    steps_log.append("\n📝 Generazione codice con GPT-4.1...")
    try:
        code_data = await _generate_agent_code(
            name, description, capabilities, tech_stack, port
        )
    except RuntimeError as e:
        return f"❌ Errore generazione codice: {e}"

    # ─── STEP 3: Validazione sintassi ────────────────────────────
    steps_log.append("🔍 Validazione sintassi...")

    # Valida main.py
    py_error = _validate_python_syntax(code_data["main_py"], "main.py")
    if py_error:
        return f"❌ Codice generato non valido: {py_error}"

    # Valida Dockerfile
    df_error = _validate_dockerfile(code_data["dockerfile"])
    if df_error:
        return f"❌ Dockerfile non valido: {df_error}"

    steps_log.append("   ✓ Sintassi Python OK")
    steps_log.append("   ✓ Dockerfile OK")

    # ─── STEP 4: Scrittura file su host ──────────────────────────
    steps_log.append(f"\n📁 Scrittura file in {agent_dir}/...")

    # Crea directory
    mkdir_result = await _call_bridge(f"mkdir -p {agent_dir}", timeout=10)
    if mkdir_result.get("exit_code", -1) != 0:
        return f"❌ Impossibile creare directory: {mkdir_result.get('stderr', '')}"

    # Scrivi i file (usa heredoc con delimitatore sicuro)
    files_to_write = {
        "Dockerfile": code_data["dockerfile"],
        "main.py": code_data["main_py"],
        "requirements.txt": code_data["requirements_txt"],
    }

    for filename, content in files_to_write.items():
        filepath = f"{agent_dir}/{filename}"
        # Usa python3 per scrivere file in modo sicuro (evita problemi con heredoc)
        escaped_content = content.replace("\\", "\\\\").replace("'", "\\'")
        write_cmd = (
            f"python3 -c \"import sys; "
            f"open('{filepath}', 'w').write(sys.stdin.read())\" "
            f"<< 'ENDOFNIK29FILE'\n{content}\nENDOFNIK29FILE"
        )
        # Metodo alternativo più robusto: base64
        import base64
        b64_content = base64.b64encode(content.encode()).decode()
        write_cmd = (
            f"echo '{b64_content}' | base64 -d > '{filepath}'"
        )
        write_result = await _call_bridge(write_cmd, timeout=15, cwd=agent_dir)
        if write_result.get("exit_code", -1) != 0:
            return f"❌ Errore scrittura {filename}: {write_result.get('stderr', '')}"

    steps_log.append("   ✓ Dockerfile scritto")
    steps_log.append("   ✓ main.py scritto")
    steps_log.append("   ✓ requirements.txt scritto")

    # ─── STEP 5: Assicura rete Docker ────────────────────────────
    network = await _ensure_docker_network()
    steps_log.append(f"\n🌐 Rete Docker: {network}")

    # ─── STEP 6: Build immagine Docker ───────────────────────────
    steps_log.append(f"\n🏗️ Build immagine Docker: {container_name}...")

    build_result = await _call_bridge(
        f"docker build -t {container_name} {agent_dir}",
        timeout=120,
        cwd=agent_dir
    )
    if build_result.get("exit_code", -1) != 0:
        error_output = build_result.get("stderr", "") + build_result.get("stdout", "")
        return (
            f"❌ Errore build Docker:\n{error_output[-500:]}\n\n"
            f"I file sono stati salvati in {agent_dir}/ — puoi correggerli manualmente."
        )
    steps_log.append("   ✓ Build completata")

    # ─── STEP 7: Avvio container ─────────────────────────────────
    steps_log.append(f"\n🚀 Avvio container {container_name}...")

    # Rimuovi eventuale container con stesso nome (orfano)
    await _call_bridge(f"docker rm -f {container_name} 2>/dev/null", timeout=10)

    run_cmd = (
        f"docker run -d "
        f"--name {container_name} "
        f"--network {network} "
        f"-p {port}:{port} "
        f"--restart unless-stopped "
        f"{container_name}"
    )
    run_result = await _call_bridge(run_cmd, timeout=30)
    if run_result.get("exit_code", -1) != 0:
        return (
            f"❌ Errore avvio container:\n{run_result.get('stderr', '')}\n"
            f"Immagine buildata con successo — prova ad avviare manualmente."
        )
    steps_log.append("   ✓ Container avviato")

    # ─── STEP 8: Health check ────────────────────────────────────
    steps_log.append("\n💓 Health check...")

    healthy = False
    for attempt in range(15):  # 15 tentativi x 2s = 30s max
        await asyncio.sleep(2)
        health_result = await _call_bridge(
            f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health",
            timeout=5
        )
        status_code = health_result.get("stdout", "").strip()
        if status_code == "200":
            healthy = True
            break

    if not healthy:
        # Cleanup: ferma e rimuovi il container
        steps_log.append("   ✗ Health check fallito dopo 30s")
        await _call_bridge(f"docker stop {container_name}", timeout=10)
        await _call_bridge(f"docker rm {container_name}", timeout=10)

        # Recupera log per debug
        logs_result = await _call_bridge(
            f"docker logs {container_name} 2>&1 | tail -20",
            timeout=10
        )
        logs_output = logs_result.get("stdout", "nessun log disponibile")

        return (
            f"❌ L'agente non risponde al health check dopo 30 secondi.\n"
            f"Container fermato e rimosso.\n\n"
            f"**Ultimi log:**\n```\n{logs_output}\n```\n\n"
            f"I file sorgente sono in {agent_dir}/ — controlla main.py per errori."
        )

    steps_log.append("   ✓ Agente risponde correttamente")

    # ─── STEP 9: Registrazione in agents.json ────────────────────
    agents = _load_agents_registry()
    new_agent = {
        "name": name,
        "description": description,
        "url": f"http://{container_name}:{port}",
        "port": port,
        "capabilities": capabilities,
        "container": container_name,
        "tech_stack": tech_stack or None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    agents.append(new_agent)
    _save_agents_registry(agents)

    steps_log.append("\n📋 Agente registrato in agents.json")

    # ─── RISULTATO FINALE ────────────────────────────────────────
    steps_log.append(f"\n{'═' * 50}")
    steps_log.append(f"✅ Agente **{name}** creato con successo!")
    steps_log.append(f"   URL interno: http://{container_name}:{port}")
    steps_log.append(f"   URL host: http://localhost:{port}")
    steps_log.append(f"   Capacità: {', '.join(capabilities)}")
    steps_log.append(f"   File: {agent_dir}/")
    steps_log.append(f"\nUsa `delegate_to_agent` con agent_name='{name}' per inviargli task.")

    return "\n".join(steps_log)


# ═══════════════════════════════════════════════════════════════════
# TOOL: LIST DOCKER AGENTS
# ═══════════════════════════════════════════════════════════════════

async def execute_list_docker_agents(args: dict) -> str:
    """
    Lista tutti gli agenti Docker registrati con il loro stato.
    Controlla se i container sono effettivamente running.
    """
    agents = _load_agents_registry()

    if not agents:
        return "📋 Nessun agente Docker registrato."

    lines = [f"📋 **Agenti Docker Registrati** ({len(agents)} totale)\n"]

    for agent in agents:
        container = agent.get("container", f"nik29-{agent['name']}")

        # Controlla stato container via bridge
        status = "unknown"
        if agent.get("port"):
            status_result = await _call_bridge(
                f"docker inspect --format='{{{{.State.Status}}}}' {container} 2>/dev/null",
                timeout=5
            )
            raw_status = status_result.get("stdout", "").strip()
            if raw_status in ("running", "exited", "paused", "restarting"):
                status = raw_status
            elif status_result.get("exit_code", -1) != 0:
                status = "not_found"
        else:
            # Agente legacy (es. immagini) senza porta esplicita — check health
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    resp = await client.get(f"{agent['url']}/health")
                    status = "running" if resp.status_code == 200 else "unhealthy"
            except Exception:
                status = "unreachable"

        # Emoji stato
        status_emoji = {
            "running": "🟢",
            "exited": "🔴",
            "paused": "⏸️",
            "not_found": "❓",
            "unreachable": "🔴",
            "unhealthy": "🟡",
            "unknown": "❓",
        }.get(status, "❓")

        port_str = f":{agent['port']}" if agent.get("port") else ""
        caps_str = ", ".join(agent.get("capabilities", []))

        lines.append(
            f"### {status_emoji} {agent['name']}\n"
            f"- **Stato**: {status}\n"
            f"- **URL**: {agent['url']}\n"
            f"- **Porta**: {agent.get('port', 'N/A')}\n"
            f"- **Container**: {container}\n"
            f"- **Capacità**: {caps_str}\n"
            f"- **Descrizione**: {agent.get('description', '-')}\n"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# TOOL: REMOVE DOCKER AGENT
# ═══════════════════════════════════════════════════════════════════

async def execute_remove_docker_agent(args: dict) -> str:
    """
    Ferma e rimuove un agente Docker.
    Stoppa container, rimuove immagine, deregistra da agents.json.
    """
    name = args.get("name", "").strip().lower()
    remove_files = args.get("remove_files", False)

    if not name:
        return "❌ Errore: 'name' è obbligatorio."

    # Protezione nomi
    if name in PROTECTED_NAMES:
        return f"❌ Errore: '{name}' è un agente protetto e non può essere rimosso."

    # Verifica esistenza
    agents = _load_agents_registry()
    agent = None
    for a in agents:
        if a["name"] == name:
            agent = a
            break

    if not agent:
        available = [a["name"] for a in agents]
        return (
            f"❌ Agente '{name}' non trovato.\n"
            f"Agenti registrati: {', '.join(available) if available else 'nessuno'}"
        )

    container_name = agent.get("container", f"nik29-{name}")
    steps_log = [f"🗑️ Rimozione agente: **{name}**\n"]

    # Step 1: Stop container
    stop_result = await _call_bridge(f"docker stop {container_name}", timeout=15)
    if stop_result.get("exit_code", -1) == 0:
        steps_log.append(f"   ✓ Container {container_name} fermato")
    else:
        steps_log.append(f"   ⚠️ Container non in esecuzione o non trovato")

    # Step 2: Remove container
    rm_result = await _call_bridge(f"docker rm {container_name}", timeout=10)
    if rm_result.get("exit_code", -1) == 0:
        steps_log.append(f"   ✓ Container rimosso")

    # Step 3: Remove image
    rmi_result = await _call_bridge(f"docker rmi {container_name}", timeout=15)
    if rmi_result.get("exit_code", -1) == 0:
        steps_log.append(f"   ✓ Immagine Docker rimossa")
    else:
        steps_log.append(f"   ⚠️ Immagine non rimossa (potrebbe essere in uso)")

    # Step 4: Remove files (opzionale)
    if remove_files:
        agent_dir = f"{PROJECT_DIR}/agents/{name}"
        rmdir_result = await _call_bridge(f"rm -rf {agent_dir}", timeout=10)
        if rmdir_result.get("exit_code", -1) == 0:
            steps_log.append(f"   ✓ File sorgente rimossi ({agent_dir})")
        else:
            steps_log.append(f"   ⚠️ Errore rimozione file: {rmdir_result.get('stderr', '')}")

    # Step 5: Deregistra da agents.json
    agents = [a for a in agents if a["name"] != name]
    _save_agents_registry(agents)
    steps_log.append(f"   ✓ Agente deregistrato da agents.json")

    steps_log.append(f"\n✅ Agente **{name}** rimosso completamente.")
    return "\n".join(steps_log)
