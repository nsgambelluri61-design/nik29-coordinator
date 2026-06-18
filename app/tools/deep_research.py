"""
Deep Research Tool per nik29-coordinator
=========================================
Esegue ricerche web parallele, legge 10-20 pagine con aiohttp
(fallback Playwright per pagine che falliscono), e sintetizza
tutto con GPT-4.1 in italiano.

Autore: generato per nik29-coordinator
"""

import os
import asyncio
import logging
import json
from typing import Dict, Any, List, Optional

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger("nik29.deep_research")

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "BSAHah3s8zk26X1asFdBy2B5H5_DvyP")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

MAX_WORDS_PER_PAGE = 2000
HTTP_TIMEOUT = 10        # secondi per fetch HTTP
PLAYWRIGHT_TIMEOUT = 15  # secondi per fallback Playwright

# ---------------------------------------------------------------------------
# Schema OpenAI Tool
# ---------------------------------------------------------------------------
DEEP_RESEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "deep_research",
        "description": (
            "Ricerca web approfondita: cerca su Brave, legge 10-20 pagine in parallelo, "
            "e sintetizza i risultati con GPT-4.1. Usa questo tool quando serve una ricerca "
            "completa su un argomento."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "La query di ricerca"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Numero di pagine da leggere (default 10, max 20)"
                },
                "focus": {
                    "type": "string",
                    "description": "Aspetto specifico su cui concentrare la sintesi (opzionale)"
                }
            },
            "required": ["query"]
        }
    }
}

# ---------------------------------------------------------------------------
# 1. Brave Search
# ---------------------------------------------------------------------------
async def _brave_search(query: str, count: int) -> List[Dict[str, str]]:
    """Cerca URL rilevanti su Brave Search API."""
    count = max(1, min(count, 20))
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": count,
        "search_lang": "it",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                BRAVE_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error(f"Brave API error HTTP {resp.status}: {body[:200]}")
                    return []
                data = await resp.json()
                results = data.get("web", {}).get("results", [])
                return [
                    {"url": r.get("url", ""), "title": r.get("title", "No title")}
                    for r in results
                    if r.get("url")
                ]
    except Exception as exc:
        logger.error(f"Brave search exception: {exc}")
        return []


# ---------------------------------------------------------------------------
# 2. Estrazione testo con BeautifulSoup
# ---------------------------------------------------------------------------
def _extract_text(html: str) -> str:
    """Estrae il testo principale da HTML rimuovendo nav/footer/ads."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    # Rimuovi elementi non pertinenti
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "iframe", "noscript", "form", "button",
                     "advertisement", "ads"]):
        tag.decompose()

    # Prova prima a trovare il contenuto principale
    main_content = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id="content")
        or soup.find(class_="content")
        or soup.find(class_="post-content")
        or soup.find(class_="entry-content")
        or soup.body
    )

    target = main_content if main_content else soup
    text = target.get_text(separator=" ", strip=True)

    # Tronca a MAX_WORDS_PER_PAGE parole
    words = text.split()
    if len(words) > MAX_WORDS_PER_PAGE:
        words = words[:MAX_WORDS_PER_PAGE]
    return " ".join(words)


# ---------------------------------------------------------------------------
# 3. Fetch HTTP singola pagina
# ---------------------------------------------------------------------------
async def _fetch_http(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTTP di una singola pagina. Restituisce testo pulito o stringa vuota."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    }
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            allow_redirects=True,
        ) as resp:
            if resp.status == 200:
                html = await resp.text(errors="replace")
                text = _extract_text(html)
                if len(text.strip()) >= 50:
                    return text
    except asyncio.TimeoutError:
        logger.debug(f"HTTP timeout per: {url}")
    except Exception as exc:
        logger.debug(f"HTTP fetch fallito per {url}: {exc}")
    return ""


# ---------------------------------------------------------------------------
# 4. Fallback Playwright
# ---------------------------------------------------------------------------
async def _fetch_playwright(url: str) -> str:
    """
    Fallback Playwright per pagine che richiedono JS.
    Prova prima il server Playwright su localhost:5006,
    poi il browser_manager interno del coordinator.
    """
    # Tentativo 1: API server Playwright su :5006
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"url": url, "wait_time": 2}
            async with session.post(
                "http://localhost:5006/navigate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=PLAYWRIGHT_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("content", "")
                    words = text.split()
                    if len(words) > MAX_WORDS_PER_PAGE:
                        words = words[:MAX_WORDS_PER_PAGE]
                    if len(" ".join(words).strip()) >= 50:
                        return " ".join(words)
    except Exception as exc:
        logger.debug(f"Playwright server :5006 non disponibile per {url}: {exc}")

    # Tentativo 2: browser_manager interno (headless Chromium del coordinator)
    try:
        from app.tools.browser_tools import browser_manager
        page = await browser_manager.get_new_page()
        try:
            await asyncio.wait_for(
                page.goto(url, wait_until="domcontentloaded"),
                timeout=PLAYWRIGHT_TIMEOUT,
            )
            await asyncio.sleep(1)
            html = await page.content()
            text = _extract_text(html)
            if len(text.strip()) >= 50:
                return text
        finally:
            await page.close()
    except Exception as exc:
        logger.error(f"browser_manager fallback fallito per {url}: {exc}")

    return ""


# ---------------------------------------------------------------------------
# 5. Processo singola pagina (HTTP + Playwright fallback)
# ---------------------------------------------------------------------------
async def _process_page(url_data: Dict[str, str], session: aiohttp.ClientSession) -> Dict[str, str]:
    """Scarica e processa una singola pagina con retry automatico su Playwright."""
    url = url_data["url"]
    title = url_data.get("title", url)

    text = await _fetch_http(url, session)

    if not text:
        logger.info(f"Fallback Playwright per: {url}")
        text = await _fetch_playwright(url)

    return {
        "url": url,
        "title": title,
        "content": text if text else "",
    }


# ---------------------------------------------------------------------------
# 6. Sintesi GPT-4.1
# ---------------------------------------------------------------------------
async def _synthesize_with_gpt(
    query: str,
    focus: Optional[str],
    pages_data: List[Dict[str, str]],
) -> str:
    """Invia i contenuti estratti a GPT-4.1 per una sintesi strutturata in italiano."""
    if not OPENAI_API_KEY:
        return "Errore: OPENAI_API_KEY non configurata nell'ambiente."

    # Costruisci il contesto numerando le fonti
    context_parts = []
    for i, p in enumerate(pages_data, 1):
        if p.get("content"):
            context_parts.append(
                f"[{i}] FONTE: {p['title']}\nURL: {p['url']}\n{p['content'][:3000]}"
            )

    if not context_parts:
        return "Nessun contenuto utile estratto dalle pagine."

    full_context = "\n\n---\n\n".join(context_parts)
    focus_instruction = (
        f"Concentrati in particolare su questo aspetto: **{focus}**"
        if focus
        else "Fornisci una sintesi completa, esaustiva e ben strutturata."
    )

    system_prompt = (
        "Sei un assistente di ricerca esperto. Il tuo compito è analizzare le informazioni "
        "estratte da diverse fonti web e produrre una sintesi dettagliata in italiano.\n\n"
        "Regole:\n"
        "1. Usa il formato Markdown (titoli ##, elenchi, **grassetto** per concetti chiave).\n"
        "2. Cita le fonti con numeri [1], [2], ecc. nel testo dove pertinente.\n"
        "3. Includi una sezione '## Fonti' alla fine con URL numerati.\n"
        "4. Sintetizza in modo logico e coerente, non riassumere ogni fonte separatamente.\n"
        "5. Sii obiettivo e basati ESCLUSIVAMENTE sulle informazioni fornite nel contesto.\n"
        "6. Se le fonti sono contraddittorie, segnalalo esplicitamente."
    )

    user_prompt = (
        f"**Query di ricerca:** {query}\n"
        f"{focus_instruction}\n\n"
        f"**Contenuti estratti dal web:**\n\n{full_context}"
    )

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Prova prima gpt-4.1, poi fallback a gpt-4o
    for model in ["gpt-4.1", "gpt-4o"]:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 3000,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{OPENAI_API_BASE}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"]
                    elif resp.status == 404 and model == "gpt-4.1":
                        logger.warning("gpt-4.1 non disponibile, provo gpt-4o...")
                        continue
                    else:
                        error_text = await resp.text()
                        logger.error(f"OpenAI API error {resp.status}: {error_text[:300]}")
                        return f"Errore nella sintesi GPT (HTTP {resp.status})."
        except Exception as exc:
            logger.error(f"GPT synthesis exception con {model}: {exc}")
            if model == "gpt-4.1":
                continue
            return f"Errore durante la chiamata a GPT: {exc}"

    return "Errore: nessun modello GPT disponibile."


# ---------------------------------------------------------------------------
# 7. Funzione principale deep_research
# ---------------------------------------------------------------------------
async def execute_deep_research(
    query: str,
    num_results: int = 10,
    focus: Optional[str] = None,
) -> str:
    """
    Orchestratore principale del deep research.
    1. Brave Search -> URL
    2. Fetch parallelo (aiohttp + Playwright fallback)
    3. Sintesi GPT-4.1
    """
    num_results = max(1, min(num_results, 20))
    logger.info(f"[deep_research] Query='{query}' num_results={num_results} focus={focus}")

    # Step 1: Brave Search
    urls = await _brave_search(query, num_results)
    if not urls:
        return f"Nessun risultato trovato su Brave Search per: '{query}'"

    logger.info(f"[deep_research] Trovati {len(urls)} URL. Avvio fetch parallelo...")

    # Step 2: Fetch parallelo (max 20 pagine contemporaneamente)
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_process_page(url_data, session) for url_data in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filtra errori e pagine vuote
    valid_pages = []
    for r in results:
        if isinstance(r, dict) and r.get("content") and len(r["content"].strip()) >= 50:
            valid_pages.append(r)

    if not valid_pages:
        return "Impossibile estrarre contenuti utili dalle pagine trovate."

    logger.info(f"[deep_research] Estratti contenuti da {len(valid_pages)}/{len(urls)} pagine. Avvio sintesi GPT...")

    # Step 3: Sintesi GPT
    synthesis = await _synthesize_with_gpt(query, focus, valid_pages)

    # Step 4: Formatta risultato finale
    output = (
        f"# Deep Research: {query}\n\n"
        f"{synthesis}\n\n"
        f"---\n"
        f"*Pagine analizzate: {len(valid_pages)}/{len(urls)}*"
    )
    return output


# ---------------------------------------------------------------------------
# 8. Wrapper per il dispatcher del coordinator
# ---------------------------------------------------------------------------
async def deep_research(**kwargs: Any) -> str:
    """Entry point chiamato dal dispatcher di coordinator.py."""
    query = kwargs.get("query", "").strip()
    if not query:
        return "Errore: il parametro 'query' è obbligatorio."

    num_results = int(kwargs.get("num_results", 10))
    focus = kwargs.get("focus") or None

    return await execute_deep_research(query, num_results, focus)


# ---------------------------------------------------------------------------
# Registry per il dispatcher (pattern del progetto)
# ---------------------------------------------------------------------------
DEEP_RESEARCH_TOOL_HANDLERS = {
    "deep_research": deep_research,
}
