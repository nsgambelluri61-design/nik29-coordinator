#!/usr/bin/env python3
"""
=============================================================================
  SELF-IMPROVE FIX — Filtro Intelligente per Lezioni
  Versione: 1.0.0
  
  Questo modulo sostituisce la logica di salvataggio lezioni nel modulo
  self_improve esistente di nik29-coordinator.
  
  Regole:
    1. Errori temporanei (rete, timeout, Docker down) → MAI salvati
    2. Errori logici → salvati come "pending" (quarantena)
    3. Pending → "permanent" solo dopo 3+ occorrenze dello stesso errore
    4. Pending scadono dopo 24h se non confermati
    5. Pulizia automatica integrata
=============================================================================
"""

import os
import re
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("SelfImprove")

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
LESSONS_FILE = DATA_DIR / "lessons.json"

# Soglia per promozione a permanente
CONFIRMATION_THRESHOLD = 3

# Scadenza lezioni pending (ore)
PENDING_EXPIRY_HOURS = 24

# ---------------------------------------------------------------------------
# CLASSIFICAZIONE ERRORI
# ---------------------------------------------------------------------------

# Pattern regex per errori TEMPORANEI (non devono MAI diventare lezioni)
TRANSIENT_ERROR_PATTERNS = [
    r"(?i)connection\s*refused",
    r"(?i)connect\s*timeout",
    r"(?i)read\s*timeout",
    r"(?i)timeout\s*error",
    r"(?i)timeout\s*after",
    r"(?i)timed?\s*out",
    r"(?i)host\s*unreachable",
    r"(?i)network\s*is\s*unreachable",
    r"(?i)no\s*route\s*to\s*host",
    r"(?i)502\s*bad\s*gateway",
    r"(?i)503\s*service\s*unavailable",
    r"(?i)504\s*gateway\s*timeout",
    r"(?i)socket\.?error",
    r"(?i)errno\s*(111|110|113|101)",
    r"(?i)temporary\s*failure",
    r"(?i)name\s*resolution",
    r"(?i)dns.*fail",
    r"(?i)docker.*spento",
    r"(?i)docker.*not\s*running",
    r"(?i)container.*not\s*found",
    r"(?i)bridge.*non.*raggiungibile",
    r"(?i)cannot\s*connect\s*to\s*docker",
    r"(?i)connection\s*reset\s*by\s*peer",
    r"(?i)broken\s*pipe",
]

# Pattern per errori LOGICI (candidati a diventare lezioni)
LOGIC_ERROR_PATTERNS = [
    r"(?i)keyerror",
    r"(?i)typeerror",
    r"(?i)valueerror",
    r"(?i)attributeerror",
    r"(?i)indexerror",
    r"(?i)syntaxerror",
    r"(?i)indentationerror",
    r"(?i)nameerror",
    r"(?i)importerror",
    r"(?i)modulenotfounderror",
    r"(?i)jsondecodeerror",
    r"(?i)validationerror",
    r"(?i)assertionerror",
    r"(?i)permission.*denied",  # Questo è persistente, non temporaneo
]


# ---------------------------------------------------------------------------
# FUNZIONI DI SUPPORTO
# ---------------------------------------------------------------------------

def load_lessons() -> list:
    """Carica le lezioni dal file JSON."""
    if not LESSONS_FILE.exists():
        return []
    try:
        with open(LESSONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        logger.warning(f"File lezioni corrotto o illeggibile: {LESSONS_FILE}")
        return []


def save_lessons(lessons: list):
    """Salva le lezioni nel file JSON."""
    LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LESSONS_FILE, "w", encoding="utf-8") as f:
        json.dump(lessons, f, indent=2, ensure_ascii=False)


def compute_error_signature(tool_name: str, error_message: str) -> str:
    """
    Genera una firma univoca per un errore basata su tool + tipo di errore.
    Ignora dettagli variabili (timestamp, ID, path specifici).
    """
    # Normalizza: rimuovi numeri, path, UUID
    normalized = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>", error_message)
    normalized = re.sub(r"/[\w/.-]+", "<PATH>", normalized)
    normalized = re.sub(r"\d{10,}", "<TIMESTAMP>", normalized)
    normalized = re.sub(r"0x[0-9a-f]+", "<ADDR>", normalized)
    
    # Hash della combinazione tool + errore normalizzato
    raw = f"{tool_name}::{normalized.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def classify_error(error_message: str) -> str:
    """
    Classifica un errore come 'transient', 'logic', o 'unknown'.
    """
    error_str = str(error_message)
    
    # Prima controlla se è temporaneo
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if re.search(pattern, error_str):
            return "transient"
    
    # Poi controlla se è logico
    for pattern in LOGIC_ERROR_PATTERNS:
        if re.search(pattern, error_str):
            return "logic"
    
    # Default: unknown (trattato come logic ma con soglia più alta)
    return "unknown"


# ---------------------------------------------------------------------------
# FUNZIONE PRINCIPALE: REGISTRAZIONE LEZIONE
# ---------------------------------------------------------------------------

def register_lesson(
    tool_name: str,
    error_message: str,
    solution: str,
    context: str = "",
    force: bool = False
) -> dict:
    """
    Registra una lezione con filtro intelligente.
    
    Args:
        tool_name: Nome del tool che ha generato l'errore
        error_message: Messaggio di errore completo
        solution: Soluzione trovata dal modello
        context: Contesto aggiuntivo (es. input dell'utente)
        force: Se True, bypassa il filtro (per lezioni manuali)
    
    Returns:
        dict con:
            - saved: bool (se la lezione è stata salvata)
            - reason: str (motivo del salvataggio o rifiuto)
            - status: str (pending/permanent/rejected)
    """
    
    # Step 1: Classificazione
    error_class = classify_error(error_message)
    
    if error_class == "transient" and not force:
        logger.info(f"[FILTRO] Errore temporaneo ignorato per {tool_name}: {error_message[:80]}...")
        return {
            "saved": False,
            "reason": f"Errore classificato come temporaneo ({error_class}). Non salvato.",
            "status": "rejected"
        }
    
    # Step 2: Genera firma univoca
    signature = compute_error_signature(tool_name, error_message)
    now = datetime.now().isoformat()
    
    # Step 3: Cerca lezione esistente con stessa firma
    lessons = load_lessons()
    existing = None
    existing_idx = None
    
    for idx, lesson in enumerate(lessons):
        if lesson.get("signature") == signature:
            existing = lesson
            existing_idx = idx
            break
    
    if existing:
        # Incrementa contatore
        existing["occurrences"] = existing.get("occurrences", 1) + 1
        existing["last_seen"] = now
        existing["last_error"] = str(error_message)[:200]
        
        # Aggiorna soluzione se diversa (potrebbe essere migliorata)
        if solution and solution != existing.get("solution"):
            existing["solution"] = solution
        
        # Promozione a permanente?
        threshold = CONFIRMATION_THRESHOLD if error_class == "logic" else CONFIRMATION_THRESHOLD + 2
        if existing["occurrences"] >= threshold and existing.get("status") == "pending":
            existing["status"] = "permanent"
            existing["confirmed_at"] = now
            logger.info(f"[PROMOZIONE] Lezione {signature} promossa a permanente ({existing['occurrences']} occorrenze).")
            result_status = "permanent"
        else:
            result_status = existing["status"]
        
        lessons[existing_idx] = existing
        save_lessons(lessons)
        
        return {
            "saved": True,
            "reason": f"Lezione esistente aggiornata (occorrenze: {existing['occurrences']}).",
            "status": result_status
        }
    
    else:
        # Nuova lezione: parte come pending
        new_lesson = {
            "id": f"lesson_{int(time.time())}_{signature[:6]}",
            "signature": signature,
            "tool": tool_name,
            "error_class": error_class,
            "error_summary": str(error_message)[:200],
            "solution": solution,
            "context": context[:300] if context else "",
            "status": "permanent" if force else "pending",
            "occurrences": 1,
            "first_seen": now,
            "last_seen": now,
            "last_error": str(error_message)[:200]
        }
        
        lessons.append(new_lesson)
        save_lessons(lessons)
        
        status = "permanent" if force else "pending"
        logger.info(f"[NUOVA] Lezione {signature} salvata come {status} per {tool_name}.")
        
        return {
            "saved": True,
            "reason": f"Nuova lezione creata in stato '{status}'.",
            "status": status
        }


# ---------------------------------------------------------------------------
# PULIZIA AUTOMATICA
# ---------------------------------------------------------------------------

def cleanup_expired_lessons() -> dict:
    """
    Rimuove le lezioni pending scadute (>24h senza nuove occorrenze).
    Da eseguire periodicamente (es. ogni ora o all'avvio).
    
    Returns:
        dict con statistiche della pulizia
    """
    lessons = load_lessons()
    now = datetime.now()
    
    kept = []
    removed_count = 0
    
    for lesson in lessons:
        if lesson.get("status") == "pending":
            last_seen_str = lesson.get("last_seen", lesson.get("first_seen", ""))
            if last_seen_str:
                try:
                    last_seen = datetime.fromisoformat(last_seen_str)
                    age_hours = (now - last_seen).total_seconds() / 3600
                    
                    if age_hours > PENDING_EXPIRY_HOURS:
                        logger.info(f"[PULIZIA] Rimossa lezione scaduta: {lesson.get('id')} "
                                   f"(tool={lesson.get('tool')}, età={age_hours:.1f}h)")
                        removed_count += 1
                        continue
                except ValueError:
                    pass
        
        kept.append(lesson)
    
    if removed_count > 0:
        save_lessons(kept)
    
    return {
        "total_before": len(lessons),
        "removed": removed_count,
        "total_after": len(kept)
    }


def purge_transient_lessons() -> dict:
    """
    Rimuove TUTTE le lezioni che contengono pattern di errori temporanei.
    Utile come one-shot per pulire lezioni errate già salvate.
    """
    lessons = load_lessons()
    
    kept = []
    removed_count = 0
    
    for lesson in lessons:
        content = json.dumps(lesson, ensure_ascii=False).lower()
        is_transient = any(re.search(p, content) for p in TRANSIENT_ERROR_PATTERNS)
        
        if is_transient:
            logger.info(f"[PURGE] Rimossa lezione temporanea: {lesson.get('id')} — {lesson.get('error_summary', '')[:60]}")
            removed_count += 1
        else:
            kept.append(lesson)
    
    if removed_count > 0:
        save_lessons(kept)
    
    return {
        "total_before": len(lessons),
        "purged": removed_count,
        "total_after": len(kept)
    }


# ---------------------------------------------------------------------------
# LETTURA LEZIONI (per il modello)
# ---------------------------------------------------------------------------

def get_active_lessons(tool_name: Optional[str] = None) -> list:
    """
    Restituisce solo le lezioni PERMANENTI (confermate).
    Il modello deve leggere SOLO queste, non le pending.
    
    Args:
        tool_name: Se specificato, filtra per tool
    
    Returns:
        Lista di lezioni permanenti attive
    """
    lessons = load_lessons()
    active = [l for l in lessons if l.get("status") == "permanent"]
    
    if tool_name:
        active = [l for l in active if l.get("tool") == tool_name]
    
    return active


def get_lessons_summary() -> dict:
    """Restituisce un riepilogo delle lezioni per la dashboard."""
    lessons = load_lessons()
    
    summary = {
        "total": len(lessons),
        "permanent": len([l for l in lessons if l.get("status") == "permanent"]),
        "pending": len([l for l in lessons if l.get("status") == "pending"]),
        "by_tool": {},
        "by_class": {"logic": 0, "unknown": 0, "transient": 0}
    }
    
    for lesson in lessons:
        tool = lesson.get("tool", "unknown")
        error_class = lesson.get("error_class", "unknown")
        summary["by_tool"][tool] = summary["by_tool"].get(tool, 0) + 1
        summary["by_class"][error_class] = summary["by_class"].get(error_class, 0) + 1
    
    return summary


# ---------------------------------------------------------------------------
# INTEGRAZIONE CON IL COORDINATOR ESISTENTE
# ---------------------------------------------------------------------------

"""
ISTRUZIONI DI INTEGRAZIONE:

1. Nel file principale del coordinator (es. main.py o coordinator.py), 
   sostituire la vecchia logica di salvataggio lezioni con:
   
   from self_improve_fix import register_lesson, cleanup_expired_lessons, get_active_lessons

2. Quando un tool fallisce e il modello trova una soluzione:
   
   result = register_lesson(
       tool_name="nome_del_tool",
       error_message=str(exception),
       solution="La soluzione trovata dal modello",
       context="Cosa stava facendo l'utente"
   )
   
   if result["saved"]:
       logger.info(f"Lezione registrata: {result['reason']}")

3. Quando il modello deve leggere le lezioni (nel prompt o pre-processing):
   
   # IMPORTANTE: usare get_active_lessons() e NON leggere direttamente il file!
   lessons = get_active_lessons(tool_name="tool_corrente")

4. All'avvio del container, eseguire la pulizia:
   
   cleanup_expired_lessons()
   purge_transient_lessons()  # Solo la prima volta per pulire il vecchio

5. Aggiungere al cron/scheduler (ogni ora):
   
   cleanup_expired_lessons()
"""


# ---------------------------------------------------------------------------
# MAIN (per test e pulizia manuale)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Self-Improve Fix — Filtro Intelligente Lezioni")
    parser.add_argument("--purge", action="store_true", help="Rimuovi tutte le lezioni temporanee esistenti")
    parser.add_argument("--cleanup", action="store_true", help="Rimuovi lezioni pending scadute")
    parser.add_argument("--summary", action="store_true", help="Mostra riepilogo lezioni")
    parser.add_argument("--test", action="store_true", help="Esegui test di classificazione")
    args = parser.parse_args()
    
    if args.purge:
        result = purge_transient_lessons()
        print(f"Purge completato: {result['purged']} lezioni temporanee rimosse su {result['total_before']} totali.")
    
    elif args.cleanup:
        result = cleanup_expired_lessons()
        print(f"Cleanup completato: {result['removed']} lezioni scadute rimosse.")
    
    elif args.summary:
        summary = get_lessons_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    
    elif args.test:
        # Test di classificazione
        test_cases = [
            ("Connection refused on port 4010", "transient"),
            ("KeyError: 'data' in response", "logic"),
            ("TypeError: NoneType has no attribute 'get'", "logic"),
            ("timeout after 30s waiting for response", "transient"),
            ("Docker daemon not running", "transient"),
            ("IndentationError: unexpected indent", "logic"),
            ("502 Bad Gateway from upstream", "transient"),
            ("JSONDecodeError: Expecting value at line 1", "logic"),
            ("bridge non raggiungibile sulla porta 4010", "transient"),
            ("ModuleNotFoundError: No module named 'foo'", "logic"),
        ]
        
        print("TEST CLASSIFICAZIONE ERRORI:")
        print("-" * 70)
        all_pass = True
        for error_msg, expected in test_cases:
            result = classify_error(error_msg)
            status = "✓" if result == expected else "✗"
            if result != expected:
                all_pass = False
            print(f"  {status} '{error_msg[:50]}...' → {result} (atteso: {expected})")
        
        print("-" * 70)
        print(f"Risultato: {'TUTTI PASSATI' if all_pass else 'ALCUNI FALLITI'}")
    
    else:
        parser.print_help()
