"""
model_router.py — Intelligent Model Routing (mini vs 4.1)
==========================================================
Routes requests to the appropriate model based on complexity:
- gpt-4.1-mini: default for simple tasks
- gpt-4.1: for complex tasks (web_agent, screenshot analysis, deep analysis, code gen)

Part of the nik29-coordinator advanced browser upgrade package.
"""

import os
import re
import logging
from typing import Optional

logger = logging.getLogger("model_router")

# Environment variable names
ENV_MODEL_DEFAULT = "OPENAI_MODEL_DEFAULT"  # Usually gpt-4.1-mini
ENV_MODEL_LARGE = "OPENAI_MODEL_LARGE"      # Usually gpt-4.1
ENV_MODEL_FORCE = "OPENAI_MODEL_FORCE"      # Force a specific model (overrides routing)

# Default model names
DEFAULT_MODEL_MINI = "gpt-4.1-mini"
DEFAULT_MODEL_LARGE = "gpt-4.1"

# Keywords/patterns that trigger routing to the large model
COMPLEX_TASK_PATTERNS = [
    # Tool-based triggers
    r"\bweb_agent\b",
    r"\banalyze_screenshot\b",
    r"\bscreenshot\b.*\banalys",
    r"\bautonomous\b.*\bnavig",
    # Explicit user requests
    r"\bdeep\s+analysis\b",
    r"\banalisi\s+approfondita\b",
    r"\banalizza\s+in\s+dettaglio\b",
    r"\bragiona\s+passo\s+passo\b",
    r"\bstep[\s-]by[\s-]step\b",
    r"\bthink\s+carefully\b",
    r"\breason\s+through\b",
    # Complex task indicators
    r"\brefactor\b",
    r"\barchitect",
    r"\bdesign\s+pattern\b",
    r"\bmulti[\s-]step\b",
    r"\bcomplex\b.*\bcode\b",
    r"\bwrite\s+a\s+(full|complete|entire)\b",
    r"\bgenerate\s+(a\s+)?(full|complete|entire)\b",
    r"\bdebug\b.*\b(complex|difficult|tricky)\b",
    r"\bsecurity\s+audit\b",
    r"\bperformance\s+optim",
    # Long code generation
    r"\bimplementa\b",
    r"\bimplements?\b.*\b(class|module|system)\b",
    r"\bcrea\s+(un|una)\s+(sistema|modulo|classe|applicazione)\b",
]

# Compiled patterns for performance
_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in COMPLEX_TASK_PATTERNS]

# Tool names that always require the large model
LARGE_MODEL_TOOLS = {"web_agent", "analyze_screenshot"}


class ModelRouter:
    """Routes requests to the appropriate model based on complexity analysis."""

    def __init__(
        self,
        model_default: Optional[str] = None,
        model_large: Optional[str] = None,
        model_force: Optional[str] = None,
    ):
        """
        Args:
            model_default: Default (small/fast) model name
            model_large: Large (powerful) model name for complex tasks
            model_force: If set, always use this model (overrides all routing)
        """
        self.model_default = model_default or os.getenv(ENV_MODEL_DEFAULT, DEFAULT_MODEL_MINI)
        self.model_large = model_large or os.getenv(ENV_MODEL_LARGE, DEFAULT_MODEL_LARGE)
        self.model_force = model_force or os.getenv(ENV_MODEL_FORCE, "")

    def route(
        self,
        user_message: str = "",
        tool_calls: Optional[list] = None,
        message_history: Optional[list] = None,
        force_model: Optional[str] = None,
    ) -> str:
        """
        Determine which model to use for this request.

        Args:
            user_message: The current user message text
            tool_calls: List of tool names being invoked (if any)
            message_history: Full conversation history (for context analysis)
            force_model: Explicit override for this single request

        Returns:
            Model name string (e.g., "gpt-4.1" or "gpt-4.1-mini")
        """
        # Priority 1: Explicit per-request override
        if force_model:
            logger.info(f"Model forced per-request: {force_model}")
            return force_model

        # Priority 2: Global force override (env/config)
        if self.model_force:
            logger.info(f"Model forced globally: {self.model_force}")
            return self.model_force

        # Priority 3: Tool-based routing
        if tool_calls:
            for tool_name in tool_calls:
                if tool_name in LARGE_MODEL_TOOLS:
                    logger.info(f"Routing to large model — tool trigger: {tool_name}")
                    return self.model_large

        # Priority 4: Pattern-based routing on user message
        if user_message:
            for pattern in _compiled_patterns:
                if pattern.search(user_message):
                    logger.info(f"Routing to large model — pattern match: {pattern.pattern}")
                    return self.model_large

        # Priority 5: Message length heuristic (very long messages often = complex tasks)
        if user_message and len(user_message) > 2000:
            logger.info("Routing to large model — long message heuristic")
            return self.model_large

        # Priority 6: Conversation depth heuristic
        if message_history and len(message_history) > 20:
            logger.info("Routing to large model — deep conversation heuristic")
            return self.model_large

        # Default: use the fast model
        logger.debug(f"Routing to default model: {self.model_default}")
        return self.model_default

    def get_config(self) -> dict:
        """Return current routing configuration."""
        return {
            "model_default": self.model_default,
            "model_large": self.model_large,
            "model_force": self.model_force or None,
            "complex_patterns_count": len(COMPLEX_TASK_PATTERNS),
            "large_model_tools": list(LARGE_MODEL_TOOLS),
        }


# Module-level singleton
_router: Optional[ModelRouter] = None


def get_router(
    model_default: Optional[str] = None,
    model_large: Optional[str] = None,
    model_force: Optional[str] = None,
) -> ModelRouter:
    """Get or create the singleton router instance."""
    global _router
    if _router is None:
        _router = ModelRouter(
            model_default=model_default,
            model_large=model_large,
            model_force=model_force,
        )
    return _router


def route_model(
    user_message: str = "",
    tool_calls: Optional[list] = None,
    message_history: Optional[list] = None,
    force_model: Optional[str] = None,
) -> str:
    """
    Convenience function for routing.
    Called from coordinator.py chat endpoint.

    Args:
        user_message: Current user message
        tool_calls: Tool names being called
        message_history: Conversation history
        force_model: Per-request model override

    Returns:
        Model name to use
    """
    router = get_router()
    return router.route(
        user_message=user_message,
        tool_calls=tool_calls,
        message_history=message_history,
        force_model=force_model,
    )
