#!/usr/bin/env python3
"""Patch coordinator.py per aggiungere generate_agent tool."""
import ast, sys, shutil

COORD = "/app/app/coordinator.py"
BACKUP = "/app/app/coordinator.py.bak3"

shutil.copy(COORD, BACKUP)
print(f"Backup: {BACKUP}")

with open(COORD) as f:
    content = f.read()

if "generate_agent_tool" in content:
    print("GIA PRESENTE - nessuna modifica")
    sys.exit(0)

lines = content.split("\n")

# PATCH 1: Import
imp = "from app.tools.generate_agent_tool import GENERATE_AGENT_TOOL_DEFINITION, LIST_DOCKER_AGENTS_TOOL_DEFINITION, REMOVE_DOCKER_AGENT_TOOL_DEFINITION, execute_generate_agent, execute_list_docker_agents, execute_remove_docker_agent"
pos = -1
for i, line in enumerate(lines):
    if "verify_tool" in line and "import" in line:
        pos = i
        break
if pos < 0:
    for i, line in enumerate(lines):
        if line.startswith("from "):
            pos = i
lines.insert(pos + 1, imp)
print(f"Import inserito dopo riga {pos + 1}")

# PATCH 2: Tool definitions
td = "TOOLS_DEFINITION.append(GENERATE_AGENT_TOOL_DEFINITION)\nTOOLS_DEFINITION.append(LIST_DOCKER_AGENTS_TOOL_DEFINITION)\nTOOLS_DEFINITION.append(REMOVE_DOCKER_AGENT_TOOL_DEFINITION)"
pos2 = -1
for i, line in enumerate(lines):
    if "TOOLS_DEFINITION.append(" in line:
        pos2 = i
lines.insert(pos2 + 1, td)
print(f"Tool defs inserite dopo riga {pos2 + 1}")

# PATCH 3: Dispatch
dp = '            elif name == "generate_agent":\n                return await execute_generate_agent(args)\n            elif name == "list_docker_agents":\n                return await execute_list_docker_agents(args)\n            elif name == "remove_docker_agent":\n                return await execute_remove_docker_agent(args)'
pos3 = -1
for i, line in enumerate(lines):
    if "custom_" in line and "startswith" in line:
        pos3 = i
        break
if pos3 > 0:
    lines.insert(pos3, dp)
    print(f"Dispatch inserito prima di riga {pos3 + 1}")
else:
    print("ATTENZIONE: dispatch non inserito (non trovato punto di inserimento)")

# Verifica sintassi
new_content = "\n".join(lines)
try:
    ast.parse(new_content)
except SyntaxError as e:
    print(f"ERRORE SINTASSI riga {e.lineno}: {e.msg}")
    shutil.copy(BACKUP, COORD)
    print("ROLLBACK eseguito!")
    sys.exit(1)

with open(COORD, "w") as f:
    f.write(new_content)

print("PATCH COMPLETATA CON SUCCESSO!")
