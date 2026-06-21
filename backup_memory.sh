#!/bin/bash
# ============================================================
# backup_memory.sh - Backup memorie nik29 con retry
# 
# - Copia i file di memoria nella cartella /backups/
# - Pusha su GitHub
# - Se non c'è internet, riprova ogni 5 minuti finché non riesce
# ============================================================

MEMORY_DIR="/data/memory"
REPO_DIR="/app"
BACKUP_DIR="${REPO_DIR}/backups"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
DATE=$(date +%Y-%m-%d)
RETRY_INTERVAL=300  # 5 minuti

echo "[BACKUP] Inizio backup memorie - ${TIMESTAMP}"

# Crea la cartella backups se non esiste
mkdir -p "${BACKUP_DIR}"

# Copia tutti i file di memoria
echo "[BACKUP] Copio file di memoria..."
for file in facts.json preferences.json lessons.json self_rules.json summaries.json projects.json istruzioni.md semantic_index.json; do
    if [ -f "${MEMORY_DIR}/${file}" ]; then
        cp "${MEMORY_DIR}/${file}" "${BACKUP_DIR}/${file}"
        echo "  - ${file}"
    fi
done

# Embeddings
if [ -f "${MEMORY_DIR}/embeddings.npy" ]; then
    cp "${MEMORY_DIR}/embeddings.npy" "${BACKUP_DIR}/embeddings.npy"
    echo "  - embeddings.npy"
fi

# Conversazioni (ultime 20)
if [ -d "${MEMORY_DIR}/conversations" ]; then
    mkdir -p "${BACKUP_DIR}/conversations"
    ls -t "${MEMORY_DIR}/conversations/"*.json 2>/dev/null | head -20 | while read f; do
        cp "$f" "${BACKUP_DIR}/conversations/$(basename $f)"
    done
    echo "  - conversazioni copiate"
fi

# Timestamp ultimo backup
echo "${TIMESTAMP}" > "${BACKUP_DIR}/last_backup.txt"
echo "[BACKUP] File copiati localmente."

# Git add + commit
cd "${REPO_DIR}"
git add backups/ 2>/dev/null || true
git commit -m "backup: memorie ${DATE}" 2>/dev/null || {
    echo "[BACKUP] Nessuna modifica (memorie invariate). Fine."
    exit 0
}

# Push con retry infinito finché non riesce
echo "[BACKUP] Tentativo push su GitHub..."
while true; do
    if git push origin HEAD 2>/dev/null; then
        echo "[BACKUP] Push completato! Memorie al sicuro su GitHub."
        exit 0
    fi
    echo "[BACKUP] Push fallito (no internet?). Riprovo tra 5 minuti..."
    sleep ${RETRY_INTERVAL}
done
