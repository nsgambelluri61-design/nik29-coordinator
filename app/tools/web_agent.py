"""
web_agent.py — Autonomous Multi-Step Navigation Loop
=====================================================
A tool that takes a high-level goal and autonomously navigates the web
using existing browser_tools (browser_navigate, browser_click, browser_fill,
browser_screenshot, browser_evaluate) until it finds the answer.

Part of the nik29-coordinator advanced browser upgrade package.
"""

import json
import base64
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger("web_agent")

# Tool definition for OpenAI function calling format
WEB_AGENT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_agent",
        "description": (
            "Autonomous web navigation agent. Takes a goal (e.g., 'find the price of "
            "memory foam mattresses on ildormire.com') and autonomously navigates: opens "
            "pages, reads content, decides what to click or where to go, navigates again, "
            "until it finds the answer or reaches max_steps. Returns a structured summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The navigation goal to achieve (what information to find or action to perform)"
                },
                "start_url": {
                    "type": "string",
                    "description": "Optional starting URL. If not provided, the agent will decide where to start."
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum navigation steps before stopping (default: 10)",
                    "default": 10
                }
            },
            "required": ["goal"]
        }
    }
}

# Internal tools the agent can use during navigation
NAVIGATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate to a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click on an element identified by CSS selector",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the element to click"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill a form field with text",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input field"},
                    "text": {"type": "string", "description": "Text to fill in"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the current page to visually understand the layout",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": "Execute JavaScript on the page and return the result",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "JavaScript expression to evaluate"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_current_screenshot",
            "description": "Analyze the current screenshot visually using GPT-4.1 vision to understand page layout, buttons, text, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What to look for in the screenshot"}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_result",
            "description": "Report the final result when the goal has been achieved",
            "parameters": {
                "type": "object",
                "properties": {
                    "found": {"type": "boolean", "description": "Whether the goal was achieved"},
                    "summary": {"type": "string", "description": "Summary of what was found"},
                    "data": {"type": "string", "description": "The specific data/answer found (if any)"}
                },
                "required": ["found", "summary"]
            }
        }
    }
]


class WebAgent:
    """Autonomous web navigation agent that uses browser tools to achieve a goal."""

    def __init__(
        self,
        browser_tools: dict,
        screenshot_analyzer_fn=None,
        model: str = "gpt-4.1",
        client: Optional[AsyncOpenAI] = None,
    ):
        """
        Args:
            browser_tools: Dict mapping tool names to async callables:
                {
                    "browser_navigate": async fn(url) -> result,
                    "browser_click": async fn(selector) -> result,
                    "browser_fill": async fn(selector, text) -> result,
                    "browser_screenshot": async fn() -> base64_image,
                    "browser_evaluate": async fn(expression) -> result,
                }
            screenshot_analyzer_fn: Optional async fn(base64_image, question) -> str
            model: Model to use for the agent's reasoning (default: gpt-4.1 for complex navigation)
            client: AsyncOpenAI client instance
        """
        self.browser_tools = browser_tools
        self.screenshot_analyzer_fn = screenshot_analyzer_fn
        self.model = model
        self.client = client or AsyncOpenAI()

    async def run(self, goal: str, start_url: Optional[str] = None, max_steps: int = 10) -> dict:
        """
        Execute the autonomous navigation loop.

        Returns:
            dict with keys: success, summary, data, steps_taken, history
        """
        logger.info(f"WebAgent starting — goal: {goal}, max_steps: {max_steps}")

        system_prompt = (
            "You are an autonomous web navigation agent. Your goal is to navigate web pages "
            "to find specific information or complete a task.\n\n"
            f"YOUR GOAL: {goal}\n\n"
            "INSTRUCTIONS:\n"
            "1. Use browser_navigate to go to URLs\n"
            "2. Use browser_evaluate to read page content (document.title, innerText, links, etc.)\n"
            "3. Use browser_click to interact with elements\n"
            "4. Use browser_fill to fill form fields\n"
            "5. Use browser_screenshot + analyze_current_screenshot when you need to visually understand the page\n"
            "6. When you have found the answer, call report_result with found=true\n"
            "7. If you cannot find the answer after trying, call report_result with found=false\n\n"
            "STRATEGY:\n"
            "- First navigate to the relevant page\n"
            "- Use browser_evaluate with document.body.innerText or specific selectors to read content\n"
            "- Look for links, buttons, or navigation elements to explore\n"
            "- Be systematic: don't revisit pages you've already checked\n"
            "- If a page is complex, take a screenshot and analyze it visually\n"
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Initial user message
        initial_msg = f"Please achieve this goal: {goal}"
        if start_url:
            initial_msg += f"\n\nStart by navigating to: {start_url}"
        else:
            initial_msg += "\n\nDecide where to start navigating."

        messages.append({"role": "user", "content": initial_msg})

        history = []
        steps_taken = 0
        result = {"success": False, "summary": "Max steps reached without finding answer", "data": None, "steps_taken": 0, "history": []}

        while steps_taken < max_steps:
            steps_taken += 1
            logger.info(f"WebAgent step {steps_taken}/{max_steps}")

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=NAVIGATION_TOOLS,
                    tool_choice="auto",
                    temperature=0.2,
                )
            except Exception as e:
                logger.error(f"WebAgent LLM call failed: {e}")
                result["summary"] = f"LLM call failed: {str(e)}"
                break

            choice = response.choices[0]
            assistant_message = choice.message

            # Add assistant message to conversation
            messages.append(assistant_message.model_dump())

            # If no tool calls, the agent is done thinking
            if not assistant_message.tool_calls:
                if assistant_message.content:
                    history.append({"step": steps_taken, "action": "thinking", "detail": assistant_message.content})
                continue

            # Process each tool call
            for tool_call in assistant_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"  Tool call: {fn_name}({fn_args})")
                history.append({"step": steps_taken, "action": fn_name, "args": fn_args})

                # Handle report_result — agent is done
                if fn_name == "report_result":
                    result["success"] = fn_args.get("found", False)
                    result["summary"] = fn_args.get("summary", "")
                    result["data"] = fn_args.get("data")
                    result["steps_taken"] = steps_taken
                    result["history"] = history
                    logger.info(f"WebAgent finished — success: {result['success']}")
                    return result

                # Execute the browser tool
                tool_result = await self._execute_tool(fn_name, fn_args)

                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(tool_result) if tool_result is not None else "OK"
                })

        result["steps_taken"] = steps_taken
        result["history"] = history
        return result

    async def _execute_tool(self, fn_name: str, fn_args: dict) -> str:
        """Execute a browser tool and return the result as a string."""
        try:
            if fn_name == "browser_navigate":
                res = await self.browser_tools["browser_navigate"](fn_args["url"])
                return f"Navigated to {fn_args['url']}. Result: {res}"

            elif fn_name == "browser_click":
                res = await self.browser_tools["browser_click"](fn_args["selector"])
                return f"Clicked {fn_args['selector']}. Result: {res}"

            elif fn_name == "browser_fill":
                res = await self.browser_tools["browser_fill"](fn_args["selector"], fn_args["text"])
                return f"Filled {fn_args['selector']} with '{fn_args['text']}'. Result: {res}"

            elif fn_name == "browser_screenshot":
                res = await self.browser_tools["browser_screenshot"]()
                # res should be base64 image data
                return "Screenshot taken successfully. Use analyze_current_screenshot to understand what's on the page."

            elif fn_name == "browser_evaluate":
                res = await self.browser_tools["browser_evaluate"](fn_args["expression"])
                # Truncate very long results
                res_str = str(res)
                if len(res_str) > 4000:
                    res_str = res_str[:4000] + "... [truncated]"
                return f"JavaScript result: {res_str}"

            elif fn_name == "analyze_current_screenshot":
                if self.screenshot_analyzer_fn:
                    # Take a fresh screenshot first
                    screenshot_b64 = await self.browser_tools["browser_screenshot"]()
                    analysis = await self.screenshot_analyzer_fn(screenshot_b64, fn_args.get("question", "Describe what you see"))
                    return f"Visual analysis: {analysis}"
                else:
                    return "Screenshot analysis not available. Use browser_evaluate to read page content instead."

            else:
                return f"Unknown tool: {fn_name}"

        except Exception as e:
            logger.error(f"Tool execution error ({fn_name}): {e}")
            return f"Error executing {fn_name}: {str(e)}"


async def execute_web_agent(
    goal: str,
    start_url: Optional[str] = None,
    max_steps: int = 10,
    browser_tools: dict = None,
    screenshot_analyzer_fn=None,
    model: str = "gpt-4.1",
    client: Optional[AsyncOpenAI] = None,
) -> dict:
    """
    Convenience function to run the web agent.
    Called from coordinator.py dispatch.

    Args:
        goal: What to find or accomplish
        start_url: Optional starting URL
        max_steps: Max navigation steps (default 10)
        browser_tools: Dict of browser tool async callables
        screenshot_analyzer_fn: Optional screenshot analysis function
        model: Model to use for reasoning
        client: AsyncOpenAI client

    Returns:
        dict with: success, summary, data, steps_taken, history
    """
    if browser_tools is None:
        raise ValueError("browser_tools dict is required")

    agent = WebAgent(
        browser_tools=browser_tools,
        screenshot_analyzer_fn=screenshot_analyzer_fn,
        model=model,
        client=client,
    )

    return await agent.run(goal=goal, start_url=start_url, max_steps=max_steps)
