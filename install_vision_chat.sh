#!/bin/bash

echo "Installazione patch GPT-4o Vision per nik29-coordinator..."

# 1. Copia il file patch nel container
docker cp vision_chat_patch.py nik29-coordinator:/app/app/vision_chat_patch.py

# 2. Patch coordinator.py
echo "Patching coordinator.py..."
docker exec nik29-coordinator bash -c '
# Aggiungi import in cima se non c è
if ! grep -q "from app.vision_chat_patch import process_images_in_message" /app/app/coordinator.py; then
    sed -i "/from openai import AsyncOpenAI/a from app.vision_chat_patch import process_images_in_message" /app/app/coordinator.py
fi

# Trova la linea "content = user_message + file_info" e modificala
# per intercettare le immagini
if ! grep -q "user_message = await process_images_in_message" /app/app/coordinator.py; then
    sed -i "s/content = user_message + file_info/user_message = await process_images_in_message(self.client, user_message, uploaded_files)\n        content = user_message + file_info/" /app/app/coordinator.py
fi
'

echo "Riavvio container nik29-coordinator..."
docker restart nik29-coordinator

echo "Patch installato con successo!"
echo "Ora quando carichi un'immagine nella chat, il coordinatore userà GPT-4o per vederla."
