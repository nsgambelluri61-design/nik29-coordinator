"""
semantic_search_tool.py - Tool per la ricerca semantica avanzata nella memoria persistente.
"""
from typing import Optional
from app.semantic_memory import search_memory_semantic

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "semantic_search",
        "description": "Esegue una ricerca semantica avanzata (per significato) in tutte le memorie (fatti, preferenze, lezioni, regole).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Il concetto o la domanda da cercare"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Numero massimo di risultati da restituire (default: 5)"
                }
            },
            "required": ["query"]
        }
    }
}

class SemanticSearchTool:
    """Tool per eseguire ricerche semantiche."""
    
    def __init__(self):
        self.name = "semantic_search"

    async def execute(self, query: str, top_k: int = 5, **kwargs) -> str:
        """Esegue la ricerca semantica e formatta i risultati."""
        if not query.strip():
            return "❌ Errore: La query di ricerca non può essere vuota."
            
        try:
            results = await search_memory_semantic(query, top_k=top_k)
            if results:
                response = f"🔍 Risultati ricerca semantica per '{query}':\n"
                for r in results:
                    score_pct = int(r['score'] * 100)
                    # Mostra solo risultati con score rilevante (> 20%)
                    if score_pct > 20:
                        source = r.get('metadata', {}).get('source', 'sconosciuta')
                        response += f"- [{score_pct}% match] [{source}] {r['text']}\n"
                return response
            else:
                return f"Nessun risultato semantico trovato per: '{query}'"
        except Exception as e:
            return f"❌ Errore durante la ricerca semantica: {e}"
