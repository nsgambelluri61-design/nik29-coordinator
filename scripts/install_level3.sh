#!/bin/bash
# =============================================================================
# INSTALL LEVEL 3 AUTONOMY PACKAGE
# =============================================================================
# Uso: ./scripts/install_level3.sh
# Esegui dalla root del progetto nik29-coordinator
# =============================================================================

set -e

echo "🚀 Installazione Level 3 Autonomy Package per nik29-coordinator"
echo "================================================================"

# Check we're in the right directory
if [ ! -f "docker-compose.yml" ] && [ ! -f "docker-compose.yaml" ]; then
    echo "❌ Errore: esegui questo script dalla directory root di nik29-coordinator"
    echo "   cd ~/nik29-coordinator && ./scripts/install_level3.sh"
    exit 1
fi

echo ""
echo "📁 Step 1: Creazione directory..."
mkdir -p app/tools
mkdir -p app/monitoring
mkdir -p app/scheduler
mkdir -p data/monitoring
mkdir -p data/scheduler

echo "✅ Directory create"

echo ""
echo "📄 Step 2: Copia file Python..."

# Copy tool files (only if they don't exist or force overwrite)
for dir in "app/tools" "app/monitoring" "app/scheduler"; do
    if [ -d "../nik29-level3/$dir" ]; then
        cp -v ../nik29-level3/$dir/*.py $dir/ 2>/dev/null || true
    fi
done

echo "✅ File Python copiati"

echo ""
echo "📄 Step 3: Copia file dati..."
# Only copy if not already existing (don't overwrite user data)
if [ ! -f "data/scheduler/tasks.json" ]; then
    cp -v ../nik29-level3/data/scheduler/tasks.json data/scheduler/
    echo "✅ tasks.json creato con 3 task predefiniti"
else
    echo "⚠️  tasks.json esiste già — non sovrascritto"
fi

if [ ! -f "data/monitoring/health_log.json" ]; then
    cp -v ../nik29-level3/data/monitoring/health_log.json data/monitoring/
    echo "✅ health_log.json creato"
else
    echo "⚠️  health_log.json esiste già — non sovrascritto"
fi

echo ""
echo "📦 Step 4: Aggiornamento requirements.txt..."
# Append new dependencies if not already present
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    # Extract package name (before >=)
    pkg=$(echo "$line" | cut -d'>' -f1 | cut -d'=' -f1 | xargs)
    if ! grep -qi "^$pkg" requirements.txt 2>/dev/null; then
        echo "$line" >> requirements.txt
        echo "  + Aggiunto: $line"
    else
        echo "  ✓ Già presente: $pkg"
    fi
done < ../nik29-level3/requirements_level3.txt

echo "✅ requirements.txt aggiornato"

echo ""
echo "================================================================"
echo "✅ FILE INSTALLATI!"
echo ""
echo "⚠️  PASSI MANUALI RIMANENTI:"
echo ""
echo "1. Modifica app/coordinator.py seguendo PATCH_COORDINATOR.py"
echo "   (aggiungi import, registra tool, avvia servizi)"
echo ""
echo "2. Modifica docker-compose.yml seguendo PATCH_DOCKER_COMPOSE.yml"
echo "   (aggiungi volumi e variabili ambiente)"
echo ""
echo "3. Aggiungi BRAVE_API_KEY al tuo .env:"
echo "   echo 'BRAVE_API_KEY=la_tua_chiave' >> .env"
echo ""
echo "4. Rebuild e restart:"
echo "   docker compose build && docker compose up -d"
echo ""
echo "================================================================"
echo "🎉 Level 3 Autonomy pronto!"
