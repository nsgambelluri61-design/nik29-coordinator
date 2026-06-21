import os
import asyncio
import base64
import json
import traceback
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import atexit

# Global state to keep the browser running
_playwright_instance = None
_browser = None
_page = None

TOOL_DEFINITION = {
    "name": "browser_interact",
    "description": "Navigate and interact with web pages using a real browser. Can open URLs, click elements, fill forms, take screenshots, extract text, and visually describe pages using AI vision.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "click", "fill", "screenshot", "extract", "describe", "scroll", "wait", "back", "close"],
                "description": "The browser action to perform"
            },
            "url": {
                "type": "string",
                "description": "URL to open (required for 'open' action)"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector or text to identify an element (for click, fill, wait)"
            },
            "text": {
                "type": "string", 
                "description": "Text to type (for fill) or scroll direction (up/down)"
            },
            "description": {
                "type": "string",
                "description": "What to look for when describing a page visually (for describe action)"
            }
        },
        "required": ["action"]
    }
}

async def _ensure_browser():
    global _playwright_instance, _browser, _page
    if _page is not None and not _page.is_closed():
        return _page

    if _playwright_instance is None:
        _playwright_instance = await async_playwright().start()
    
    if _browser is None:
        _browser = await _playwright_instance.chromium.launch(headless=True)
    
    _page = await _browser.new_page(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return _page

async def _close_browser():
    global _playwright_instance, _browser, _page
    if _page:
        try:
            await _page.close()
        except Exception:
            pass
        _page = None
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright_instance:
        try:
            await _playwright_instance.stop()
        except Exception:
            pass
        _playwright_instance = None

# Ensure browser is closed on exit
atexit.register(lambda: asyncio.run(_close_browser()) if asyncio.get_event_loop().is_running() else None)

async def _find_element(page, selector):
    """Helper to find element by CSS selector or text content"""
    if not selector:
        return None
        
    # Check if it looks like a CSS selector
    is_css = any(selector.startswith(c) for c in ['.', '#', '[', ':']) or ' ' in selector or '>' in selector
    
    if is_css:
        try:
            # Quick check if selector is valid
            element = page.locator(selector).first
            count = await element.count()
            if count > 0:
                return element
        except Exception:
            pass
            
    # Try by text content
    text_locator = page.get_by_text(selector, exact=False).first
    count = await text_locator.count()
    if count > 0:
        return text_locator
        
    # Fallback to CSS if it was just a tag name (e.g. 'button')
    if not is_css:
        element = page.locator(selector).first
        count = await element.count()
        if count > 0:
            return element
            
    return None

async def _describe_with_gpt4o(image_path, description_prompt=None):
    """Call OpenAI GPT-4o vision to describe the image"""
    try:
        import openai
    except ImportError:
        return "Error: openai package is not installed. Please install it to use the 'describe' action."

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "Error: OPENAI_API_KEY environment variable is not set."

    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        return f"Error reading screenshot: {str(e)}"

    prompt = description_prompt if description_prompt else "Describe what you see on this webpage."
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error calling OpenAI API: {str(e)}"

async def browser_interact(action, url=None, selector=None, text=None, description=None):
    try:
        if action == "close":
            await _close_browser()
            return {"status": "success", "message": "Browser closed"}
            
        page = await _ensure_browser()
        
        if action == "open":
            if not url:
                return {"status": "error", "message": "URL is required for 'open' action"}
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await page.goto(url, wait_until="networkidle", timeout=30000)
            title = await page.title()
            current_url = page.url
            return {"status": "success", "title": title, "url": current_url}
            
        elif action == "click":
            if not selector:
                return {"status": "error", "message": "Selector is required for 'click' action"}
            element = await _find_element(page, selector)
            if not element:
                return {"status": "error", "message": f"Element not found: {selector}"}
            await element.click(timeout=10000)
            # Wait a bit for potential navigation or DOM updates
            await page.wait_for_timeout(1000)
            return {"status": "success", "message": f"Clicked on {selector}"}
            
        elif action == "fill":
            if not selector or text is None:
                return {"status": "error", "message": "Selector and text are required for 'fill' action"}
            element = await _find_element(page, selector)
            if not element:
                return {"status": "error", "message": f"Element not found: {selector}"}
            await element.fill(text, timeout=10000)
            return {"status": "success", "message": f"Filled {selector} with text"}
            
        elif action == "screenshot":
            import time
            timestamp = int(time.time())
            path = f"/tmp/screenshot_{timestamp}.png"
            await page.screenshot(path=path, full_page=True)
            return {"status": "success", "path": path}
            
        elif action == "extract":
            # Extract visible text from body
            content = await page.evaluate("document.body.innerText")
            return {"status": "success", "text": content}
            
        elif action == "describe":
            import time
            timestamp = int(time.time())
            path = f"/tmp/screenshot_{timestamp}.png"
            await page.screenshot(path=path, full_page=False) # Just viewport for description
            desc = await _describe_with_gpt4o(path, description)
            return {"status": "success", "description": desc, "screenshot_path": path}
            
        elif action == "scroll":
            direction = text.lower() if text else "down"
            if direction == "down":
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
            elif direction == "up":
                await page.evaluate("window.scrollBy(0, -window.innerHeight)")
            else:
                return {"status": "error", "message": "Text must be 'up' or 'down' for scroll action"}
            await page.wait_for_timeout(500)
            return {"status": "success", "message": f"Scrolled {direction}"}
            
        elif action == "wait":
            if not selector:
                return {"status": "error", "message": "Selector is required for 'wait' action"}
            try:
                # First try as exact text, then as CSS
                if any(selector.startswith(c) for c in ['.', '#', '[', ':']) or ' ' in selector or '>' in selector:
                    await page.wait_for_selector(selector, timeout=10000)
                else:
                    await page.get_by_text(selector, exact=False).first.wait_for(timeout=10000)
                return {"status": "success", "message": f"Element {selector} appeared"}
            except PlaywrightTimeoutError:
                return {"status": "error", "message": f"Timeout waiting for {selector}"}
                
        elif action == "back":
            await page.go_back(wait_until="networkidle", timeout=30000)
            return {"status": "success", "url": page.url}
            
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}
            
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return {"status": "error", "message": error_msg, "traceback": traceback.format_exc()}
