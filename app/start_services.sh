#!/bin/bash
# =============================================================================
# start_services.sh — Avvia self_evolution_service in background
# =============================================================================
# Questo script viene eseguito DENTRO il container nik29-coordinator.
# Si avvia DOPO il coordinator principale.
# Se crasha, il coordinator continua a funzionare normalmente.
# =============================================================================

SERVICE_NAME="self_evolution_service"
SERVICE_PATH="/app/app/self_evolution_service.py"
LOG_FILE="/data/memory/self_evolution_service.log"
PID_FILE="/tmp/self_evolution.pid"
PORT=4005

# Crea directory necessarie
mkdir -p /app/app/tools/custom
mkdir -p /data/memory

# Verifica che il file esista
if [ ! -f "$SERVICE_PATH" ]; then
    echo "[start_services] ✗ File non trovato: $SERVICE_PATH"
    exit 1
fi

# Controlla se è già in esecuzione
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[start_services] Servizio già in esecuzione (PID: $OLD_PID)"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Controlla se la porta è già occupata
if command -v ss > /dev/null 2>&1; then
    if ss -tlnp | grep -q ":${PORT} "; then
        echo "[start_services] ⚠ Porta ${PORT} già occupata"
        exit 0
    fi
elif command -v netstat > /dev/null 2>&1; then
    if netstat -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        echo "[start_services] ⚠ Porta ${PORT} già occupata"
        exit 0
    fi
fi

# Attendi che il coordinator sia pronto (max 30s)
echo "[start_services] Attendo che il coordinator sia pronto..."
WAITED=0
while [ $WAITED -lt 30 ]; do
    if curl -sf http://localhost:4001/health > /dev/null 2>&1; then
        echo "[start_services] ✓ Coordinator pronto"
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge 30 ]; then
    echo "[start_services] ⚠ Coordinator non risponde, avvio comunque self_evolution"
fi

# Avvia il servizio in background con restart automatico
echo "[start_services] Avvio ${SERVICE_NAME} sulla porta ${PORT}..."

(
    while true; do
        echo "[$(date)] Avvio self_evolution_service..." >> "$LOG_FILE"
        python3 "$SERVICE_PATH" >> "$LOG_FILE" 2>&1
        EXIT_CODE=$?
        echo "[$(date)] Servizio terminato con codice ${EXIT_CODE}" >> "$LOG_FILE"

        # Se esce con 0, è stato fermato intenzionalmente
        if [ $EXIT_CODE -eq 0 ]; then
            echo "[$(date)] Arresto pulito, non riavvio." >> "$LOG_FILE"
            break
        fi

        # Attendi prima di riavviare (backoff)
        echo "[$(date)] Riavvio tra 5 secondi..." >> "$LOG_FILE"
        sleep 5
    done
) &

# Salva PID del processo wrapper
WRAPPER_PID=$!
echo "$WRAPPER_PID" > "$PID_FILE"

# Attendi che la porta sia attiva
sleep 3
READY=false
for i in $(seq 1 10); do
    if curl -sf http://localhost:${PORT}/health > /dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 1
done

if [ "$READY" = true ]; then
    echo "[start_services] ✓ ${SERVICE_NAME} attivo su porta ${PORT} (PID: ${WRAPPER_PID})"
else
    echo "[start_services] ⚠ ${SERVICE_NAME} avviato ma non ancora raggiungibile"
    echo "  Controlla: tail -f ${LOG_FILE}"
fi
