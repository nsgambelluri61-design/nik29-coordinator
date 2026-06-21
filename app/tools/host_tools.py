"""
╔══════════════════════════════════════════════════════════════════╗
║  NIK29 HOST TOOLS - Level 2 Autonomy                            ║
║  Tool per esecuzione comandi host, gestione Docker e Git        ║
╚══════════════════════════════════════════════════════════════════╝

Questi tool comunicano con il Host Bridge (localhost:4002) per eseguire
comandi sul Mac host FUORI dal container Docker.

TOOL DISPONIBILI:
  1. host_shell     - Esecuzione comandi generici sul Mac host
  2. docker_manage  - Gestione del proprio container Docker
  3. git_auto       - Operazioni Git autonome (add, commit, push, ecc.)

REQUISITI:
  - Host Bridge attivo su localhost:4002
  - Rete Docker con accesso a host.docker.internal

AUTORE: nik29-coordinator Level 2 Autonomy
VERSIONE: 1.0.0
"""

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("host_tools")

# ═══════════════════════════════════════════════════════════════════
# CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════════════

# URL del bridge (da dentro Docker, host.docker.internal punta al Mac)
BRIDGE_URL = os.environ.get("HOST_BRIDGE_URL", "http://host.docker.internal:4002")

# Timeout per le richieste HTTP al bridge
HTTP_TIMEOUT = 60.0

# Directory del progetto sul Mac host
PROJECT_DIR = os.environ.get(
    "HOST_PROJECT_DIR",
    "/Users/nicolasgambelluri/Downloads/nik29-coordinator-v0.6.0"
)


# ═══════════════════════════════════════════════════════════════════
# CLIENT HTTP PER IL BRIDGE
# ═══════════════════════════════════════════════════════════════════

async def _call_bridge(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None
) -> dict:
    """
    Chiama il Host Bridge per eseguire un comando sul Mac.

    Args:
        command: Comando da eseguire
        timeout: Timeout in secondi
        cwd: Directory di lavoro (opzionale)

    Returns:
        dict con stdout, stderr, exit_code
    """
    payload = {
        "command": command,
        "timeout": timeout,
    }
    if cwd:
        payload["cwd"] = cwd

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{BRIDGE_URL}/exec",
                json=payload
            )

            result = response.json()

            # Log per debug
            if result.get("exit_code", 0) != 0:
                logger.warning(
                    f"Comando '{command}' exit_code={result.get('exit_code')} "
                    f"stderr={result.get('stderr', '')[:200]}"
                )

            return result

    except httpx.ConnectError:
        error_msg = (
            "Impossibile connettersi al Host Bridge (localhost:4002). "
            "Verifica che host_bridge.py sia in esecuzione sul Mac."
        )
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "exit_code": -99,
            "error": "bridge_unreachable"
        }
    except httpx.TimeoutException:
        error_msg = f"Timeout nella comunicazione con il bridge (>{HTTP_TIMEOUT}s)"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "exit_code": -98,
            "error": "bridge_timeout"
        }
    except Exception as e:
        error_msg = f"Errore comunicazione bridge: {str(e)}"
        logger.error(error_msg)
        return {
            "stdout": "",
            "stderr": error_msg,
            "exit_code": -97,
            "error": str(e)
        }


async def _check_bridge_health() -> bool:
    """Verifica che il bridge sia raggiungibile e funzionante."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BRIDGE_URL}/health")
            return response.status_code == 200
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
# TOOL 1: HOST SHELL
# ═══════════════════════════════════════════════════════════════════

class HostShellTool:
    """
    Esegue comandi shell sul Mac host (fuori dal container Docker).
    Utilizza il Host Bridge su localhost:4002.
    """

    async def execute(self, command: str, timeout: int = 30, cwd: Optional[str] = None) -> str:
        """
        Esegue un comando sul Mac host tramite il bridge.

        Args:
            command: Il comando da eseguire
            timeout: Timeout in secondi (max 120)
            cwd: Directory di lavoro opzionale

        Returns:
            Stringa con output del comando
        """
        if not command or not command.strip():
            return "Errore: nessun comando specificato."

        # Limita timeout
        timeout = min(max(timeout, 5), 120)

        result = await _call_bridge(command, timeout=timeout, cwd=cwd)

        # Formatta output leggibile
        output_parts = []

        if result.get("stdout"):
            output_parts.append(result["stdout"])

        if result.get("stderr"):
            if output_parts:
                output_parts.append(f"\n--- STDERR ---\n{result['stderr']}")
            else:
                output_parts.append(result["stderr"])

        if not output_parts:
            exit_code = result.get("exit_code", 0)
            if exit_code == 0:
                output_parts.append("(comando completato con successo, nessun output)")
            else:
                output_parts.append(f"(comando terminato con exit code {exit_code})")

        # Aggiungi info exit code se errore
        exit_code = result.get("exit_code", 0)
        if exit_code != 0 and exit_code > 0:
            output_parts.append(f"\n[Exit code: {exit_code}]")

        return "\n".join(output_parts)


# ═══════════════════════════════════════════════════════════════════
# TOOL 2: DOCKER MANAGE
# ═══════════════════════════════════════════════════════════════════

class DockerManageTool:
    """
    Gestisce il proprio container Docker (nik29-coordinator).
    Permette restart, rebuild, logs, status.
    """

    # Nome del container/servizio
    CONTAINER_NAME = "nik29-coordinator"
    COMPOSE_FILE = f"{PROJECT_DIR}/docker-compose.yml"

    async def execute(self, action: str, lines: int = 50) -> str:
        """
        Esegue un'azione di gestione Docker.

        Args:
            action: Azione da eseguire (status, logs, restart, rebuild)
            lines: Numero di righe per i log (default 50)

        Returns:
            Risultato dell'operazione
        """
        action = action.lower().strip()

        if action == "status":
            return await self._status()
        elif action == "logs":
            return await self._logs(lines)
        elif action == "restart":
            return await self._restart()
        elif action == "rebuild":
            return await self._rebuild()
        elif action == "health":
            return await self._health()
        else:
            return (
                f"Azione '{action}' non riconosciuta. "
                f"Azioni disponibili: status, logs, restart, rebuild, health"
            )

    async def _status(self) -> str:
        """Mostra lo stato del container."""
        result = await _call_bridge(
            f"docker ps -a --filter name={self.CONTAINER_NAME} "
            f"--format '{{{{.Status}}}} | {{{{.Ports}}}} | {{{{.Image}}}}'",
            timeout=10
        )
        if result.get("stdout"):
            return f"Container {self.CONTAINER_NAME}:\n{result['stdout']}"
        return f"Container {self.CONTAINER_NAME} non trovato o errore: {result.get('stderr', '')}"

    async def _logs(self, lines: int = 50) -> str:
        """Mostra gli ultimi N log del container."""
        lines = min(max(lines, 10), 500)
        result = await _call_bridge(
            f"docker logs --tail {lines} {self.CONTAINER_NAME}",
            timeout=15
        )
        output = result.get("stdout", "") + result.get("stderr", "")
        if output:
            return f"Ultimi {lines} log di {self.CONTAINER_NAME}:\n{output}"
        return "Nessun log disponibile."

    async def _restart(self) -> str:
        """Riavvia il container (docker-compose restart)."""
        result = await _call_bridge(
            f"cd {PROJECT_DIR} && docker-compose restart {self.CONTAINER_NAME}",
            timeout=60,
            cwd=PROJECT_DIR
        )
        if result.get("exit_code", -1) == 0:
            return (
                f"Container {self.CONTAINER_NAME} riavviato con successo.\n"
                f"NOTA: Questo tool potrebbe non rispondere per qualche secondo "
                f"durante il riavvio."
            )
        return f"Errore nel riavvio: {result.get('stderr', result.get('stdout', 'errore sconosciuto'))}"

    async def _rebuild(self) -> str:
        """Rebuild completo: build --no-cache + recreate."""
        # Step 1: Build
        build_result = await _call_bridge(
            f"cd {PROJECT_DIR} && docker-compose build --no-cache {self.CONTAINER_NAME}",
            timeout=120,
            cwd=PROJECT_DIR
        )
        if build_result.get("exit_code", -1) != 0:
            return f"Errore durante il build:\n{build_result.get('stderr', build_result.get('stdout', ''))}"

        # Step 2: Recreate
        recreate_result = await _call_bridge(
            f"cd {PROJECT_DIR} && docker-compose up -d --force-recreate {self.CONTAINER_NAME}",
            timeout=60,
            cwd=PROJECT_DIR
        )
        if recreate_result.get("exit_code", -1) == 0:
            return (
                f"Rebuild completato con successo!\n"
                f"Build: OK\n"
                f"Recreate: OK\n"
                f"NOTA: Il container si sta riavviando. "
                f"Potrebbe non rispondere per 10-30 secondi."
            )
        return f"Build OK ma errore nel recreate:\n{recreate_result.get('stderr', '')}"

    async def _health(self) -> str:
        """Controlla lo stato di salute del container."""
        result = await _call_bridge(
            f"docker inspect --format='{{{{.State.Health.Status}}}}' {self.CONTAINER_NAME}",
            timeout=10
        )
        health_status = result.get("stdout", "").strip()

        # Info aggiuntive
        stats_result = await _call_bridge(
            f"docker stats --no-stream --format "
            f"'CPU: {{{{.CPUPerc}}}} | MEM: {{{{.MemUsage}}}} | NET: {{{{.NetIO}}}}' "
            f"{self.CONTAINER_NAME}",
            timeout=10
        )
        stats = stats_result.get("stdout", "N/A").strip()

        return (
            f"Health check: {health_status or 'N/A'}\n"
            f"Risorse: {stats}"
        )


# ═══════════════════════════════════════════════════════════════════
# TOOL 3: GIT AUTO
# ═══════════════════════════════════════════════════════════════════

class GitAutoTool:
    """
    Gestione autonoma di Git per il progetto nik29-coordinator.
    Permette commit, push, status, log, diff.
    """

    def __init__(self):
        self.repo_dir = PROJECT_DIR

    async def execute(
        self,
        action: str,
        message: Optional[str] = None,
        files: Optional[str] = None,
        count: int = 10
    ) -> str:
        """
        Esegue un'operazione Git.

        Args:
            action: Azione (status, add_commit_push, log, diff, pull)
            message: Messaggio di commit (per add_commit_push)
            files: File da aggiungere (default "." = tutti)
            count: Numero di commit per log (default 10)

        Returns:
            Risultato dell'operazione
        """
        action = action.lower().strip()

        if action == "status":
            return await self._status()
        elif action == "add_commit_push":
            return await self._add_commit_push(message, files)
        elif action == "log":
            return await self._log(count)
        elif action == "diff":
            return await self._diff(files)
        elif action == "pull":
            return await self._pull()
        elif action == "branch":
            return await self._branch()
        else:
            return (
                f"Azione '{action}' non riconosciuta. "
                f"Azioni disponibili: status, add_commit_push, log, diff, pull, branch"
            )

    async def _status(self) -> str:
        """Mostra lo stato del repository."""
        result = await _call_bridge(
            "git status --short",
            timeout=10,
            cwd=self.repo_dir
        )
        status = result.get("stdout", "").strip()
        if not status:
            return "Repository pulito, nessuna modifica."
        return f"Stato repository:\n{status}"

    async def _add_commit_push(
        self,
        message: Optional[str] = None,
        files: Optional[str] = None
    ) -> str:
        """Esegue git add + commit + push in sequenza."""
        if not message:
            return "Errore: messaggio di commit obbligatorio per add_commit_push."

        files_to_add = files or "."
        results = []

        # Step 1: git add
        add_result = await _call_bridge(
            f"git add {files_to_add}",
            timeout=15,
            cwd=self.repo_dir
        )
        if add_result.get("exit_code", -1) != 0:
            return f"Errore in git add: {add_result.get('stderr', '')}"
        results.append("✓ git add completato")

        # Step 2: git commit
        # Escape del messaggio per sicurezza
        safe_message = message.replace('"', '\\"').replace("'", "\\'")
        commit_result = await _call_bridge(
            f'git commit -m "{safe_message}"',
            timeout=15,
            cwd=self.repo_dir
        )
        if commit_result.get("exit_code", -1) != 0:
            stderr = commit_result.get("stderr", "") + commit_result.get("stdout", "")
            if "nothing to commit" in stderr.lower():
                return "Nessuna modifica da committare (working tree pulito)."
            return f"Errore in git commit: {stderr}"
        results.append(f"✓ git commit: {message}")

        # Step 3: git push
        push_result = await _call_bridge(
            "git push origin HEAD",
            timeout=30,
            cwd=self.repo_dir
        )
        if push_result.get("exit_code", -1) != 0:
            stderr = push_result.get("stderr", "")
            # git push scrive su stderr anche in caso di successo
            if "->".lower() in stderr.lower() or "branch" in stderr.lower():
                results.append("✓ git push completato")
            else:
                return f"Add e commit OK, ma errore in push:\n{stderr}"
        else:
            results.append("✓ git push completato")

        return "\n".join(results)

    async def _log(self, count: int = 10) -> str:
        """Mostra gli ultimi N commit."""
        count = min(max(count, 1), 50)
        result = await _call_bridge(
            f"git log --oneline --graph -n {count}",
            timeout=10,
            cwd=self.repo_dir
        )
        log_output = result.get("stdout", "").strip()
        if log_output:
            return f"Ultimi {count} commit:\n{log_output}"
        return "Nessun commit trovato."

    async def _diff(self, files: Optional[str] = None) -> str:
        """Mostra le differenze correnti."""
        cmd = "git diff --stat"
        if files:
            cmd += f" -- {files}"

        result = await _call_bridge(cmd, timeout=15, cwd=self.repo_dir)
        diff_output = result.get("stdout", "").strip()

        if not diff_output:
            # Prova anche staged
            staged_result = await _call_bridge(
                "git diff --cached --stat",
                timeout=15,
                cwd=self.repo_dir
            )
            diff_output = staged_result.get("stdout", "").strip()
            if diff_output:
                return f"Differenze staged:\n{diff_output}"
            return "Nessuna differenza rilevata."

        return f"Differenze:\n{diff_output}"

    async def _pull(self) -> str:
        """Esegue git pull."""
        result = await _call_bridge(
            "git pull origin HEAD",
            timeout=30,
            cwd=self.repo_dir
        )
        output = result.get("stdout", "") + result.get("stderr", "")
        if result.get("exit_code", -1) == 0:
            return f"Pull completato:\n{output.strip()}"
        return f"Errore in git pull:\n{output.strip()}"

    async def _branch(self) -> str:
        """Mostra i branch."""
        result = await _call_bridge(
            "git branch -a",
            timeout=10,
            cwd=self.repo_dir
        )
        return result.get("stdout", "Nessun branch trovato.").strip()


# ═══════════════════════════════════════════════════════════════════
# DEFINIZIONI TOOL PER OPENAI FUNCTION CALLING
# ═══════════════════════════════════════════════════════════════════

HOST_SHELL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "host_shell",
        "description": (
            "Esegue un comando shell sul Mac HOST (fuori dal container Docker). "
            "Utile per operazioni sul sistema host: gestire file, controllare processi, "
            "eseguire script. I comandi sono filtrati da una whitelist di sicurezza. "
            "NON usare per comandi Docker o Git (usa docker_manage e git_auto)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "Il comando da eseguire sul Mac host. "
                        "Comandi consentiti: git, docker, ls, cat, grep, find, "
                        "mkdir, cp, mv, rm, echo, sed, python3, npm, node, curl, brew, ecc."
                    )
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in secondi (default 30, max 120)",
                    "default": 30
                },
                "cwd": {
                    "type": "string",
                    "description": (
                        "Directory di lavoro opzionale. "
                        "Default: ~/Downloads/nik29-coordinator-v0.6.0/"
                    )
                }
            },
            "required": ["command"]
        }
    }
}

DOCKER_MANAGE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "docker_manage",
        "description": (
            "Gestisce il proprio container Docker (nik29-coordinator). "
            "Permette di controllare lo stato, vedere i log, riavviare o "
            "ricostruire il container. ATTENZIONE: restart e rebuild causeranno "
            "una breve interruzione del servizio."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "logs", "restart", "rebuild", "health"],
                    "description": (
                        "Azione da eseguire: "
                        "status = stato container, "
                        "logs = ultimi log, "
                        "restart = riavvia container, "
                        "rebuild = build --no-cache + recreate, "
                        "health = stato di salute + risorse"
                    )
                },
                "lines": {
                    "type": "integer",
                    "description": "Numero di righe di log da mostrare (solo per action=logs, default 50)",
                    "default": 50
                }
            },
            "required": ["action"]
        }
    }
}

GIT_AUTO_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "git_auto",
        "description": (
            "Gestione autonoma di Git per il progetto nik29-coordinator. "
            "Permette di fare commit e push automatici, controllare lo stato, "
            "vedere la cronologia e le differenze. Opera sul repository host."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "add_commit_push", "log", "diff", "pull", "branch"],
                    "description": (
                        "Azione Git da eseguire: "
                        "status = mostra modifiche, "
                        "add_commit_push = add + commit + push (richiede message), "
                        "log = cronologia commit, "
                        "diff = differenze correnti, "
                        "pull = aggiorna da remoto, "
                        "branch = mostra branch"
                    )
                },
                "message": {
                    "type": "string",
                    "description": (
                        "Messaggio di commit (obbligatorio per add_commit_push). "
                        "Formato consigliato: 'tipo: descrizione' "
                        "(es. 'feat: nuovo tool X', 'fix: corretto bug Y')"
                    )
                },
                "files": {
                    "type": "string",
                    "description": (
                        "File specifici da aggiungere/diffondere "
                        "(default '.' = tutti i file modificati)"
                    )
                },
                "count": {
                    "type": "integer",
                    "description": "Numero di commit da mostrare per action=log (default 10)",
                    "default": 10
                }
            },
            "required": ["action"]
        }
    }
}


# ═══════════════════════════════════════════════════════════════════
# LISTA COMPLETA DEFINIZIONI (per import facile)
# ═══════════════════════════════════════════════════════════════════

ALL_TOOL_DEFINITIONS = [
    HOST_SHELL_TOOL_DEFINITION,
    DOCKER_MANAGE_TOOL_DEFINITION,
    GIT_AUTO_TOOL_DEFINITION,
]

# Istanze dei tool (singleton)
host_shell_tool = HostShellTool()
docker_manage_tool = DockerManageTool()
git_auto_tool = GitAutoTool()
