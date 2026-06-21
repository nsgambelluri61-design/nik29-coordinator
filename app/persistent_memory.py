"""
persistent_memory.py - Sistema di memoria persistente automatica per nik29-coordinator.

Carica automaticamente all'inizio di ogni sessione:
- istruzioni.md (istruzioni personalizzate)
- facts.json (fatti sull'utente)
- preferences.json (preferenze utente)
- lessons.json (lezioni apprese)
- self_rules.json (regole auto-imposte)
- Riassunti delle ultime 2-3 conversazioni

Inietta tutto nel system prompt come sezione <persistent_memory>.
Auto-salva nuovi apprendimenti alla fine di ogni conversazione.
"""

import os
import json
import asyncio
from app.semantic_memory import save_memory_semantic

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("persistent_memory")

# Percorsi file memoria
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
FACTS_FILE = os.path.join(MEMORY_DIR, "facts.json")
PREFERENCES_FILE = os.path.join(MEMORY_DIR, "preferences.json")
LESSONS_FILE = os.path.join(MEMORY_DIR, "lessons.json")
SELF_RULES_FILE = os.path.join(MEMORY_DIR, "self_rules.json")
INSTRUCTIONS_FILE = os.path.join(MEMORY_DIR, "istruzioni.md")
CONVERSATIONS_DIR = os.path.join(MEMORY_DIR, "conversations")
SUMMARIES_FILE = os.path.join(MEMORY_DIR, "summaries.json")


def _read_json_safe(filepath: str, default=None) -> dict | list:
    """Legge un file JSON in modo sicuro. Ritorna default se non esiste o è corrotto."""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning(f"Errore lettura {filepath}: {e}")
    return default


def _read_text_safe(filepath: str) -> str:
    """Legge un file di testo in modo sicuro. Ritorna stringa vuota se non esiste."""
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
    except OSError as e:
        logger.warning(f"Errore lettura {filepath}: {e}")
    return ""


def _save_json_safe(filepath: str, data) -> bool:
    """Salva un file JSON in modo atomico. Ritorna True se successo."""
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


# ============================================================
# CARICAMENTO MEMORIA PERSISTENTE
# ============================================================

def load_instructions() -> str:
    """Carica le istruzioni personalizzate da istruzioni.md."""
    content = _read_text_safe(INSTRUCTIONS_FILE)
    if content.strip():
        return content.strip()
    return ""


def load_facts() -> str:
    """Carica i fatti sull'utente da facts.json e li formatta come testo."""
    data = _read_json_safe(FACTS_FILE, {"facts": []})
    facts = data.get("facts", [])
    
    if not facts:
        return ""
    
    lines = []
    # Raggruppa per categoria
    categories = {}
    for f in facts:
        cat = f.get("category", "general")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f.get("fact", ""))
    
    for cat, items in categories.items():
        lines.append(f"**{cat}:**")
        for item in items[-10:]:  # Max 10 per categoria
            if item.strip():
                lines.append(f"- {item}")
    
    return "\n".join(lines)


def load_preferences() -> str:
    """Carica le preferenze utente da preferences.json e le formatta come testo."""
    data = _read_json_safe(PREFERENCES_FILE, {"preferences": {}})
    prefs = data.get("preferences", {})
    
    if not prefs:
        return ""
    
    lines = []
    for key, val in prefs.items():
        value = val.get("value", val) if isinstance(val, dict) else val
        lines.append(f"- **{key}**: {value}")
    
    return "\n".join(lines)


def load_lessons() -> str:
    """Carica le lezioni apprese da lessons.json e le formatta come testo."""
    data = _read_json_safe(LESSONS_FILE, {"lessons": []})
    lessons = data.get("lessons", [])
    
    if not lessons:
        return ""
    
    # Ordina: prima le più usate, poi le più recenti
    by_usage = sorted(lessons, key=lambda x: x.get("times_used", 0), reverse=True)[:5]
    by_date = sorted(lessons, key=lambda x: x.get("date", ""), reverse=True)[:5]
    
    # Unisci senza duplicati, max 8 lezioni
    seen_ids = set()
    selected = []
    for l in by_usage + by_date:
        lid = l.get("id", id(l))
        if lid not in seen_ids and len(selected) < 8:
            seen_ids.add(lid)
            selected.append(l)
    
    lines = []
    for l in selected:
        cat = l.get("category", "")
        lesson = l.get("lesson", "")
        context = l.get("context", "")
        entry = f"- [{cat}] {lesson}"
        if context:
            entry += f" (contesto: {context[:80]})"
        lines.append(entry)
    
    return "\n".join(lines)


def load_self_rules() -> str:
    """Carica le regole auto-imposte da self_rules.json e le formatta come testo."""
    data = _read_json_safe(SELF_RULES_FILE, {"rules": []})
    rules = data.get("rules", [])
    
    if not rules:
        return ""
    
    lines = []
    for r in rules:
        rule_text = r.get("rule", r) if isinstance(r, dict) else str(r)
        lines.append(f"- {rule_text}")
    
    return "\n".join(lines)


def load_recent_conversations(max_conversations: int = 3) -> str:
    """
    Carica i riassunti delle ultime 2-3 conversazioni.
    Prima prova da summaries.json, poi fallback sui file di conversazione raw.
    """
    # Strategia 1: Usa summaries.json se disponibile
    summaries_text = _load_from_summaries(max_conversations)
    if summaries_text:
        return summaries_text
    
    # Strategia 2: Fallback - leggi i file di conversazione più recenti
    return _load_from_conversation_files(max_conversations)


def _load_from_summaries(max_conversations: int) -> str:
    """Carica riassunti da summaries.json."""
    data = _read_json_safe(SUMMARIES_FILE, {"conversations": {}})
    conversations = data.get("conversations", {})
    
    if not conversations:
        return ""
    
    # Ordina per data di aggiornamento (più recenti prima)
    sorted_convs = sorted(
        conversations.items(),
        key=lambda x: x[1].get("updated_at", ""),
        reverse=True
    )[:max_conversations]
    
    if not sorted_convs:
        return ""
    
    lines = []
    for conv_id, conv_data in sorted_convs:
        topic = conv_data.get("last_topic", "Conversazione")
        key_points = conv_data.get("key_points", [])
        updated = conv_data.get("updated_at", "")[:10]
        
        lines.append(f"**{topic}** ({updated}):")
        if key_points:
            for point in key_points[-3:]:  # Max 3 punti per conversazione
                lines.append(f"  - {point}")
        else:
            lines.append("  - (nessun punto chiave salvato)")
    
    return "\n".join(lines)


def _load_from_conversation_files(max_conversations: int) -> str:
    """Fallback: legge i file di conversazione più recenti e genera un mini-riassunto."""
    if not os.path.exists(CONVERSATIONS_DIR):
        return ""
    
    # Trova i file più recenti
    conv_files = []
    try:
        for filename in os.listdir(CONVERSATIONS_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(CONVERSATIONS_DIR, filename)
                mtime = os.path.getmtime(filepath)
                conv_files.append((filepath, mtime))
    except OSError:
        return ""
    
    if not conv_files:
        return ""
    
    # Ordina per data modifica (più recenti prima)
    conv_files.sort(key=lambda x: x[1], reverse=True)
    conv_files = conv_files[:max_conversations]
    
    lines = []
    for filepath, mtime in conv_files:
        data = _read_json_safe(filepath, {})
        messages = data.get("messages", [])
        updated = data.get("updated_at", "")[:10]
        
        if not messages:
            continue
        
        # Estrai un mini-riassunto: primo messaggio utente + ultimo messaggio assistant
        first_user = ""
        last_assistant = ""
        for msg in messages:
            if msg.get("role") == "user" and not first_user:
                first_user = msg.get("content", "")[:100]
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content.strip():
                    last_assistant = content[:100]
        
        if first_user:
            lines.append(f"**Sessione** ({updated}):")
            lines.append(f"  - Richiesta: {first_user}")
            if last_assistant:
                lines.append(f"  - Ultima risposta: {last_assistant}")
    
    return "\n".join(lines)


# ============================================================
# COSTRUZIONE BLOCCO <persistent_memory>
# ============================================================

def build_persistent_memory_block() -> str:
    """
    Costruisce il blocco completo <persistent_memory> da iniettare nel system prompt.
    Carica tutti i file di memoria e li assembla in formato strutturato.
    """
    sections = []
    
    # 1. Istruzioni personalizzate
    instructions = load_instructions()
    if instructions:
        sections.append(f"## Istruzioni Personalizzate\n{instructions}")
    
    # 2. Fatti sull'utente
    facts = load_facts()
    if facts:
        sections.append(f"## Fatti sull'Utente\n{facts}")
    
    # 3. Preferenze
    preferences = load_preferences()
    if preferences:
        sections.append(f"## Preferenze\n{preferences}")
    
    # 4. Lezioni apprese
    lessons = load_lessons()
    if lessons:
        sections.append(f"## Lezioni Apprese\n{lessons}")
    
    # 5. Regole auto-imposte
    rules = load_self_rules()
    if rules:
        sections.append(f"## Regole Auto-imposte\n{rules}")
    
    # 6. Conversazioni recenti
    recent = load_recent_conversations(max_conversations=3)
    if recent:
        sections.append(f"## Conversazioni Recenti\n{recent}")
    
    if not sections:
        return ""
    
    block = "\n\n".join(sections)
    return f"\n<persistent_memory>\n{block}\n</persistent_memory>\n"


# ============================================================
# AUTO-SAVE: Estrazione e salvataggio nuovi apprendimenti
# ============================================================

def extract_and_save_learnings(messages: list, conversation_id: str) -> None:
    """
    Analizza i messaggi della conversazione e salva automaticamente
    nuovi apprendimenti nella memoria persistente.
    
    Cerca pattern come:
    - Fatti espliciti sull'utente (nome, lavoro, preferenze dichiarate)
    - Correzioni dell'utente (indica una preferenza o regola)
    - Risultati di self_improve già salvati (evita duplicati)
    
    Questa funzione è leggera e non usa LLM - fa pattern matching semplice.
    """
    if not messages:
        return
    
    new_facts = []
    new_preferences = []
    
    # Analizza solo i messaggi utente recenti (ultimi 10)
    user_messages = [
        m.get("content", "") for m in messages[-20:]
        if m.get("role") == "user" and m.get("content")
    ]
    
    # Pattern per preferenze esplicite
    preference_patterns = [
        "preferisco", "mi piace", "non mi piace", "voglio che tu",
        "d'ora in poi", "ricordati che", "ricorda che", "nota che",
        "il mio nome è", "mi chiamo", "lavoro come", "sono di",
        "il mio sito", "la mia email", "il mio numero"
    ]
    
    # Pattern per fatti
    fact_patterns = [
        "il mio nome è", "mi chiamo", "sono di", "abito a",
        "lavoro come", "ho un negozio", "il mio sito è",
        "la mia azienda", "il mio business"
    ]
    
    for msg in user_messages:
        msg_lower = msg.lower()
        
        # Cerca fatti espliciti
        for pattern in fact_patterns:
            if pattern in msg_lower and len(msg) < 200:
                # Evita duplicati controllando se il fatto è già in memoria
                if not _fact_already_exists(msg[:150]):
                    new_facts.append(msg[:150])
                break
        
        # Cerca preferenze esplicite
        for pattern in preference_patterns:
            if pattern in msg_lower and len(msg) < 200:
                if not _preference_already_exists(msg[:150]):
                    new_preferences.append(msg[:150])
                break
    
    # Salva nuovi fatti
    if new_facts:
        data = _read_json_safe(FACTS_FILE, {"facts": []})
        facts_list = data.get("facts", [])
        for fact in new_facts[:3]:  # Max 3 nuovi fatti per sessione
            facts_list.append({
                "fact": fact,
                "category": "auto_learned",
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "source_conversation": conversation_id
            })
        data["facts"] = facts_list[-200:]
        _save_json_safe(FACTS_FILE, data)
        logger.info(f"Auto-salvati {len(new_facts)} nuovi fatti dalla conversazione {conversation_id}")
        # Salvataggio semantico in background
        for fact in new_facts[:3]:
            try:
                asyncio.create_task(save_memory_semantic(fact, {"source": "facts.json", "category": "auto_learned"}))
            except Exception as e:
                logger.error(f"Errore salvataggio semantico: {e}")
    
    # Salva nuove preferenze
    if new_preferences:
        data = _read_json_safe(PREFERENCES_FILE, {"preferences": {}})
        prefs = data.get("preferences", {})
        for pref in new_preferences[:3]:  # Max 3 nuove preferenze per sessione
            key = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            prefs[key] = {
                "value": pref,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "auto_learned",
                "source_conversation": conversation_id
            }
        data["preferences"] = prefs
        _save_json_safe(PREFERENCES_FILE, data)
        logger.info(f"Auto-salvate {len(new_preferences)} nuove preferenze dalla conversazione {conversation_id}")
        # Salvataggio semantico in background
        for pref in new_preferences[:3]:
            try:
                text = f"Preferenza: {pref}"
                asyncio.create_task(save_memory_semantic(text, {"source": "preferences.json", "type": "auto_learned"}))
            except Exception as e:
                logger.error(f"Errore salvataggio semantico: {e}")


def _fact_already_exists(fact_text: str) -> bool:
    """Controlla se un fatto simile esiste già in memoria."""
    data = _read_json_safe(FACTS_FILE, {"facts": []})
    facts = data.get("facts", [])
    fact_lower = fact_text.lower()[:50]
    
    for f in facts:
        existing = f.get("fact", "").lower()[:50]
        if fact_lower in existing or existing in fact_lower:
            return True
    return False


def _preference_already_exists(pref_text: str) -> bool:
    """Controlla se una preferenza simile esiste già in memoria."""
    data = _read_json_safe(PREFERENCES_FILE, {"preferences": {}})
    prefs = data.get("preferences", {})
    pref_lower = pref_text.lower()[:50]
    
    for key, val in prefs.items():
        existing = ""
        if isinstance(val, dict):
            existing = val.get("value", "").lower()[:50]
        else:
            existing = str(val).lower()[:50]
        if pref_lower in existing or existing in pref_lower:
            return True
    return False


# ============================================================
# SALVATAGGIO RIASSUNTO CONVERSAZIONE
# ============================================================

def save_conversation_summary(conversation_id: str, messages: list) -> None:
    """
    Salva un riassunto leggero della conversazione per il contesto futuro.
    Estrae il topic principale e i punti chiave senza usare LLM.
    """
    if not messages or len(messages) < 2:
        return
    
    # Estrai primo messaggio utente come topic
    first_user_msg = ""
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            first_user_msg = msg["content"][:100]
            break
    
    if not first_user_msg:
        return
    
    # Estrai punti chiave: messaggi utente significativi
    key_points = []
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            content = msg["content"].strip()
            if len(content) > 10 and len(content) < 200:
                key_points.append(content[:100])
    
    # Mantieni max 5 punti chiave
    key_points = key_points[:5]
    
    # Salva in summaries.json
    data = _read_json_safe(SUMMARIES_FILE, {"conversations": {}})
    conversations = data.get("conversations", {})
    
    conversations[conversation_id] = {
        "conversation_id": conversation_id,
        "last_topic": first_user_msg,
        "key_points": key_points,
        "message_count": len(messages),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Mantieni solo le ultime 50 conversazioni
    if len(conversations) > 50:
        sorted_keys = sorted(
            conversations.keys(),
            key=lambda k: conversations[k].get("updated_at", "")
        )
        for k in sorted_keys[:-50]:
            del conversations[k]
    
    data["conversations"] = conversations
    _save_json_safe(SUMMARIES_FILE, data)
    logger.info(f"Riassunto conversazione {conversation_id} salvato")


# ============================================================
# FUNZIONE PRINCIPALE: end_session
# ============================================================

def end_session(conversation_id: str, messages: list) -> None:
    """
    Chiamata alla fine di ogni sessione/conversazione.
    Esegue:
    1. Estrazione e salvataggio nuovi apprendimenti
    2. Salvataggio riassunto conversazione
    """
    try:
        extract_and_save_learnings(messages, conversation_id)
        save_conversation_summary(conversation_id, messages)
    except Exception as e:
        logger.error(f"Errore in end_session per {conversation_id}: {e}")
