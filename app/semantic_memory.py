import os
import json
import logging
import math
from datetime import datetime, timezone
from openai import AsyncOpenAI

logger = logging.getLogger("semantic_memory")

# Usa il path corretto per la memoria: /data/memory (non /app/data/memory)
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
EMBEDDINGS_FILE = os.path.join(MEMORY_DIR, "embeddings.json")

# Inizializza il client OpenAI asincrono
client = AsyncOpenAI()

def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Calcola la cosine similarity tra due vettori."""
    try:
        import numpy as np
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    except ImportError:
        # Fallback se numpy non è disponibile
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

def _read_json_safe(filepath: str, default=None) -> dict | list:
    """Legge un file JSON in modo sicuro."""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning(f"Errore lettura {filepath}: {e}")
    return default

def _save_json_safe(filepath: str, data) -> bool:
    """Salva un file JSON in modo atomico."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
        return True
    except OSError as e:
        logger.error(f"Errore salvataggio {filepath}: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False

async def embed_text(text: str) -> list[float]:
    """Genera l'embedding per un testo usando OpenAI."""
    try:
        response = await client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Errore generazione embedding: {e}")
        return []

async def save_memory_semantic(text: str, metadata: dict = None) -> bool:
    """Genera l'embedding e salva la memoria nel file embeddings.json."""
    if not text.strip():
        return False
        
    embedding = await embed_text(text)
    if not embedding:
        return False
        
    data = _read_json_safe(EMBEDDINGS_FILE, {"embeddings": []})
    embeddings_list = data.get("embeddings", [])
    
    import uuid
    new_entry = {
        "id": str(uuid.uuid4())[:8],
        "text": text,
        "embedding": embedding,
        "metadata": metadata or {"timestamp": datetime.now(timezone.utc).isoformat()}
    }
    
    embeddings_list.append(new_entry)
    data["embeddings"] = embeddings_list
    
    return _save_json_safe(EMBEDDINGS_FILE, data)

async def search_memory_semantic(query: str, top_k: int = 5) -> list[dict]:
    """Cerca le memorie più simili alla query usando cosine similarity."""
    if not query.strip():
        return []
        
    query_embedding = await embed_text(query)
    if not query_embedding:
        return []
        
    data = _read_json_safe(EMBEDDINGS_FILE, {"embeddings": []})
    embeddings_list = data.get("embeddings", [])
    
    if not embeddings_list:
        return []
        
    results = []
    for entry in embeddings_list:
        if "embedding" in entry and entry["embedding"]:
            score = _cosine_similarity(query_embedding, entry["embedding"])
            results.append({
                "id": entry.get("id"),
                "text": entry.get("text"),
                "metadata": entry.get("metadata", {}),
                "score": score
            })
            
    # Ordina per score decrescente
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]

async def reindex_all() -> int:
    """
    Legge facts.json, preferences.json, lessons.json e self_rules.json 
    (da /data/memory) e genera embeddings per tutte le memorie non indicizzate.
    """
    indexed_count = 0
    
    # Carica le memorie semantiche esistenti per evitare duplicati
    sem_data = _read_json_safe(EMBEDDINGS_FILE, {"embeddings": []})
    existing_texts = {e.get("text", "") for e in sem_data.get("embeddings", [])}
    
    texts_to_index = []
    
    # 1. Leggi facts.json
    facts_file = os.path.join(MEMORY_DIR, "facts.json")
    facts_data = _read_json_safe(facts_file, {"facts": []})
    for f in facts_data.get("facts", []):
        text = f.get("fact", "")
        if text and text not in existing_texts:
            texts_to_index.append({
                "text": text,
                "metadata": {
                    "source": "facts.json",
                    "category": f.get("category", "general")
                }
            })
            
    # 2. Leggi preferences.json
    prefs_file = os.path.join(MEMORY_DIR, "preferences.json")
    prefs_data = _read_json_safe(prefs_file, {"preferences": {}})
    for key, val in prefs_data.get("preferences", {}).items():
        value_str = val.get("value", val) if isinstance(val, dict) else str(val)
        text = f"Preferenza {key}: {value_str}"
        if text and text not in existing_texts:
            texts_to_index.append({
                "text": text,
                "metadata": {
                    "source": "preferences.json",
                    "key": key
                }
            })
            
    # 3. Leggi lessons.json
    lessons_file = os.path.join(MEMORY_DIR, "lessons.json")
    lessons_data = _read_json_safe(lessons_file, {"lessons": []})
    for l in lessons_data.get("lessons", []):
        lesson_text = l.get("lesson", "")
        context = l.get("context", "")
        text = f"Lezione [{l.get('category', 'general')}]: {lesson_text}"
        if context:
            text += f" (Contesto: {context})"
        if lesson_text and text not in existing_texts:
            texts_to_index.append({
                "text": text,
                "metadata": {
                    "source": "lessons.json",
                    "category": l.get("category", "general")
                }
            })
            
    # 4. Leggi self_rules.json
    rules_file = os.path.join(MEMORY_DIR, "self_rules.json")
    rules_data = _read_json_safe(rules_file, {"rules": []})
    for r in rules_data.get("rules", []):
        rule_text = r.get("rule", r) if isinstance(r, dict) else str(r)
        text = f"Regola: {rule_text}"
        if rule_text and text not in existing_texts:
            texts_to_index.append({
                "text": text,
                "metadata": {
                    "source": "self_rules.json"
                }
            })
            
    # Processa in batch per evitare rate limit
    batch_size = 20
    for i in range(0, len(texts_to_index), batch_size):
        batch = texts_to_index[i:i+batch_size]
        for item in batch:
            success = await save_memory_semantic(item["text"], item["metadata"])
            if success:
                indexed_count += 1
                
    return indexed_count
