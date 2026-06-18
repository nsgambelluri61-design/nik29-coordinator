"""
Level 3 Autonomy — Background Monitor
Runs periodic health checks, attempts auto-fix, and alerts on failure.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.tools.monitoring_tools import (
    health_check,
    auto_debug,
    send_alert,
    _append_health_log,
)

logger = logging.getLogger("nik29.monitor")

# Monitor interval in seconds (5 minutes)
MONITOR_INTERVAL = 300

# Track consecutive failures for escalation
_failure_count: dict = {}


async def _run_health_cycle():
    """Single health check cycle with auto-fix and alerting."""
    try:
        report = await health_check(check_type="all")
        status = report.get("overall_status", "unknown")

        if status == "healthy":
            # Reset failure counters
            _failure_count.clear()
            logger.info("Health check passed — all systems healthy.")
            return

        # Something is wrong — identify issues
        issues = []
        checks = report.get("checks", {})

        # Website check
        if "website" in checks and not checks["website"].get("reachable"):
            issues.append("website_down")

        # Docker check
        if "docker" in checks and not checks["docker"].get("bridge_reachable"):
            issues.append("host_bridge_unreachable")

        # Disk check
        if "disk" in checks and checks["disk"].get("warning"):
            issues.append("disk_space_low")

        for issue in issues:
            _failure_count[issue] = _failure_count.get(issue, 0) + 1
            count = _failure_count[issue]

            if count == 1:
                # First failure: try auto-fix
                logger.warning(f"Issue detected: {issue} — attempting auto-fix...")
                fix_result = await auto_debug(issue=issue, action="auto")
                if fix_result.get("resolved"):
                    logger.info(f"Auto-fix resolved: {issue}")
                    _failure_count[issue] = 0
                else:
                    logger.warning(f"Auto-fix did not resolve: {issue}")

            elif count == 2:
                # Second consecutive failure: alert Nicola
                logger.error(f"Persistent issue: {issue} — sending alert.")
                await send_alert(
                    message=(
                        f"Problema rilevato: <b>{issue}</b>\n"
                        f"Il sistema ha provato a risolvere automaticamente ma non ci è riuscito.\n"
                        f"Potrebbe servire un intervento manuale."
                    ),
                    severity="warning",
                )

            elif count >= 3:
                # Critical — repeated failures
                if count % 5 == 0:  # Don't spam, alert every 5th failure
                    await send_alert(
                        message=(
                            f"🔴 Problema persistente: <b>{issue}</b>\n"
                            f"Fallimenti consecutivi: {count}\n"
                            f"Serve intervento urgente!"
                        ),
                        severity="critical",
                    )

    except Exception as e:
        logger.error(f"Monitor cycle error: {e}", exc_info=True)
        _append_health_log({
            "type": "monitor_error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })


async def start_monitoring():
    """Start the background monitoring loop. Call this on app startup."""
    logger.info(f"Background monitor started (interval: {MONITOR_INTERVAL}s)")
    # Wait a bit before first check to let the app fully start
    await asyncio.sleep(15)

    while True:
        try:
            await _run_health_cycle()
        except Exception as e:
            logger.error(f"Unhandled monitor error: {e}", exc_info=True)
        await asyncio.sleep(MONITOR_INTERVAL)


def create_monitor_task() -> asyncio.Task:
    """Create and return the monitoring background task."""
    return asyncio.create_task(start_monitoring())
