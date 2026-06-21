#!/bin/bash
# fix_vision_direct.sh
# Aggiorna vision_chat_patch.py (GPT-4o diretto, no nik29-images/4002)
# e patcha agent_client.py per rimuovere il default agent nik29-images.

set -e

CONTAINER="nik29-coordinator"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== fix_vision_direct.sh — GPT-4o Vision diretta ==="
echo ""

# -------------------------------------------------------
# 1. Copia il nuovo vision_chat_patch.py nel container
# -------------------------------------------------------
echo "[1/4] Copia vision_chat_patch.py nel container..."
docker cp "${SCRIPT_DIR}/vision_chat_patch.py" "${CONTAINER}:/app/app/vision_chat_patch.py"
echo "  OK."

# -------------------------------------------------------
# 2. Patch agent_client.py — rimuovi il DEFAULT_AGENTS
#    che punta a nik29-images:4002 e sostituiscilo con
#    lista vuota (il file agents.json su disco ha la
#    precedenza; se non esiste, ora parte da lista vuota
#    invece di tentare di contattare un container morto).
# -------------------------------------------------------
echo "[2/4] Patch agent_client.py (rimozione nik29-images:4002)..."

docker exec "$CONTAINER" python3 - << 'PYEOF'
import sys, shutil
from pathlib import Path

TARGET = Path("/app/app/agent_client.py")
BACKUP = Path("/app/app/agent_client.py.bak_vision")

shutil.copy(TARGET, BACKUP)
print(f"  Backup: {BACKUP}")

src = TARGET.read_text(encoding="utf-8")

# Sostituisci il blocco DEFAULT_AGENTS con lista vuota
# Pattern: tutto tra "DEFAULT_AGENTS = [" e il "]" di chiusura del blocco
import re

OLD_BLOCK = re.compile(
    r'DEFAULT_AGENTS\s*=\s*\[.*?^\]',
    re.DOTALL | re.MULTILINE
)

NEW_BLOCK = (
    "DEFAULT_AGENTS = []  "
    "# nik29-images rimosso: usa GPT-4o vision direttamente via vision_chat_patch.py"
)

new_src, n = OLD_BLOCK.subn(NEW_BLOCK, src, count=1)
if n == 0:
    print("  ATTENZIONE: pattern DEFAULT_AGENTS non trovato — file invariato.")
    sys.exit(0)

TARGET.write_text(new_src, encoding="utf-8")
print(f"  Sostituito DEFAULT_AGENTS con lista vuota ({n} occorrenza/e).")

# Verifica che non ci siano più riferimenti a :4002
remaining = new_src.count("4002")
if remaining:
    print(f"  ATTENZIONE: ancora {remaining} occorrenza/e di '4002' nel file.")
else:
    print("  Verifica OK: nessun riferimento a 4002 rimasto.")
PYEOF

# -------------------------------------------------------
# 3. Assicura che coordinator.py abbia import + chiamata
# -------------------------------------------------------
echo "[3/4] Verifica/applica patch coordinator.py..."

docker exec "$CONTAINER" python3 - << 'PYEOF'
import re, sys, shutil
from pathlib import Path

TARGET = Path("/app/app/coordinator.py")
BACKUP = Path("/app/app/coordinator.py.bak_vision")

src = TARGET.read_text(encoding="utf-8")

# --- Import ---
IMPORT_LINE = "from app.vision_chat_patch import process_images_in_message"
if IMPORT_LINE not in src:
    src = src.replace(
        "from openai import AsyncOpenAI",
        "from openai import AsyncOpenAI\n" + IMPORT_LINE,
        1
    )
    print("  Import aggiunto.")
else:
    print("  Import già presente.")

# --- Chiamata ---
CALL_MARKER = "process_images_in_message(self.client"
if CALL_MARKER not in src:
    shutil.copy(TARGET, BACKUP)
    print(f"  Backup: {BACKUP}")

    # Strategia A: riga semplice "content = user_message + file_info"
    PATTERN_A = re.compile(r'^(\s*)content = user_message \+ file_info\s*$', re.MULTILINE)
    def insert_call_a(m):
        indent = m.group(1)
        return (
            f"{indent}user_message = await process_images_in_message("
            f"self.client, user_message, uploaded_files)\n"
            f"{m.group(0)}"
        )
    new_src, n = PATTERN_A.subn(insert_call_a, src, count=1)

    if n == 0:
        # Strategia B: blocco vision già presente (struttura con image_parts)
        PATTERN_B_START = re.compile(r'^\s*# Gestisci file caricati', re.MULTILINE)
        PATTERN_B_END   = re.compile(r'^\s*# (Loop di esecuzione|=== PLANNER|Classifica il messaggio)', re.MULTILINE)
        lines = src.splitlines(keepends=True)
        start_idx = end_idx = None
        for i, line in enumerate(lines):
            if PATTERN_B_START.match(line) and start_idx is None:
                start_idx = i
            elif start_idx is not None and PATTERN_B_END.match(line):
                end_idx = i
                break
        if start_idx is not None and end_idx is not None:
            ind = "        "
            new_block = [
                f"{ind}# Gestisci file caricati (vision via GPT-4o)\n",
                f"{ind}file_info = \"\"\n",
                f"{ind}if uploaded_files:\n",
                f"{ind}    for f in uploaded_files:\n",
                f"{ind}        file_info += f\"\\n[File caricato: {{f.get('name','unknown')}} -> workspace/{{f.get('name','')}}]\"\n",
                f"\n",
                f"{ind}# Analisi visiva GPT-4o (se ci sono immagini)\n",
                f"{ind}user_message = await process_images_in_message(self.client, user_message, uploaded_files)\n",
                f"\n",
                f"{ind}# Aggiungi messaggio utente\n",
                f"{ind}content = user_message + file_info\n",
                f"{ind}messages.append({{\"role\": \"user\", \"content\": content}})\n",
                f"\n",
            ]
            new_src = "".join(lines[:start_idx] + new_block + lines[end_idx:])
            n = 1
            print("  Chiamata inserita con Strategia B (blocco vision sostituito).")
        else:
            print("  ERRORE: nessuna strategia applicabile per la chiamata.")
            sys.exit(1)
    else:
        print("  Chiamata inserita con Strategia A.")

    TARGET.write_text(new_src, encoding="utf-8")
else:
    print("  Chiamata già presente.")

# Verifica finale
final = TARGET.read_text(encoding="utf-8")
count = final.count("process_images_in_message")
print(f"  Verifica: 'process_images_in_message' presente {count} volte. OK.")
PYEOF

# -------------------------------------------------------
# 4. Riavvia il container
# -------------------------------------------------------
echo "[4/4] Riavvio container $CONTAINER..."
docker restart "$CONTAINER"

echo ""
echo "=== Completato ==="
echo "GPT-4o vision attivo. nik29-images/4002 rimosso."
echo ""
echo "Log: docker logs $CONTAINER --tail 30"
