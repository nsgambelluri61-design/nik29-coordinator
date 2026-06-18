"""
=============================================================================
PATCH INSTRUCTIONS FOR app/coordinator.py
=============================================================================

This file shows EXACTLY what to add to your existing coordinator.py.
DO NOT replace the file — add these sections in the right places.

=============================================================================
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Add these imports at the TOP of coordinator.py (after existing imports)
# ─────────────────────────────────────────────────────────────────────────────

IMPORTS_TO_ADD = """
# === Level 3 Autonomy Imports ===
from app.tools.monitoring_tools import MONITORING_TOOLS, MONITORING_TOOL_HANDLERS
from app.tools.scheduler_tools import SCHEDULER_TOOLS, SCHEDULER_TOOL_HANDLERS
from app.tools.web_tools import WEB_TOOLS, WEB_TOOL_HANDLERS
from app.monitoring.monitor import create_monitor_task
from app.scheduler.scheduler import start_scheduler
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Register tools in your tool definitions list
# Find where you define your OpenAI tools list (e.g., TOOLS = [...])
# and ADD these after the existing tools:
# ─────────────────────────────────────────────────────────────────────────────

TOOLS_REGISTRATION = """
# === Level 3 Tools Registration ===
# Add to your existing TOOLS list:
TOOLS.extend(MONITORING_TOOLS)
TOOLS.extend(SCHEDULER_TOOLS)
TOOLS.extend(WEB_TOOLS)
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Register tool handlers in your handler dispatch
# Find where you dispatch tool calls (e.g., TOOL_HANDLERS = {...})
# and ADD these:
# ─────────────────────────────────────────────────────────────────────────────

HANDLERS_REGISTRATION = """
# === Level 3 Tool Handlers ===
# Add to your existing TOOL_HANDLERS dict:
TOOL_HANDLERS.update(MONITORING_TOOL_HANDLERS)
TOOL_HANDLERS.update(SCHEDULER_TOOL_HANDLERS)
TOOL_HANDLERS.update(WEB_TOOL_HANDLERS)
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: Start background services on app startup
# Find your FastAPI app startup (e.g., @app.on_event("startup") or lifespan)
# and ADD these lines inside the startup function:
# ─────────────────────────────────────────────────────────────────────────────

STARTUP_CODE = """
# === Level 3 Background Services ===
# Add inside your startup function/lifespan:

# Start the background health monitor
monitor_task = create_monitor_task()

# Start the task scheduler
await start_scheduler()
"""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: If your coordinator uses a lifespan context manager, it looks like:
# ─────────────────────────────────────────────────────────────────────────────

LIFESPAN_EXAMPLE = """
# Example with FastAPI lifespan (modern approach):

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    monitor_task = create_monitor_task()
    await start_scheduler()
    logger.info("Level 3 autonomy services started.")
    yield
    # Shutdown
    monitor_task.cancel()
    logger.info("Level 3 autonomy services stopped.")

app = FastAPI(lifespan=lifespan)
"""
