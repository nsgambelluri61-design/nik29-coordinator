import asyncio
import logging
import json
import os
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

class BrowserManager:
    """Gestisce un'istanza singleton del browser Playwright."""
    _instance = None
    _browser: Optional[Browser] = None
    _playwright = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
        return cls._instance
        
    async def get_browser(self) -> Browser:
        if self._browser is None:
            logger.info("Avvio nuova istanza browser Playwright")
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser
        
    async def get_new_page(self) -> Page:
        browser = await self.get_browser()
        return await browser.new_page()

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

browser_manager = BrowserManager()

async def browser_navigate(url: str, wait_seconds: int = 2) -> str:
    """Naviga verso un URL e restituisce il contenuto testuale della pagina."""
    page = None
    try:
        page = await browser_manager.get_new_page()
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(wait_seconds)
        
        # Estrai testo pulito rimuovendo script e style
        content = await page.evaluate('''() => {
            const clone = document.body.cloneNode(true);
            const scripts = clone.getElementsByTagName('script');
            const styles = clone.getElementsByTagName('style');
            while(scripts.length > 0) scripts[0].parentNode.removeChild(scripts[0]);
            while(styles.length > 0) styles[0].parentNode.removeChild(styles[0]);
            return clone.innerText || clone.textContent;
        }''')
        return f"Contenuto estratto da {url}:\n{content[:2000]}..." if content else "Nessun contenuto trovato"
    except Exception as e:
        logger.error(f"Errore navigazione {url}: {e}")
        return f"Errore: {str(e)}"
    finally:
        if page:
            await page.close()

async def browser_screenshot(url: Optional[str] = None, full_page: bool = False) -> str:
    """Scatta uno screenshot della pagina corrente e lo salva."""
    page = None
    try:
        page = await browser_manager.get_new_page()
        if url:
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1)
            
        filename = f"screenshot_{asyncio.get_event_loop().time()}.png"
        filepath = os.path.join(os.getcwd(), filename)
        await page.screenshot(path=filepath, full_page=full_page)
        return f"Screenshot salvato in: {filepath}"
    except Exception as e:
        logger.error(f"Errore screenshot: {e}")
        return f"Errore: {str(e)}"
    finally:
        if page:
            await page.close()

async def browser_click(selector: str, url: Optional[str] = None) -> str:
    """Clicca su un elemento tramite selettore CSS o testo."""
    page = None
    try:
        page = await browser_manager.get_new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1)
            
        # Cerca di cliccare (gestisce sia selettore CSS che text=...)
        if selector.startswith("text="):
            await page.click(selector)
        else:
            await page.locator(selector).first.click()
            
        return f"Click su '{selector}' completato."
    except Exception as e:
        logger.error(f"Errore click su {selector}: {e}")
        return f"Errore: {str(e)}"
    finally:
        if page:
            await page.close()

async def browser_fill(selector: str, value: str, url: Optional[str] = None) -> str:
    """Compila un campo form."""
    page = None
    try:
        page = await browser_manager.get_new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1)
            
        await page.fill(selector, value)
        return f"Campo '{selector}' compilato con '{value}'."
    except Exception as e:
        logger.error(f"Errore fill su {selector}: {e}")
        return f"Errore: {str(e)}"
    finally:
        if page:
            await page.close()

async def browser_evaluate(script: str, url: Optional[str] = None) -> str:
    """Esegue JavaScript sulla pagina e restituisce il risultato."""
    page = None
    try:
        page = await browser_manager.get_new_page()
        if url:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(1)
            
        result = await page.evaluate(script)
        return f"Risultato script: {json.dumps(result)}"
    except Exception as e:
        logger.error(f"Errore evaluate: {e}")
        return f"Errore: {str(e)}"
    finally:
        if page:
            await page.close()

# Definizioni degli strumenti (formato OpenAI function calling)
BROWSER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Naviga verso un URL e restituisce il contenuto testuale della pagina.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "L'URL da visitare."},
                    "wait_seconds": {"type": "integer", "description": "Secondi da attendere per il caricamento JS (default 2)."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Scatta uno screenshot della pagina corrente e lo salva.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "L'URL da visitare prima dello screenshot (opzionale)."},
                    "full_page": {"type": "boolean", "description": "Se true, cattura l'intera pagina scrollabile (default false)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Clicca su un elemento tramite selettore CSS o testo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selettore CSS o testo (es. 'text=Accedi')."},
                    "url": {"type": "string", "description": "L'URL da visitare prima del click (opzionale)."}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Compila un campo form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "Selettore CSS del campo input."},
                    "value": {"type": "string", "description": "Il testo da inserire."},
                    "url": {"type": "string", "description": "L'URL da visitare prima di compilare (opzionale)."}
                },
                "required": ["selector", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": "Esegue JavaScript sulla pagina e restituisce il risultato.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "Il codice JS da eseguire."},
                    "url": {"type": "string", "description": "L'URL da visitare prima di eseguire lo script (opzionale)."}
                },
                "required": ["script"]
            }
        }
    }
]

# Mapping dei tool alle rispettive funzioni asincrone
BROWSER_TOOL_HANDLERS = {
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_fill": browser_fill,
    "browser_evaluate": browser_evaluate
}
