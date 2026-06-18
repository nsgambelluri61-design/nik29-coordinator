"""
Level 3 Autonomy — Web Search & Browse Tools
Brave Search API, URL browsing, and combined web research.
"""

import os
import logging
from typing import Optional

import aiohttp
import trafilatura

logger = logging.getLogger("nik29.web_tools")

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Max chars to return from page content
MAX_PAGE_CONTENT = 4000


# ============================================================
# BRAVE SEARCH TOOL
# ============================================================

BRAVE_SEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "brave_search",
        "description": (
            "Search the web using Brave Search API. Returns top results with title, URL, and snippet. "
            "Use for finding current information, products, news, or any web content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (1-10, default 5).",
                },
                "language": {
                    "type": "string",
                    "description": "Language code (e.g., 'it' for Italian, 'en' for English). Default: 'it'.",
                },
            },
            "required": ["query"],
        },
    },
}


async def brave_search(query: str, count: int = 5, language: str = "it") -> dict:
    """Search the web using Brave Search API."""
    if not BRAVE_API_KEY:
        return {"error": "BRAVE_API_KEY not configured. Set it in environment variables."}

    count = max(1, min(10, count))

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": count,
        "search_lang": language,
        "ui_lang": language,
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
                    return {"error": f"Brave API error (HTTP {resp.status}): {body[:200]}"}

                data = await resp.json()

        # Extract web results
        web_results = data.get("web", {}).get("results", [])
        results = []
        for r in web_results[:count]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            })

        return {
            "query": query,
            "results": results,
            "total_found": len(results),
        }

    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


# ============================================================
# BROWSE URL TOOL
# ============================================================

BROWSE_URL_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "browse_url",
        "description": (
            "Download a web page and extract its main text content. "
            "Strips HTML and returns clean readable text (max 4000 chars). "
            "Use to actually READ the content of a web page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to browse and extract content from.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 4000).",
                },
            },
            "required": ["url"],
        },
    },
}


async def browse_url(url: str, max_chars: int = MAX_PAGE_CONTENT) -> dict:
    """Download and extract main content from a URL."""
    try:
        # Download the page
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status} fetching {url}"}
                html = await resp.text()

        # Extract main content using trafilatura
        content = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=False,
        )

        if not content:
            # Fallback: try basic extraction
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            # Remove scripts and styles
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            content = soup.get_text(separator="\n", strip=True)

        if not content:
            return {"url": url, "content": "", "error": "Could not extract content from page."}

        # Truncate if needed
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[... contenuto troncato ...]"

        return {
            "url": url,
            "content": content,
            "length": len(content),
        }

    except Exception as e:
        return {"url": url, "content": "", "error": f"Failed to browse: {str(e)}"}


# ============================================================
# WEB RESEARCH TOOL
# ============================================================

WEB_RESEARCH_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "web_research",
        "description": (
            "Power research tool: searches the web for a query, then reads the top 3 results "
            "and returns their content. Combines brave_search + browse_url for comprehensive research."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The research query.",
                },
                "num_pages": {
                    "type": "integer",
                    "description": "Number of pages to read (1-5, default 3).",
                },
                "language": {
                    "type": "string",
                    "description": "Search language (default 'it').",
                },
            },
            "required": ["query"],
        },
    },
}


async def web_research(query: str, num_pages: int = 3, language: str = "it") -> dict:
    """Search and read multiple pages for comprehensive research."""
    num_pages = max(1, min(5, num_pages))

    # Step 1: Search
    search_results = await brave_search(query=query, count=num_pages + 2, language=language)

    if "error" in search_results:
        return {"error": f"Search failed: {search_results['error']}"}

    results = search_results.get("results", [])
    if not results:
        return {"query": query, "findings": [], "summary": "No results found."}

    # Step 2: Browse top results
    findings = []
    for r in results[:num_pages]:
        url = r.get("url", "")
        if not url:
            continue

        page_content = await browse_url(url=url, max_chars=2000)

        findings.append({
            "title": r.get("title", ""),
            "url": url,
            "snippet": r.get("snippet", ""),
            "content": page_content.get("content", ""),
            "error": page_content.get("error"),
        })

    return {
        "query": query,
        "findings": findings,
        "pages_read": len(findings),
    }


# ============================================================
# TOOL REGISTRY
# ============================================================

WEB_TOOLS = [BRAVE_SEARCH_TOOL_DEF, BROWSE_URL_TOOL_DEF, WEB_RESEARCH_TOOL_DEF]

WEB_TOOL_HANDLERS = {
    "brave_search": brave_search,
    "browse_url": browse_url,
    "web_research": web_research,
}
