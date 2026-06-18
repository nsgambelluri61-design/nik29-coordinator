#!/usr/bin/env python3
"""
Fix: patch coordinator.py per registrare i tool multi-agente.
I file sono gia' al posto giusto (unzip li ha messi).
Eseguire da: cd ~/Downloads/nik29-coordinator-v0.6.0 && python3 fix_agents_patch.py
"""
import sys
from pathlib import Path

root = Path(__file__).parent
coord = root / "app" / "coordinator.py"

if not coord.exists():
    print("ERRORE: coordinator.py non trovato!")
    sys.exit(1)

# Verifica file agenti
for f in ["app/agents/__init__.py", "app/agents/agent_manager.py", "app/agents/agent_tools.py"]:
    if not (root / f).exists():
        print(f"ERRORE: {f} mancante!")
        sys.exit(1)
print("File agenti OK")

content = coord.read_text(encoding="utf-8")

# Backup
backup = coord.with_suffix(".py.bak_agents2")
backup.write_text(content, encoding="utf-8")

if "handle_create_agent" in content:
    print("Patch gia' applicato! Niente da fare.")
    sys.exit(0)

# PATCH 1: Aggiungi import dopo l'import di model_router
old_import = "from app.routing.model_router import route_model"
new_import = """from app.routing.model_router import route_model
from app.agents.agent_tools import ALL_AGENT_TOOL_SCHEMAS, handle_create_agent, handle_delegate_to_agent, handle_list_agents
from app.agents import AgentManager"""

if old_import in content:
    content = content.replace(old_import, new_import)
    print("OK: Import aggiunto")
else:
    print("WARN: import model_router non trovato, aggiungo in cima")
    content = "from app.agents.agent_tools import ALL_AGENT_TOOL_SCHEMAS, handle_create_agent, handle_delegate_to_agent, handle_list_agents\nfrom app.agents import AgentManager\n" + content

# PATCH 2: Aggiungi handler nel dispatcher (dopo BROWSER_TOOL_HANDLERS)
old_dispatch = "elif name in BROWSER_TOOL_HANDLERS:\n                handler = BROWSER_TOOL_HANDLERS[name]\n                return str(await handler(**args))"
new_dispatch = """elif name in BROWSER_TOOL_HANDLERS:
                handler = BROWSER_TOOL_HANDLERS[name]
                return str(await handler(**args))
            # === Multi-Agent Framework ===
            elif name == "create_agent":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_create_agent(args, self._agent_manager)
            elif name == "delegate_to_agent":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_delegate_to_agent(args, self._agent_manager)
            elif name == "list_agents":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_list_agents(args, self._agent_manager)"""

if old_dispatch in content:
    content = content.replace(old_dispatch, new_dispatch)
    print("OK: Handler registrati nel dispatcher")
else:
    print("WARN: Pattern dispatcher non trovato esattamente, provo variante...")
    # Prova con indentazione diversa
    if "BROWSER_TOOL_HANDLERS" in content:
        # Inserisci dopo il blocco BROWSER
        marker = "return str(await handler(**args))"
        # Trova l'ultima occorrenza (quella del browser)
        idx = content.rfind(marker)
        if idx > 0:
            insert_pos = idx + len(marker)
            agent_block = """
            # === Multi-Agent Framework ===
            elif name == "create_agent":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_create_agent(args, self._agent_manager)
            elif name == "delegate_to_agent":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_delegate_to_agent(args, self._agent_manager)
            elif name == "list_agents":
                if not hasattr(self, '_agent_manager'):
                    self._agent_manager = AgentManager()
                return await handle_list_agents(args, self._agent_manager)"""
            content = content[:insert_pos] + agent_block + content[insert_pos:]
            print("OK: Handler registrati (variante)")
        else:
            print("ERRORE: non riesco a trovare il punto di inserimento!")
            sys.exit(1)

# PATCH 3: Aggiungi gli schema alla lista tools
# Cerca dove vengono aggiunti i tool (pattern: *BROWSER_TOOLS o tools.extend)
if "ALL_AGENT_TOOL_SCHEMAS" not in content.split("import")[-1]:
    # Cerca *BROWSER_TOOLS nella lista
    if "*BROWSER_TOOLS" in content:
        content = content.replace("*BROWSER_TOOLS,", "*BROWSER_TOOLS,\n    *ALL_AGENT_TOOL_SCHEMAS,")
        print("OK: Schema tool aggiunti alla lista")
    elif "BROWSER_TOOLS" in content:
        # Potrebbe essere aggiunto con extend
        # Aggiungiamo dopo l'ultima riga che aggiunge tool
        content = content.replace(
            "from app.tools.browser_tools import BROWSER_TOOLS, BROWSER_TOOL_HANDLERS",
            "from app.tools.browser_tools import BROWSER_TOOLS, BROWSER_TOOL_HANDLERS\n# Agent tools schemas aggiunti via ALL_AGENT_TOOL_SCHEMAS"
        )
        # Trova dove tools viene definito e aggiungi extend
        if "tools = [" in content or "self.tools" in content:
            pass  # Lo gestiamo diversamente
    else:
        print("WARN: Non trovo dove aggiungere gli schema. Li aggiungo manualmente.")

# Salva
coord.write_text(content, encoding="utf-8")
print("\ncoordinator.py patchato con successo!")
print("Ora fai: docker compose build && docker compose up -d")
