"""
Tool Shell per nik29-coordinator.
Esegue comandi di sistema in modo sicuro con timeout e limiti di output.
"""

import asyncio
import logging
import shlex

logger = logging.getLogger("shell_tool")

# Comandi vietati per sicurezza
BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=/dev/zero",
    ":(){ :|:& };:", "shutdown", "reboot", "halt",
    "init 0", "init 6"
]

# Timeout massimo per un comando (secondi)
MAX_TIMEOUT = 60
MAX_OUTPUT_LENGTH = 10000


class ShellTool:
    """Esegue comandi shell in modo sicuro."""

    async def execute(self, command: str) -> str:
        """
        Esegue un comando shell e restituisce l'output.

        Args:
            command: Il comando da eseguire

        Returns:
            Output del comando (stdout + stderr) come stringa
        """
        if not command or not command.strip():
            return "Errore: nessun comando specificato."

        # Controlla comandi bloccati
        cmd_lower = command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return f"Comando bloccato per sicurezza: {command}"

        logger.info(f"Eseguo: {command}")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/data/workspace"
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=MAX_TIMEOUT
                )
            except asyncio.TimeoutError:
                process.kill()
                return f"Timeout: il comando non ha terminato entro {MAX_TIMEOUT} secondi."

            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                if output:
                    output += "\n--- STDERR ---\n"
                output += stderr.decode("utf-8", errors="replace")

            if not output:
                output = f"(comando completato con exit code {process.returncode})"

            # Tronca output troppo lungo
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + f"\n\n... (output troncato, totale {len(output)} caratteri)"

            # Aggiungi exit code se non zero
            if process.returncode != 0:
                output += f"\n[Exit code: {process.returncode}]"

            return output

        except Exception as e:
            return f"Errore esecuzione comando: {str(e)}"
