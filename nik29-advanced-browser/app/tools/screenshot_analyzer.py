"""
screenshot_analyzer.py — Visual Screenshot Analysis with GPT-4.1 Vision
========================================================================
A tool that takes a screenshot (base64) and sends it to GPT-4.1 with vision
capabilities to describe what it sees. Can answer questions about visual layout,
colors, buttons, text positioning, and page structure.

Part of the nik29-coordinator advanced browser upgrade package.
"""

import base64
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger("screenshot_analyzer")

# Tool definition for OpenAI function calling format
ANALYZE_SCREENSHOT_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "analyze_screenshot",
        "description": (
            "Analyze a browser screenshot visually using GPT-4.1 vision. "
            "Can describe page layout, identify buttons, read text, analyze colors, "
            "find navigation elements, and answer questions about what's visible on the page. "
            "Use this when you need to visually understand a web page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": (
                        "What to analyze or look for in the screenshot. "
                        "Examples: 'What products are shown?', 'Where is the search bar?', "
                        "'What is the main heading?', 'Describe the page layout'"
                    )
                },
                "screenshot_base64": {
                    "type": "string",
                    "description": (
                        "Base64-encoded screenshot image. If not provided, "
                        "a fresh screenshot will be taken automatically."
                    )
                }
            },
            "required": ["question"]
        }
    }
}


class ScreenshotAnalyzer:
    """Analyzes screenshots using GPT-4.1 vision capabilities."""

    def __init__(
        self,
        model: str = "gpt-4.1",
        client: Optional[AsyncOpenAI] = None,
        max_tokens: int = 1024,
    ):
        """
        Args:
            model: Vision-capable model to use (must support image inputs)
            client: AsyncOpenAI client instance
            max_tokens: Max tokens for the analysis response
        """
        self.model = model
        self.client = client or AsyncOpenAI()
        self.max_tokens = max_tokens

    async def analyze(
        self,
        screenshot_base64: str,
        question: str,
        context: Optional[str] = None,
    ) -> str:
        """
        Analyze a screenshot with a specific question.

        Args:
            screenshot_base64: Base64-encoded PNG/JPEG image
            question: What to look for or analyze
            context: Optional additional context about what page this is

        Returns:
            String description/analysis of the screenshot
        """
        logger.info(f"Analyzing screenshot — question: {question[:100]}")

        system_prompt = (
            "You are a visual web page analyzer. You receive screenshots of web pages "
            "and answer questions about what you see. Be precise and specific:\n"
            "- Identify text content, headings, buttons, links, forms\n"
            "- Describe layout structure (header, sidebar, main content, footer)\n"
            "- Note colors, branding, visual hierarchy\n"
            "- Identify interactive elements (buttons, inputs, dropdowns)\n"
            "- Read and report any visible text accurately\n"
            "- If asked about specific elements, describe their position and appearance\n"
            "Keep your analysis concise but thorough."
        )

        # Build the user message with image
        user_content = []

        if context:
            user_content.append({
                "type": "text",
                "text": f"Context: {context}\n\nQuestion: {question}"
            })
        else:
            user_content.append({
                "type": "text",
                "text": question
            })

        # Add the image
        # Detect if it's already a data URL or raw base64
        if screenshot_base64.startswith("data:"):
            image_url = screenshot_base64
        else:
            # Assume PNG if no prefix
            image_url = f"data:image/png;base64,{screenshot_base64}"

        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": image_url,
                "detail": "high"
            }
        })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.2,
            )

            analysis = response.choices[0].message.content
            logger.info(f"Screenshot analysis complete ({len(analysis)} chars)")
            return analysis

        except Exception as e:
            error_msg = f"Screenshot analysis failed: {str(e)}"
            logger.error(error_msg)
            return error_msg


# Module-level instance (lazy initialization)
_analyzer: Optional[ScreenshotAnalyzer] = None


def get_analyzer(model: str = "gpt-4.1", client: Optional[AsyncOpenAI] = None) -> ScreenshotAnalyzer:
    """Get or create the singleton analyzer instance."""
    global _analyzer
    if _analyzer is None or client is not None:
        _analyzer = ScreenshotAnalyzer(model=model, client=client)
    return _analyzer


async def execute_analyze_screenshot(
    question: str,
    screenshot_base64: Optional[str] = None,
    browser_screenshot_fn=None,
    context: Optional[str] = None,
    model: str = "gpt-4.1",
    client: Optional[AsyncOpenAI] = None,
) -> dict:
    """
    Convenience function to analyze a screenshot.
    Called from coordinator.py dispatch.

    Args:
        question: What to analyze in the screenshot
        screenshot_base64: Base64 image data (if None, takes a fresh screenshot)
        browser_screenshot_fn: Async function to take a screenshot (returns base64)
        context: Optional context about the page
        model: Vision model to use
        client: AsyncOpenAI client

    Returns:
        dict with: success, analysis, error
    """
    try:
        # If no screenshot provided, take one
        if screenshot_base64 is None:
            if browser_screenshot_fn is None:
                return {
                    "success": False,
                    "analysis": None,
                    "error": "No screenshot provided and no browser_screenshot function available"
                }
            screenshot_base64 = await browser_screenshot_fn()
            if not screenshot_base64:
                return {
                    "success": False,
                    "analysis": None,
                    "error": "Failed to take screenshot"
                }

        analyzer = get_analyzer(model=model, client=client)
        analysis = await analyzer.analyze(
            screenshot_base64=screenshot_base64,
            question=question,
            context=context,
        )

        return {
            "success": True,
            "analysis": analysis,
            "error": None
        }

    except Exception as e:
        logger.error(f"execute_analyze_screenshot error: {e}")
        return {
            "success": False,
            "analysis": None,
            "error": str(e)
        }
