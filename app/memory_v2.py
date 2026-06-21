"""
memory_v2.py - Upgrade del sistema memoria per nik29-coordinator v0.5.1
Aggiunge il sistema "Lessons Learned" al modulo memoria esistente.

Questo file viene importato dal coordinator_patch per estendere le funzionalità
di memoria senza sovrascrivere il file originale memory.py.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

# Percorsi file
LESSONS_FILE = "/data/memory/lessons.json"
SELF_RULES_FILE = "/data/memory/self_rules.json"

# Categorie valide per le lezioni
VALID_CATEGORIES = ["errore", "soluzione", "preferenza", "procedura"]


def _ensure_dir(filepath: str) -> None:
    """Assicura che la directory del file esista."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)


def _load_json_safe(filepath: str, default: dict) -> dict:
    """
    Carica un file JSON in modo sicuro.
    Se il file non esiste, è corrotto o vuoto, ritorna il default e ricrea il file.
    """
    _ensure_dir(filepath)
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validazione base della struttura
            if not isinstance(data, dict):
                raise ValueError("Struttura JSON non valida")
            return data
    except (json.JSONDecodeError, ValueError, OSError):
        # File corrotto - ricrea con default
        pass

    # Crea/ricrea il file con il default
    _save_json_safe(filepath, default)
    return default.copy()


def _save_json_safe(filepath: str, data: dict) -> None:
    """Salva un file JSON in modo atomico (write + rename)."""
    _ensure_dir(filepath)
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
    except OSError as e:
        # Fallback: scrittura diretta
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            raise RuntimeError(f"Impossibile salvare {filepath}: {e}")


# ============================================================
# LESSONS LEARNED SYSTEM
# ============================================================

async def save_lesson(category: str, lesson: str, context: str = "") -> str:
    """
    Salva una nuova lezione appresa.
    
    Args:
        category: Una tra "errore", "soluzione", "preferenza", "procedura"
        lesson: Il contenuto della lezione
        context: Contesto opzionale (cosa stava succedendo)
    
    Returns:
        Stringa con conferma e ID della lezione salvata
    """
    if category not in VALID_CATEGORIES:
        return f"❌ Categoria non valida: '{category}'. Usa: {', '.join(VALID_CATEGORIES)}"

    if not lesson.strip():
        return "❌ La lezione non può essere vuota."

    data = _load_json_safe(LESSONS_FILE, {"lessons": []})

    new_lesson = {
        "id": str(uuid.uuid4())[:8],
        "date": datetime.now().isoformat(),
        "category": category,
        "lesson": lesson.strip(),
        "context": context.strip(),
        "times_used": 0
    }

    data["lessons"].append(new_lesson)
    _save_json_safe(LESSONS_FILE, data)

    return f"✅ Lezione salvata [{category}] ID: {new_lesson['id']}\n📝 {lesson[:100]}"


async def get_lessons(category: Optional[str] = None, limit: int = 10) -> str:
    """
    Recupera le lezioni, opzionalmente filtrate per categoria.
    
    Args:
        category: Filtra per categoria (opzionale)
        limit: Numero massimo di lezioni da restituire
    
    Returns:
        Stringa formattata con le lezioni trovate
    """
    data = _load_json_safe(LESSONS_FILE, {"lessons": []})
    lessons = data.get("lessons", [])

    if category:
        if category not in VALID_CATEGORIES:
            return f"❌ Categoria non valida: '{category}'. Usa: {', '.join(VALID_CATEGORIES)}"
        lessons = [l for l in lessons if l.get("category") == category]

    # Ordina per data (più recenti prima)
    lessons.sort(key=lambda x: x.get("date", ""), reverse=True)
    lessons = lessons[:limit]

    if not lessons:
        msg = f"Nessuna lezione trovata"
        if category:
            msg += f" nella categoria '{category}'"
        return msg

    result_lines = [f"📚 Lezioni trovate: {len(lessons)}"]
    for l in lessons:
        used = f" (usata {l['times_used']}x)" if l.get("times_used", 0) > 0 else ""
        result_lines.append(
            f"\n[{l['category'].upper()}] {l['lesson']}"
            f"\n  ID: {l['id']} | Data: {l['date'][:10]}{used}"
        )
        if l.get("context"):
            result_lines.append(f"  Contesto: {l['context'][:80]}")

    return "\n".join(result_lines)


async def search_lessons(query: str) -> str:
    """
    Cerca lezioni per parole chiave (case-insensitive).
    
    Args:
        query: Testo da cercare nelle lezioni
    
    Returns:
        Stringa con le lezioni che contengono la query
    """
    if not query.strip():
        return "❌ Specifica una query di ricerca."

    data = _load_json_safe(LESSONS_FILE, {"lessons": []})
    lessons = data.get("lessons", [])
    query_lower = query.lower()

    matches = []
    for l in lessons:
        searchable = f"{l.get('lesson', '')} {l.get('context', '')} {l.get('category', '')}".lower()
        if query_lower in searchable:
            matches.append(l)

    if not matches:
        return f"Nessuna lezione trovata per: '{query}'"

    result_lines = [f"🔍 Trovate {len(matches)} lezioni per '{query}':"]
    for l in matches[:10]:
        result_lines.append(
            f"\n[{l['category'].upper()}] {l['lesson']}"
            f"\n  ID: {l['id']} | Data: {l['date'][:10]}"
        )

    return "\n".join(result_lines)


async def increment_lesson_usage(lesson_id: str) -> str:
    """
    Incrementa il contatore di utilizzo di una lezione.
    
    Args:
        lesson_id: ID della lezione da aggiornare
    
    Returns:
        Stringa con conferma dell'aggiornamento
    """
    if not lesson_id.strip():
        return "❌ Specifica un ID lezione."

    data = _load_json_safe(LESSONS_FILE, {"lessons": []})

    for lesson in data.get("lessons", []):
        if lesson.get("id") == lesson_id:
            lesson["times_used"] = lesson.get("times_used", 0) + 1
            _save_json_safe(LESSONS_FILE, data)
            return f"✅ Lezione {lesson_id} aggiornata: usata {lesson['times_used']} volte"

    return f"❌ Lezione con ID '{lesson_id}' non trovata."


# ============================================================
# CONTEXT BUILDER - Per il system prompt del coordinator
# ============================================================

def get_lessons_context(max_lessons: int = 5) -> str:
    """
    Genera un blocco di contesto con le lezioni più rilevanti
    da includere nel system prompt del coordinator.
    
    Returns:
        Stringa formattata per il system prompt
    """
    data = _load_json_safe(LESSONS_FILE, {"lessons": []})
    lessons = data.get("lessons", [])

    if not lessons:
        return ""

    # Prendi le lezioni più usate + le più recenti
    by_usage = sorted(lessons, key=lambda x: x.get("times_used", 0), reverse=True)[:3]
    by_date = sorted(lessons, key=lambda x: x.get("date", ""), reverse=True)[:3]

    # Unisci senza duplicati
    seen_ids = set()
    selected = []
    for l in by_usage + by_date:
        if l["id"] not in seen_ids and len(selected) < max_lessons:
            seen_ids.add(l["id"])
            selected.append(l)

    if not selected:
        return ""

    lines = ["\n## Lezioni Apprese (memoria a lungo termine)"]
    for l in selected:
        lines.append(f"- [{l['category']}] {l['lesson']}")

    return "\n".join(lines)


def get_rules_context() -> str:
    """
    Genera un blocco di contesto con le regole auto-imposte
    da includere nel system prompt del coordinator.
    
    Returns:
        Stringa formattata per il system prompt
    """
    data = _load_json_safe(SELF_RULES_FILE, {"rules": []})
    rules = data.get("rules", [])

    if not rules:
        return ""

    lines = ["\n## Regole Auto-imposte"]
    for r in rules:
        lines.append(f"- {r['rule']}")

    return "\n".join(lines)


def get_full_memory_context() -> str:
    """
    Genera il contesto completo di memoria (lezioni + regole)
    per il system prompt.
    """
    parts = []

    lessons_ctx = get_lessons_context()
    if lessons_ctx:
        parts.append(lessons_ctx)

    rules_ctx = get_rules_context()
    if rules_ctx:
        parts.append(rules_ctx)

    if parts:
        return "\n" + "\n".join(parts) + "\n"
    return ""
