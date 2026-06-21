#!/usr/bin/env python3
"""
patch_persistent_memory.py - Script per integrare semantic_memory.py in persistent_memory.py e coordinator.py
"""
import os
import shutil
import re

APP_DIR = "/app/app"
PERSISTENT_MEMORY_PATH = os.path.join(APP_DIR, "persistent_memory.py")
COORDINATOR_PATH = os.path.join(APP_DIR, "coordinator.py")

def backup_file(filepath):
    """Crea un backup del file se non esiste già."""
    if os.path.exists(filepath):
        backup_path = filepath + ".bak_semantic"
        if not os.path.exists(backup_path):
            shutil.copy2(filepath, backup_path)
            print(f"Backup creato: {backup_path}")
        return True
    return False

def patch_persistent_memory():
    """Aggiunge l'import e la chiamata a save_memory_semantic in persistent_memory.py."""
    if not backup_file(PERSISTENT_MEMORY_PATH):
        print(f"File non trovato: {PERSISTENT_MEMORY_PATH}")
        return False
        
    with open(PERSISTENT_MEMORY_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    if "save_memory_semantic" in content:
        print("persistent_memory.py è già stato patchato.")
        return True
        
    # Aggiungi import in cima
    import_statement = "import asyncio\nfrom app.semantic_memory import save_memory_semantic\n"
    if "import json" in content:
        content = content.replace("import json", f"import json\n{import_statement}", 1)
    
    # Trova il punto dove vengono salvati i nuovi fatti in extract_and_save_learnings
    if "logger.info(f\"Auto-salvati {len(new_facts)} nuovi fatti" in content:
        fact_patch = """logger.info(f"Auto-salvati {len(new_facts)} nuovi fatti dalla conversazione {conversation_id}")
        # Salvataggio semantico in background
        for fact in new_facts[:3]:
            try:
                asyncio.create_task(save_memory_semantic(fact, {"source": "facts.json", "category": "auto_learned"}))
            except Exception as e:
                logger.error(f"Errore salvataggio semantico: {e}")"""
        content = content.replace("logger.info(f\"Auto-salvati {len(new_facts)} nuovi fatti dalla conversazione {conversation_id}\")", fact_patch)
        
    # Trova il punto dove vengono salvate le nuove preferenze in extract_and_save_learnings
    if "logger.info(f\"Auto-salvate {len(new_preferences)} nuove preferenze" in content:
        pref_patch = """logger.info(f"Auto-salvate {len(new_preferences)} nuove preferenze dalla conversazione {conversation_id}")
        # Salvataggio semantico in background
        for pref in new_preferences[:3]:
            try:
                text = f"Preferenza: {pref}"
                asyncio.create_task(save_memory_semantic(text, {"source": "preferences.json", "type": "auto_learned"}))
            except Exception as e:
                logger.error(f"Errore salvataggio semantico: {e}")"""
        content = content.replace("logger.info(f\"Auto-salvate {len(new_preferences)} nuove preferenze dalla conversazione {conversation_id}\")", pref_patch)
        
    with open(PERSISTENT_MEMORY_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("persistent_memory.py patchato con successo.")
    return True

def patch_coordinator():
    """Registra semantic_search_tool in coordinator.py."""
    if not backup_file(COORDINATOR_PATH):
        print(f"File non trovato: {COORDINATOR_PATH}")
        return False
        
    with open(COORDINATOR_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    if "SemanticSearchTool" in content:
        print("coordinator.py è già stato patchato.")
        return True
        
    # 1. Aggiungi import del tool
    import_tool = "from app.tools.semantic_search_tool import SemanticSearchTool, TOOL_DEFINITION as SEMANTIC_SEARCH_TOOL_DEFINITION\n"
    if "from app.tools.shell_tool import ShellTool" in content:
        content = content.replace("from app.tools.shell_tool import ShellTool", f"{import_tool}from app.tools.shell_tool import ShellTool", 1)
        
    # 2. Aggiungi alla lista TOOLS_DEFINITION
    if "TOOLS_DEFINITION.append(THINK_TOOL_DEFINITION)" in content:
        content = content.replace("TOOLS_DEFINITION.append(THINK_TOOL_DEFINITION)", "TOOLS_DEFINITION.append(SEMANTIC_SEARCH_TOOL_DEFINITION)\nTOOLS_DEFINITION.append(THINK_TOOL_DEFINITION)", 1)
        
    # 3. Inizializza il tool nel __init__ di Coordinator
    if "self.shell_tool = ShellTool()" in content:
        content = content.replace("self.shell_tool = ShellTool()", "self.semantic_search_tool = SemanticSearchTool()\n        self.shell_tool = ShellTool()", 1)
        
    # 4. Aggiungi messaggio di progresso in _progress_message
    if "\"save_memory\": lambda a: \"Salvo nella memoria...\"," in content:
        content = content.replace("\"save_memory\": lambda a: \"Salvo nella memoria...\",", "\"semantic_search\": lambda a: f\"Ricerca semantica per: {a.get('query', '')}...\",\n            \"save_memory\": lambda a: \"Salvo nella memoria...\",", 1)
        
    # 5. Aggiungi handler in _execute_tool
    if "elif name == \"save_memory\":" in content:
        handler = """elif name == "semantic_search":
                return await self.semantic_search_tool.execute(
                    query=args.get("query", ""),
                    top_k=args.get("top_k", 5)
                )
            elif name == "save_memory":"""
        content = content.replace("elif name == \"save_memory\":", handler, 1)
        
    with open(COORDINATOR_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("coordinator.py patchato con successo.")
    return True

if __name__ == "__main__":
    print("Inizio patching per memoria semantica...")
    
    # Assicurati che i file siano nel posto giusto
    if not os.path.exists(os.path.join(APP_DIR, "semantic_memory.py")):
        if os.path.exists("semantic_memory.py"):
            shutil.copy2("semantic_memory.py", os.path.join(APP_DIR, "semantic_memory.py"))
            
    if not os.path.exists(os.path.join(APP_DIR, "tools", "semantic_search_tool.py")):
        if os.path.exists("semantic_search_tool.py"):
            os.makedirs(os.path.join(APP_DIR, "tools"), exist_ok=True)
            shutil.copy2("semantic_search_tool.py", os.path.join(APP_DIR, "tools", "semantic_search_tool.py"))
            
    patch_persistent_memory()
    patch_coordinator()
    
    print("Patching completato.")
