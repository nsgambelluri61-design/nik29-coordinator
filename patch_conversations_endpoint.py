"""
Patch per nik29-coordinator main.py:
Aggiunge l'endpoint GET /conversations/{conversation_id}
che restituisce la cronologia di una conversazione salvata.

Uso: docker exec nik29-coordinator python3 /app/patch_conversations_endpoint.py
"""
import os
import re

MAIN_PY = "/app/main.py"

# Leggi il file attuale
with open(MAIN_PY, "r", encoding="utf-8") as f:
    content = f.read()

# Controlla se l'endpoint esiste gia'
if '/conversations/' in content and 'get_conversation' in content:
    print("[OK] Endpoint /conversations/ gia' presente in main.py")
    exit(0)

# Il codice dell'endpoint da aggiungere
ENDPOINT_CODE = '''

# === PATCH: endpoint per recuperare cronologia conversazione ===
@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Restituisce la cronologia di una conversazione per il frontend."""
    import json
    from pathlib import Path
    from fastapi.responses import JSONResponse
    
    # Percorso file conversazione
    conv_dir = Path("/data/memory/conversations")
    conv_file = conv_dir / f"{conversation_id}.json"
    
    if not conv_file.exists():
        return JSONResponse({"conversation_id": conversation_id, "messages": []})
    
    try:
        with open(conv_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # data puo' essere una lista di messaggi o un dict con chiave "messages"
        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = data.get("messages", data.get("history", []))
        else:
            messages = []
        
        # Filtra solo messaggi user e assistant con contenuto
        chat_messages = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            
            # Salta system, tool, function messages
            if role not in ("user", "assistant"):
                continue
            
            # Salta messaggi vuoti
            if not content:
                continue
            
            # Se content e' una lista (multi-modal), estrai il testo
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                content = "\\n".join(text_parts)
                if not content:
                    continue
            
            chat_messages.append({
                "role": role,
                "content": content
            })
        
        return {"conversation_id": conversation_id, "messages": chat_messages}
    
    except (json.JSONDecodeError, IOError) as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Errore lettura conversazione: {str(e)}"}
        )
# === FINE PATCH ===
'''

# Strategia: inserire l'endpoint prima dell'ultimo blocco (if __name__ o uvicorn.run)
# oppure prima del primo @app.websocket se non c'e' if __name__

# Cerca il punto migliore per inserire
insertion_point = None

# Opzione 1: prima di "if __name__"
if_main_match = re.search(r'\nif\s+__name__\s*==\s*["\']__main__["\']', content)
if if_main_match:
    insertion_point = if_main_match.start()

# Opzione 2: prima di uvicorn.run (se non c'e' if __name__)
if insertion_point is None:
    uvicorn_match = re.search(r'\nuvicorn\.run\(', content)
    if uvicorn_match:
        insertion_point = uvicorn_match.start()

# Opzione 3: alla fine del file
if insertion_point is None:
    insertion_point = len(content)

# Inserisci il codice
content = content[:insertion_point] + ENDPOINT_CODE + content[insertion_point:]

# Assicurati che JSONResponse sia importato
if 'from fastapi.responses import JSONResponse' not in content:
    # Aggiungi import dopo "from fastapi import"
    fastapi_import = re.search(r'from fastapi import [^\n]+', content)
    if fastapi_import:
        insert_after = fastapi_import.end()
        content = content[:insert_after] + '\nfrom fastapi.responses import JSONResponse' + content[insert_after:]
    else:
        # Fallback: aggiungi in cima
        content = 'from fastapi.responses import JSONResponse\n' + content

# Scrivi il file modificato
with open(MAIN_PY, "w", encoding="utf-8") as f:
    f.write(content)

print("[OK] Endpoint /conversations/{conversation_id} aggiunto a main.py")
print("[INFO] Riavvia il container: docker restart nik29-coordinator")
