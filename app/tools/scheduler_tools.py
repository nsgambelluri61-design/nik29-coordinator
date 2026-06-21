"""
Level 3 Autonomy — Scheduler Tools
Tools for managing scheduled tasks via the coordinator.
"""

import json
import uuid
import logging
from datetime import datetime, timezone

from app.scheduler.scheduler import (
    _load_tasks,
    _save_tasks,
    _register_task_in_scheduler,
    _execute_task,
    get_scheduler,
)

logger = logging.getLogger("nik29.scheduler_tools")


# ============================================================
# SCHEDULE TASK TOOL
# ============================================================

SCHEDULE_TASK_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "schedule_task",
        "description": (
            "Manage scheduled tasks: add, remove, list, enable, or disable. "
            "Tasks run on cron schedules and can send Telegram messages or execute commands."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "remove", "list", "enable", "disable"],
                    "description": "Operation to perform on scheduled tasks.",
                },
                "task_id": {
                    "type": "string",
                    "description": "ID of the task (for remove/enable/disable).",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the task (for add).",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "Cron expression (5 fields: min hour dom month dow). Example: '0 9 * * *' for daily at 9:00.",
                },
                "action": {
                    "type": "string",
                    "description": "Action type: morning_briefing, site_health_check, weekly_report, custom_telegram, custom_command.",
                },
                "action_params": {
                    "type": "object",
                    "description": "Parameters for the action (e.g., {message: '...'} for custom_telegram).",
                },
            },
            "required": ["operation"],
        },
    },
}


async def schedule_task(
    operation: str,
    task_id: str = "",
    name: str = "",
    cron_expression: str = "",
    action: str = "",
    action_params: dict = None,
) -> dict:
    """Manage scheduled tasks."""
    tasks = _load_tasks()

    if operation == "list":
        return {
            "tasks": tasks,
            "count": len(tasks),
            "scheduler_running": get_scheduler() is not None and get_scheduler().running,
        }

    elif operation == "add":
        if not name or not cron_expression or not action:
            return {"error": "Missing required fields: name, cron_expression, action"}

        new_task = {
            "id": str(uuid.uuid4())[:8],
            "name": name,
            "cron_expression": cron_expression,
            "action": action,
            "action_params": action_params or {},
            "enabled": True,
            "last_run": None,
            "last_result": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        tasks.append(new_task)
        _save_tasks(tasks)
        _register_task_in_scheduler(new_task)
        return {"success": True, "task": new_task}

    elif operation == "remove":
        if not task_id:
            return {"error": "task_id is required for remove operation"}
        original_count = len(tasks)
        tasks = [t for t in tasks if t["id"] != task_id]
        if len(tasks) == original_count:
            return {"error": f"Task not found: {task_id}"}
        _save_tasks(tasks)
        # Remove from scheduler
        scheduler = get_scheduler()
        if scheduler:
            try:
                scheduler.remove_job(task_id)
            except Exception:
                pass
        return {"success": True, "removed": task_id}

    elif operation == "enable":
        if not task_id:
            return {"error": "task_id is required for enable operation"}
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        task["enabled"] = True
        _save_tasks(tasks)
        _register_task_in_scheduler(task)
        return {"success": True, "task": task}

    elif operation == "disable":
        if not task_id:
            return {"error": "task_id is required for disable operation"}
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return {"error": f"Task not found: {task_id}"}
        task["enabled"] = False
        _save_tasks(tasks)
        scheduler = get_scheduler()
        if scheduler:
            try:
                scheduler.remove_job(task_id)
            except Exception:
                pass
        return {"success": True, "task": task}

    return {"error": f"Unknown operation: {operation}"}


# ============================================================
# RUN TASK NOW TOOL
# ============================================================

RUN_TASK_NOW_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "run_task_now",
        "description": (
            "Manually trigger a scheduled task immediately, regardless of its cron schedule."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to run immediately.",
                },
            },
            "required": ["task_id"],
        },
    },
}


async def run_task_now(task_id: str) -> dict:
    """Execute a task immediately."""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"error": f"Task not found: {task_id}"}

    await _execute_task(task_id)

    # Reload to get updated result
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    return {
        "success": True,
        "task_name": task["name"] if task else task_id,
        "result": task.get("last_result") if task else None,
    }


# ============================================================
# TOOL REGISTRY
# ============================================================

SCHEDULER_TOOLS = [SCHEDULE_TASK_TOOL_DEF, RUN_TASK_NOW_TOOL_DEF]

SCHEDULER_TOOL_HANDLERS = {
    "schedule_task": schedule_task,
    "run_task_now": run_task_now,
}
