#!/usr/bin/env python3
"""Patch coordinator.py per aggiungere generate_agent tool - v3 DEFINITIVO."""
import ast, sys, shutil

COORD = "/app/app/coordinator.py"
BACKUP = "/app/app/coordinator.py.bak_v3"

shutil.copy(COORD, BACKUP)
print("Backup creato:", BACKUP)

with open(COORD) as f:
    content = f.read()

if "generate_agent_tool" in content:
    print("GIA PRESENTE - nessuna modifica necessaria")
    sys.exit(0)

lines = content.split("\n")

# PATCH 1: Import - dopo "from app.tools.verify_tool import VerifyTool"
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
print("1/3 Import inserito dopo riga", pos + 1)

# PATCH 2: Tool definitions - dopo "TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF)"
# IMPORTANTE: cerchiamo specificamente DEEP_RESEARCH_TOOL_DEF a livello di modulo
# (non dentro un try/except)
td_lines = [
    "TOOLS_DEFINITION.append(GENERATE_AGENT_TOOL_DEFINITION)",
    "TOOLS_DEFINITION.append(LIST_DOCKER_AGENTS_TOOL_DEFINITION)",
    "TOOLS_DEFINITION.append(REMOVE_DOCKER_AGENT_TOOL_DEFINITION)",
]
pos2 = -1
for i, line in enumerate(lines):
    if "TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF)" in line:
        pos2 = i
        break
if pos2 < 0:
    # Fallback: ultima riga che inizia con TOOLS_DEFINITION.append (senza indentazione)
    for i, line in enumerate(lines):
        if line.startswith("TOOLS_DEFINITION.append("):
            pos2 = i
for idx, td in enumerate(td_lines):
    lines.insert(pos2 + 1 + idx, td)
print("2/3 Tool defs inserite dopo riga", pos2 + 1)

# PATCH 3: Dispatch - PRIMA di "# === Deep Research Tool Dispatch ==="
dp_lines = [
    "            # === Generate Agent Tools (Level 4) ===",
    '            elif name == "generate_agent":',
    "                return await execute_generate_agent(args)",
    '            elif name == "list_docker_agents":',
    "                return await execute_list_docker_agents(args)",
    '            elif name == "remove_docker_agent":',
    "                return await execute_remove_docker_agent(args)",
]
pos3 = -1
for i, line in enumerate(lines):
    if "Deep Research Tool Dispatch" in line:
        pos3 = i
        break
if pos3 > 0:
    for idx, dp in enumerate(dp_lines):
        lines.insert(pos3 + idx, dp)
    print("3/3 Dispatch inserito prima di riga", pos3)
else:
    print("ERRORE: non trovo 'Deep Research Tool Dispatch'!")
    shutil.copy(BACKUP, COORD)
    print("ROLLBACK eseguito")
    sys.exit(1)

# Verifica sintassi
new_content = "\n".join(lines)
try:
    ast.parse(new_content)
except SyntaxError as e:
    print("ERRORE SINTASSI riga", e.lineno, ":", e.msg)
    shutil.copy(BACKUP, COORD)
    print("ROLLBACK eseguito")
    sys.exit(1)

with open(COORD, "w") as f:
    f.write(new_content)

print("")
print("=== PATCH COMPLETATA CON SUCCESSO! ===")
print("Ora fai: docker restart nik29-coordinator")
