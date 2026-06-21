#!/bin/bash
# Avvia self_evolution in background (non blocca il container)
nohup /app/app/start_services.sh > /dev/null 2>&1 &
