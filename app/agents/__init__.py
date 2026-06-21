"""
nik29-coordinator: Framework Multi-Agente
Package agents — gestione agenti specialisti.
"""

from .agent_manager import AgentManager, generate_agent_system_prompt

__all__ = ["AgentManager", "generate_agent_system_prompt"]
