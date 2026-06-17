"""
Tool Web Search per nik29-coordinator.
Effettua ricerche web usando DuckDuckGo HTML (no API key richiesta).
"""

import logging
import re
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger("web_tool")

SEARCH_URL = "https://html.duckduckgo.com/html/"
MAX_RESULTS = 8
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class WebSearchTool:
    """Effettua ricerche web e restituisce risultati formattati."""

    async def execute(self, query: str) -> str:
        """
        Cerca su internet e restituisce i risultati.

        Args:
            query: La query di ricerca

        Returns:
            Risultati formattati come stringa
        """
        if not query or not query.strip():
            return "Errore: nessuna query specificata."

        logger.info(f"Ricerca web: {query}")

        try:
            results = await self._search_duckduckgo(query)
            if not results:
                return f"Nessun risultato trovato per: \"{query}\""

            # Formatta risultati
            output_lines = [f"Risultati per: \"{query}\"\n"]
            for i, result in enumerate(results[:MAX_RESULTS], 1):
                title = result.get("title", "Senza titolo")
                url = result.get("url", "")
                snippet = result.get("snippet", "")
                output_lines.append(f"{i}. **{title}**")
                if url:
                    output_lines.append(f"   URL: {url}")
                if snippet:
                    output_lines.append(f"   {snippet}")
                output_lines.append("")

            return "\n".join(output_lines)

        except Exception as e:
            return f"Errore nella ricerca web: {str(e)}"

    async def _search_duckduckgo(self, query: str) -> list:
        """Esegue la ricerca su DuckDuckGo HTML e parsa i risultati."""
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"
        }
        data = {"q": query, "b": ""}

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(SEARCH_URL, headers=headers, data=data)
            if resp.status_code != 200:
                return []

            html = resp.text
            return self._parse_results(html)

    def _parse_results(self, html: str) -> list:
        """Parsa i risultati dalla pagina HTML di DuckDuckGo."""
        results = []

        # Pattern per estrarre risultati
        # DuckDuckGo HTML usa class="result__a" per i link
        link_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</(?:a|span|td)',
            re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(links[:MAX_RESULTS]):
            # Pulisci HTML dai tag
            clean_title = re.sub(r'<[^>]+>', '', title).strip()
            clean_url = url.strip()

            # DuckDuckGo wrappa gli URL in un redirect
            if "uddg=" in clean_url:
                match = re.search(r'uddg=([^&]+)', clean_url)
                if match:
                    from urllib.parse import unquote
                    clean_url = unquote(match.group(1))

            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

            if clean_title and clean_url:
                results.append({
                    "title": clean_title,
                    "url": clean_url,
                    "snippet": snippet
                })

        return results
