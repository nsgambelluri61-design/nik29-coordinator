"""
Tool Delegate per nik29-coordinator.
Delega task a sub-agenti specializzati via HTTP.
"""

import logging
from typing import Optional

from app.agent_client import agent_client

logger = logging.getLogger("delegate_tool")


class DelegateTool:
    """Delega task ai sub-agenti registrati."""

    async def execute(
        self,
        agent_name: str,
        instruction: str,
        files: Optional[list] = None
    ) -> str:
        """
        Delega un task a un sub-agente.

        Args:
            agent_name: Nome del sub-agente
            instruction: Istruzione dettagliata
            files: Lista di file da passare [{name, url}]

        Returns:
            Risultato dal sub-agente come stringa
        """
        if not agent_name:
            return "Errore: specificare il nome del sub-agente."

        if not instruction:
            return "Errore: specificare l'istruzione per il sub-agente."

        logger.info(f"Delego a '{agent_name}': {instruction[:80]}...")

        result = await agent_client.send_task(
            agent_name=agent_name,
            instruction=instruction,
            files=files or []
        )

        return result
