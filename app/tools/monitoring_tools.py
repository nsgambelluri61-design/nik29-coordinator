"""
Level 3 Autonomy — Monitoring Tools
Auto-debug, health checks, and Telegram alerts for nik29-coordinator.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

logger = logging.getLogger("nik29.monitoring_tools")

# --- Configuration ---
HOST_BRIDGE_URL = os.getenv("HOST_BRIDGE_URL", "http://host.docker.internal:4003")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID", "7072645786")
SITE_URL = os.getenv("MONITOR_SITE_URL", "https://ildormire.com")
HEALTH_LOG_PATH = "/data/monitoring/health_log.json"


# ============================================================
# UTILITY HELPERS
# ============================================================

async def _http_get(url: str, timeout: int = 10) -> dict:
    """Perform a GET request and return status + body snippet."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                body = await resp.text()
                return {
                    "status": resp.status,
                    "ok": 200 <= resp.status < 400,
                    "body_preview": body[:500],
                }
    except Exception as e:
        return {"status": 0, "ok": False, "error": str(e)}


async def _host_bridge_command(command: str) -> dict:
    """Execute a command on the Mac host via host_bridge."""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"command": command}
            async with session.post(
                f"{HOST_BRIDGE_URL}/execute",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                result = await resp.json()
                return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _send_telegram(message: str) -> dict:
    """Send a message via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
                return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _append_health_log(entry: dict):
    """Append an entry to the health log file."""
    try:
        os.makedirs(os.path.dirname(HEALTH_LOG_PATH), exist_ok=True)
        if os.path.exists(HEALTH_LOG_PATH):
            with open(HEALTH_LOG_PATH, "r") as f:
                log = json.load(f)
        else:
            log = []
        # Keep last 1000 entries
        log.append(entry)
        if len(log) > 1000:
            log = log[-1000:]
        with open(HEALTH_LOG_PATH, "w") as f:
            json.dump(log, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Failed to write health log: {e}")


# ============================================================
# HEALTH CHECK TOOL
# ============================================================

HEALTH_CHECK_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "health_check",
        "description": (
            "Checks the status of key systems: ildormire.com website (HTTP), "
            "Docker containers on the Mac host, disk space, and memory usage. "
            "Returns a structured JSON report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "check_type": {
                    "type": "string",
                    "enum": ["all", "website", "docker", "disk", "memory"],
                    "description": "Which check to perform. Default: all.",
                }
            },
            "required": [],
        },
    },
}


async def health_check(check_type: str = "all") -> dict:
    """Run health checks and return structured report."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
        "overall_status": "healthy",
    }

    checks_to_run = []
    if check_type == "all":
        checks_to_run = ["website", "docker", "disk", "memory"]
    else:
        checks_to_run = [check_type]

    for check in checks_to_run:
        if check == "website":
            result = await _http_get(SITE_URL)
            report["checks"]["website"] = {
                "url": SITE_URL,
                "status_code": result.get("status", 0),
                "reachable": result.get("ok", False),
                "error": result.get("error"),
            }
            if not result.get("ok"):
                report["overall_status"] = "degraded"

        elif check == "docker":
            result = await _host_bridge_command("docker ps --format '{{.Names}}|{{.Status}}'")
            containers = []
            if result.get("success") and result.get("output"):
                for line in result["output"].strip().split("\n"):
                    if "|" in line:
                        name, status = line.split("|", 1)
                        containers.append({"name": name, "status": status})
            report["checks"]["docker"] = {
                "containers": containers,
                "count": len(containers),
                "bridge_reachable": result.get("success", False),
            }
            if not result.get("success"):
                report["overall_status"] = "degraded"

        elif check == "disk":
            result = await _host_bridge_command("df -h / | tail -1 | awk '{print $5}'")
            usage = "unknown"
            if result.get("success") and result.get("output"):
                usage = result["output"].strip()
            report["checks"]["disk"] = {
                "root_usage": usage,
                "warning": usage.replace("%", "").isdigit() and int(usage.replace("%", "")) > 85,
            }
            if report["checks"]["disk"].get("warning"):
                report["overall_status"] = "warning"

        elif check == "memory":
            result = await _host_bridge_command(
                "vm_stat | head -10"
            )
            report["checks"]["memory"] = {
                "raw": result.get("output", "unavailable")[:300],
                "bridge_reachable": result.get("success", False),
            }

    # Log the check
    _append_health_log(report)
    return report


# ============================================================
# AUTO-DEBUG TOOL
# ============================================================

AUTO_DEBUG_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "auto_debug",
        "description": (
            "Attempts to diagnose and fix a detected issue autonomously. "
            "Can restart Docker containers, clear caches, restart services. "
            "Uses the host_bridge for Mac commands."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "issue": {
                    "type": "string",
                    "description": "Description of the issue to diagnose/fix.",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "restart_container",
                        "restart_all_containers",
                        "clear_docker_cache",
                        "check_logs",
                        "auto",
                    ],
                    "description": "Specific action to take, or 'auto' to let the system decide.",
                },
                "container_name": {
                    "type": "string",
                    "description": "Name of the container to act on (if applicable).",
                },
            },
            "required": ["issue"],
        },
    },
}


async def auto_debug(issue: str, action: str = "auto", container_name: str = "") -> dict:
    """Attempt to diagnose and fix an issue."""
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issue": issue,
        "action_taken": action,
        "steps": [],
        "resolved": False,
    }

    try:
        if action == "auto":
            # Decide based on issue keywords
            issue_lower = issue.lower()
            if "website" in issue_lower or "ildormire" in issue_lower or "site down" in issue_lower:
                action = "restart_container"
                container_name = container_name or "dormire-shop"
            elif "container" in issue_lower:
                action = "restart_container"
            elif "disk" in issue_lower or "space" in issue_lower:
                action = "clear_docker_cache"
            else:
                action = "check_logs"

        if action == "restart_container":
            target = container_name or "dormire-shop"
            result["steps"].append(f"Restarting container: {target}")
            cmd_result = await _host_bridge_command(f"docker restart {target}")
            result["steps"].append(f"Result: {cmd_result}")
            # Verify
            await asyncio.sleep(5)
            verify = await _host_bridge_command(f"docker ps --filter name={target} --format '{{{{.Status}}}}'")
            if verify.get("success") and "Up" in verify.get("output", ""):
                result["resolved"] = True
                result["steps"].append("Container is back up.")
            else:
                result["steps"].append("Container may not have restarted correctly.")

        elif action == "restart_all_containers":
            result["steps"].append("Restarting all containers via docker-compose")
            cmd_result = await _host_bridge_command(
                "cd ~/nik29-coordinator && docker compose restart"
            )
            result["steps"].append(f"Result: {cmd_result}")
            await asyncio.sleep(10)
            result["resolved"] = True

        elif action == "clear_docker_cache":
            result["steps"].append("Pruning Docker system (unused images, containers, volumes)")
            cmd_result = await _host_bridge_command("docker system prune -f")
            result["steps"].append(f"Result: {cmd_result}")
            result["resolved"] = True

        elif action == "check_logs":
            target = container_name or "nik29-coordinator"
            result["steps"].append(f"Fetching last 50 log lines from: {target}")
            cmd_result = await _host_bridge_command(f"docker logs --tail 50 {target}")
            result["steps"].append(f"Logs: {cmd_result.get('output', 'N/A')[:1000]}")
            result["resolved"] = False  # Logs are informational

    except Exception as e:
        result["steps"].append(f"Error during auto-debug: {str(e)}")

    # Log the action
    _append_health_log({"type": "auto_debug", **result})
    return result


# ============================================================
# ALERT TOOL
# ============================================================

ALERT_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "send_alert",
        "description": (
            "Sends an alert message to Nicola via Telegram. "
            "Use for important notifications that need human attention."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The alert message to send.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Severity level of the alert.",
                },
            },
            "required": ["message"],
        },
    },
}


async def send_alert(message: str, severity: str = "info") -> dict:
    """Send a Telegram alert to Nicola."""
    emoji_map = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }
    emoji = emoji_map.get(severity, "ℹ️")
    formatted = f"{emoji} <b>nik29 Alert [{severity.upper()}]</b>\n\n{message}"

    result = await _send_telegram(formatted)

    log_entry = {
        "type": "alert",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "message": message,
        "telegram_result": result,
    }
    _append_health_log(log_entry)

    return {
        "sent": result.get("ok", False),
        "severity": severity,
        "error": result.get("error") if not result.get("ok") else None,
    }


# ============================================================
# TOOL REGISTRY (for coordinator integration)
# ============================================================

MONITORING_TOOLS = [HEALTH_CHECK_TOOL_DEF, AUTO_DEBUG_TOOL_DEF, ALERT_TOOL_DEF]

MONITORING_TOOL_HANDLERS = {
    "health_check": health_check,
    "auto_debug": auto_debug,
    "send_alert": send_alert,
}
