#!/bin/bash
# fix_vision_patch.sh
# Inserisce la chiamata a process_images_in_message() in coordinator.py
# usando un patcher Python robusto (immune a variazioni di spazi/versione).

set -e

CONTAINER="nik29-coordinator"

echo "=== Fix Vision Patch per nik29-coordinator ==="
echo ""

# -------------------------------------------------------
# 1. Verifica che l'import sia già presente (deve esserlo)
# -------------------------------------------------------
echo "[1/4] Verifica import vision_chat_patch..."
IMPORT_OK=$(docker exec "$CONTAINER" grep -c "vision_chat_patch" /app/app/coordinator.py 2>/dev/null || echo "0")
if [ "$IMPORT_OK" = "0" ]; then
    echo "  ATTENZIONE: import non trovato — lo aggiungo ora..."
    docker exec "$CONTAINER" bash -c \
        "sed -i '/from openai import AsyncOpenAI/a from app.vision_chat_patch import process_images_in_message' /app/app/coordinator.py"
else
    echo "  OK: import già presente."
fi

# -------------------------------------------------------
# 2. Verifica se la chiamata è già presente
# -------------------------------------------------------
echo "[2/4] Verifica se la chiamata è già presente..."
CALL_OK=$(docker exec "$CONTAINER" grep -c "process_images_in_message" /app/app/coordinator.py 2>/dev/null || echo "0")
# L'import conta come 1 — se è > 1 la chiamata c'è già
if [ "$CALL_OK" -gt "1" ]; then
    echo "  OK: la chiamata è già presente. Niente da fare."
    echo ""
    echo "=== Patch già applicato correttamente. ==="
    exit 0
fi

# -------------------------------------------------------
# 3. Applica il patch con uno script Python nel container
#    (robusto a qualsiasi versione del file)
# -------------------------------------------------------
echo "[3/4] Applico il patch con Python patcher..."

docker exec "$CONTAINER" python3 - << 'PYEOF'
import re, sys, shutil
from pathlib import Path

TARGET = Path("/app/app/coordinator.py")
BACKUP = Path("/app/app/coordinator.py.bak_vision")

# Backup
shutil.copy(TARGET, BACKUP)
print(f"  Backup salvato in {BACKUP}")

src = TARGET.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)

# -------------------------------------------------------
# Strategia A: file con struttura semplice (main/244)
#   Cerca il pattern:
#       # Aggiungi messaggio utente
#       content = user_message + file_info
#   e inserisce PRIMA di "content = ..." la riga:
#       user_message = await process_images_in_message(self.client, user_message, uploaded_files)
# -------------------------------------------------------
PATTERN_A = re.compile(r'^(\s*)content = user_message \+ file_info\s*$')

# -------------------------------------------------------
# Strategia B: file con struttura vision (00264588b9)
#   Cerca il pattern:
#       if image_parts:
#   che indica che c'è già un blocco vision ma usa GPT-4.1.
#   In questo caso sostituiamo l'intera logica vision con
#   la nostra (che usa GPT-4o).
# -------------------------------------------------------
PATTERN_B_START = re.compile(r'^\s*# Gestisci file caricati')
PATTERN_B_END   = re.compile(r'^\s*# (Loop di esecuzione|=== PLANNER|Classifica il messaggio)')

# --- Prova Strategia A ---
patched_lines = []
applied = False
for i, line in enumerate(lines):
    m = PATTERN_A.match(line)
    if m and not applied:
        indent = m.group(1)
        # Inserisci la chiamata PRIMA della riga "content = ..."
        patched_lines.append(
            f"{indent}user_message = await process_images_in_message(self.client, user_message, uploaded_files)\n"
        )
        patched_lines.append(line)
        applied = True
        print(f"  Strategia A: inserita riga prima della riga {i+1}")
    else:
        patched_lines.append(line)

if not applied:
    print("  Strategia A non applicabile — provo Strategia B...")
    # --- Prova Strategia B ---
    # Trova il blocco "Gestisci file caricati" e sostituiscilo tutto
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if PATTERN_B_START.match(line) and start_idx is None:
            start_idx = i
        elif start_idx is not None and PATTERN_B_END.match(line):
            end_idx = i
            break

    if start_idx is not None and end_idx is not None:
        indent = "        "  # 8 spazi (dentro metodo di classe)
        new_block = [
            f"{indent}# Gestisci file caricati (vision via GPT-4o)\n",
            f"{indent}file_info = \"\"\n",
            f"{indent}if uploaded_files:\n",
            f"{indent}    for f in uploaded_files:\n",
            f"{indent}        file_info += f\"\\n[File caricato: {{f.get('name', 'unknown')}} -> workspace/{{f.get('name', '')}}]\"\n",
            f"\n",
            f"{indent}# Analisi visiva immagini con GPT-4o (se presenti)\n",
            f"{indent}user_message = await process_images_in_message(self.client, user_message, uploaded_files)\n",
            f"\n",
            f"{indent}# Aggiungi messaggio utente\n",
            f"{indent}content = user_message + file_info\n",
            f"{indent}messages.append({{\"role\": \"user\", \"content\": content}})\n",
            f"\n",
        ]
        patched_lines = lines[:start_idx] + new_block + lines[end_idx:]
        applied = True
        print(f"  Strategia B: sostituito blocco righe {start_idx+1}-{end_idx}")
    else:
        print("  ERRORE: nessuna strategia applicabile. File invariato.")
        sys.exit(1)

TARGET.write_text("".join(patched_lines), encoding="utf-8")
print("  File scritto con successo.")

# Verifica finale
result = TARGET.read_text(encoding="utf-8")
if "process_images_in_message" in result:
    count = result.count("process_images_in_message")
    print(f"  Verifica OK: 'process_images_in_message' trovato {count} volte nel file.")
else:
    print("  ERRORE: patch non trovato nel file scritto!")
    sys.exit(1)
PYEOF

# -------------------------------------------------------
# 4. Riavvia il container
# -------------------------------------------------------
echo "[4/4] Riavvio container $CONTAINER..."
docker restart "$CONTAINER"

echo ""
echo "=== Patch applicato con successo! ==="
echo "Ora quando carichi un'immagine nella chat, nik29 la analizza con GPT-4o."
echo ""
echo "Per verificare i log: docker logs $CONTAINER --tail 30"
