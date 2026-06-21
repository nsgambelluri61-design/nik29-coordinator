"""
planner — Modulo di pianificazione autonoma per nik29-coordinator.

Classifica i messaggi in SIMPLE/COMPLEX e genera piani multi-step
per task complessi, mantenendo invariato il flusso per task semplici.
"""

from app.planner.planner import TaskPlanner, classify_message
from app.planner.executor import PlanExecutor

__all__ = ["TaskPlanner", "PlanExecutor", "classify_message"]
