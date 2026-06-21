"""
Loader per self_evolution - importato dal coordinator all'avvio.
Registra i tool di self_evolution (create_tool, list_custom_tools, remove_custom_tool)
e tutti i tool custom creati.
"""

import sys
import os

def load_self_evolution_tools():
    """
    Carica le definizioni dei tool di self_evolution.
    Ritorna la lista di definizioni tool per OpenAI function calling.
    """
    try:
        sys.path.insert(0, "/app/app")
        from self_evolution import get_custom_tools_definitions
        return get_custom_tools_definitions()
    except Exception as e:
        print(f"[self_evolution_loader] Errore caricamento: {e}")
        return []


def handle_self_evolution_tool(tool_name: str, params: dict):
    """
    Gestisce l'esecuzione di un tool di self_evolution.
    Da chiamare nel coordinator quando il tool_name corrisponde.
    """
    import asyncio
    try:
        from self_evolution import execute_custom_tool

        # Controlla se siamo già in un event loop
        try:
            loop = asyncio.get_running_loop()
            # Se siamo in un loop, crea un task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = loop.run_in_executor(
                    pool,
                    lambda: asyncio.run(execute_custom_tool(tool_name, params))
                )
                return result
        except RuntimeError:
            # Nessun loop attivo, possiamo usare asyncio.run
            return asyncio.run(execute_custom_tool(tool_name, params))

    except Exception as e:
        return {"success": False, "error": f"Errore self_evolution: {str(e)}"}


# Lista dei tool gestiti da self_evolution
SELF_EVOLUTION_TOOLS = ["create_tool", "list_custom_tools", "remove_custom_tool"]


def is_self_evolution_tool(tool_name: str) -> bool:
    """Verifica se un tool è gestito da self_evolution."""
    if tool_name in SELF_EVOLUTION_TOOLS:
        return True

    # Controlla anche i tool custom nel registry
    try:
        import json
        registry_path = "/app/app/tools/custom_tools_registry.json"
        if os.path.exists(registry_path):
            with open(registry_path, "r") as f:
                registry = json.load(f)
            custom_names = [t["name"] for t in registry if t.get("active", True)]
            return tool_name in custom_names
    except Exception:
        pass

    return False
