"""
Level 3 Autonomy — Task Scheduler
APScheduler-based cron scheduling with persistent task storage.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.tools.monitoring_tools import health_check, send_alert, _append_health_log

logger = logging.getLogger("nik29.scheduler")

TASKS_FILE = "/data/scheduler/tasks.json"

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


def _load_tasks() -> list:
    """Load tasks from JSON file."""
    try:
        if os.path.exists(TASKS_FILE):
            with open(TASKS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
    return []


def _save_tasks(tasks: list):
    """Save tasks to JSON file."""
    try:
        os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
        with open(TASKS_FILE, "w") as f:
            json.dump(tasks, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to save tasks: {e}")


async def _execute_task(task_id: str):
    """Execute a scheduled task by its ID."""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        logger.error(f"Task not found: {task_id}")
        return

    logger.info(f"Executing scheduled task: {task['name']} ({task_id})")
    result = {"success": False, "output": ""}

    try:
        action = task.get("action", "")

        if action == "morning_briefing":
            result = await _morning_briefing()
        elif action == "site_health_check":
            result = await _site_health_check()
        elif action == "weekly_report":
            result = await _weekly_report()
        elif action == "custom_telegram":
            # Custom message task
            message = task.get("action_params", {}).get("message", "Task executed.")
            await send_alert(message=message, severity="info")
            result = {"success": True, "output": "Message sent."}
        elif action == "custom_command":
            # Custom host command
            from app.tools.monitoring_tools import _host_bridge_command
            cmd = task.get("action_params", {}).get("command", "echo ok")
            cmd_result = await _host_bridge_command(cmd)
            result = {"success": cmd_result.get("success", False), "output": str(cmd_result)}
        else:
            result = {"success": False, "output": f"Unknown action: {action}"}

    except Exception as e:
        result = {"success": False, "output": f"Error: {str(e)}"}
        logger.error(f"Task execution error ({task_id}): {e}", exc_info=True)

    # Update last_run and last_result
    task["last_run"] = datetime.now(timezone.utc).isoformat()
    task["last_result"] = result
    _save_tasks(tasks)

    logger.info(f"Task {task['name']} completed: {result.get('success')}")


# ============================================================
# BUILT-IN TASK ACTIONS
# ============================================================

async def _morning_briefing():
    """Morning briefing: system status + summary."""
    report = await health_check(check_type="all")
    status = report.get("overall_status", "unknown")

    status_emoji = "✅" if status == "healthy" else "⚠️"

    # Build message
    checks = report.get("checks", {})
    lines = [
        f"☀️ <b>Buongiorno! Report mattutino</b>",
        f"",
        f"Stato generale: {status_emoji} {status.upper()}",
    ]

    if "website" in checks:
        site_ok = "✅" if checks["website"].get("reachable") else "❌"
        lines.append(f"Sito web: {site_ok} (HTTP {checks['website'].get('status_code', '?')})")

    if "docker" in checks:
        n_containers = checks["docker"].get("count", 0)
        lines.append(f"Container Docker: {n_containers} attivi")

    if "disk" in checks:
        lines.append(f"Disco: {checks['disk'].get('root_usage', '?')} usato")

    message = "\n".join(lines)
    await send_alert(message=message, severity="info")
    return {"success": True, "output": message}


async def _site_health_check():
    """Hourly site health check."""
    report = await health_check(check_type="website")
    checks = report.get("checks", {})
    website = checks.get("website", {})

    if website.get("reachable"):
        return {"success": True, "output": f"Site OK (HTTP {website.get('status_code')})"}
    else:
        # Site is down — alert
        await send_alert(
            message=(
                f"❌ Il sito ildormire.com NON risponde!\n"
                f"Errore: {website.get('error', 'HTTP ' + str(website.get('status_code', '?')))}\n"
                f"Provo a risolvere automaticamente..."
            ),
            severity="critical",
        )
        # Try auto-fix
        from app.tools.monitoring_tools import auto_debug
        fix = await auto_debug(issue="website down", action="auto")
        return {"success": fix.get("resolved", False), "output": str(fix)}


async def _weekly_report():
    """Weekly report: uptime, errors, tasks completed."""
    # Read health log for stats
    log_entries = []
    try:
        if os.path.exists("/data/monitoring/health_log.json"):
            with open("/data/monitoring/health_log.json", "r") as f:
                log_entries = json.load(f)
    except Exception:
        pass

    # Count events from last 7 days
    from datetime import timedelta
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_checks = 0
    errors_detected = 0
    auto_fixes = 0
    alerts_sent = 0

    for entry in log_entries:
        ts = entry.get("timestamp", "")
        try:
            entry_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if entry_time < week_ago:
                continue
        except (ValueError, TypeError):
            continue

        entry_type = entry.get("type", "")
        if entry_type == "auto_debug":
            auto_fixes += 1
            if not entry.get("resolved"):
                errors_detected += 1
        elif entry_type == "alert":
            alerts_sent += 1
        elif "overall_status" in entry:
            total_checks += 1
            if entry.get("overall_status") != "healthy":
                errors_detected += 1

    message = (
        f"📊 <b>Report Settimanale nik29</b>\n\n"
        f"Periodo: ultimi 7 giorni\n"
        f"• Controlli eseguiti: {total_checks}\n"
        f"• Problemi rilevati: {errors_detected}\n"
        f"• Fix automatici tentati: {auto_fixes}\n"
        f"• Alert inviati: {alerts_sent}\n\n"
        f"{'✅ Settimana tranquilla!' if errors_detected == 0 else '⚠️ Ci sono stati alcuni problemi, controlla il log.'}"
    )

    await send_alert(message=message, severity="info")
    return {"success": True, "output": message}


# ============================================================
# SCHEDULER MANAGEMENT
# ============================================================

def _parse_cron(cron_expr: str) -> dict:
    """Parse a cron expression into APScheduler kwargs.
    Supports: minute hour day_of_month month day_of_week
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr}")

    fields = ["minute", "hour", "day", "month", "day_of_week"]
    kwargs = {}
    for i, field in enumerate(fields):
        if parts[i] != "*":
            kwargs[field] = parts[i]
    return kwargs


def _register_task_in_scheduler(task: dict):
    """Register a single task in the APScheduler."""
    global _scheduler
    if not _scheduler or not task.get("enabled", True):
        return

    task_id = task["id"]
    cron_expr = task.get("cron_expression", "")

    # Remove existing job if any
    try:
        _scheduler.remove_job(task_id)
    except Exception:
        pass

    if not cron_expr:
        return

    try:
        cron_kwargs = _parse_cron(cron_expr)
        _scheduler.add_job(
            _execute_task,
            trigger=CronTrigger(**cron_kwargs),
            id=task_id,
            args=[task_id],
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(f"Registered scheduled task: {task['name']} ({cron_expr})")
    except Exception as e:
        logger.error(f"Failed to register task {task_id}: {e}")


async def start_scheduler():
    """Initialize and start the scheduler with all enabled tasks."""
    global _scheduler

    _scheduler = AsyncIOScheduler(timezone="Europe/Rome")

    tasks = _load_tasks()
    for task in tasks:
        if task.get("enabled", True):
            _register_task_in_scheduler(task)

    _scheduler.start()
    logger.info(f"Scheduler started with {len(tasks)} tasks loaded.")


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Get the global scheduler instance."""
    return _scheduler
