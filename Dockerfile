FROM python:3.11-slim
WORKDIR /app
# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*
# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copia il codice applicazione
COPY app/ ./app/
COPY config/ ./config/
COPY manifest.json .
COPY static/ ./static/
# Crea directory per dati persistenti
RUN mkdir -p /data/memory /data/workspace
# Esponi porta
EXPOSE 4001
# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:4001/health || exit 1
# Avvia l'applicazione
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4001", "--ws-ping-interval", "30", "--ws-ping-timeout", "60"]
