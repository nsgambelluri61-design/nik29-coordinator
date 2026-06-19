#!/usr/bin/env python3
"""
patch_auto_reflect.py — Aggiunge auto-reflect FORZATO nel coordinator.
Dopo ogni conversazione con errori risolti, il CODICE (non il modello)
salva automaticamente una lezione. Non dipende dalla volonta' del LLM.

Include anche il fix del bug 'added_date' nel self_improve_tool.
"""
import os
import sys

def find_project_root():
    candidates = [
        os.getcwd(),
        os.path.expanduser("~/Downloads/nik29-coordinator-v0.6.0"),
        "/app"
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "app", "coordinator.py")):
            return c
    print("ERRORE: Non trovo la root del progetto.")
    sys.exit(1)

def patch(root):
    coord_path = os.path.join(root, "app", "coordinator.py")
    with open(coord_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "AUTO-REFLECT FORZATO" in content:
        print("[SKIP] Auto-reflect forzato gia' presente in coordinator.py")
    else:
        changes = 0
        
        # STEP 1: Aggiungere import _auto_save_lesson
        if "_auto_save_lesson" not in content:
            old_imp = "from app.tools.self_improve_tool import SelfImproveTool"
            new_imp = "from app.tools.self_improve_tool import SelfImproveTool\nfrom app.memory_v2 import save_lesson as _auto_save_lesson"
            if old_imp in content:
                content = content.replace(old_imp, new_imp)
                changes += 1
                print("[OK] Aggiunto import _auto_save_lesson")
        
        # STEP 2: Aggiungere tracker errori prima del loop
        if "_error_log = []" not in content:
            old_loop = "        for iteration in range(15):"
            new_loop = "        # === AUTO-REFLECT FORZATO: tracker errori ===\n        _error_log = []  # Traccia errori nei tool per auto-reflect\n        for iteration in range(15):"
            if old_loop in content:
                content = content.replace(old_loop, new_loop, 1)
                changes += 1
                print("[OK] Aggiunto tracker errori")
        
        # STEP 3: Dopo ogni risultato tool, traccia errori
        if "_error_keywords" not in content:
            old_append = """                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })"""
            new_append = """                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                    # === AUTO-REFLECT: traccia errori ===
                    _error_keywords = ["errore", "fallito", "timeout", "non trovato", "non esiste", "bloccato", "rifiutato", "impossibile", "failed", "error", "denied", "connection refused"]
                    _result_lower = (result or "").lower()[:500]
                    if any(kw in _result_lower for kw in _error_keywords):
                        _error_log.append({"tool": func_name, "error": result[:200], "iteration": iteration})"""
            if old_append in content:
                content = content.replace(old_append, new_append)
                changes += 1
                print("[OK] Aggiunto tracking errori nei risultati tool")
        
        # STEP 4: Prima del return finale, auto-reflect
        old_return = """                persistent_memory.end_session(conversation_id, messages)

                yield {"type": "response", "content": final_content}
                return"""
        new_return = """                persistent_memory.end_session(conversation_id, messages)
                # === AUTO-REFLECT FORZATO: salva lezione se errori risolti ===
                if _error_log and iteration > 0:
                    try:
                        _err_tools = list(set(e["tool"] for e in _error_log))
                        _err_summary = _error_log[0]["error"][:150]
                        _solution_hint = final_content[:150] if final_content else "Risolto dopo iterazioni multiple"
                        _lesson_text = f"Problema con {', '.join(_err_tools)}: {_err_summary}. Risolto: {_solution_hint}"
                        import asyncio as _aio
                        _aio.create_task(_auto_save_lesson(
                            category="soluzione",
                            lesson=_lesson_text,
                            context=f"Auto-reflect forzato, {len(_error_log)} errori in {iteration+1} iterazioni"
                        ))
                    except Exception:
                        pass  # Non bloccare mai la risposta

                yield {"type": "response", "content": final_content}
                return"""
        if old_return in content:
            content = content.replace(old_return, new_return, 1)
            changes += 1
            print("[OK] Aggiunto auto-reflect forzato prima del return")
        
        if changes > 0:
            with open(coord_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[OK] coordinator.py aggiornato ({changes} modifiche)")
        else:
            print("[WARN] Nessuna modifica applicata a coordinator.py")
    
    # === Fix bug 'added_date' nel self_improve_tool ===
    tool_path = os.path.join(root, "app", "tools", "self_improve_tool.py")
    if os.path.exists(tool_path):
        with open(tool_path, "r", encoding="utf-8") as f:
            tool_content = f.read()
        
        if "r.get('added_date'" not in tool_content and "r['added_date']" in tool_content:
            tool_content = tool_content.replace(
                "r['added_date']",
                "r.get('added_date', r.get('date', 'N/A'))"
            )
            with open(tool_path, "w", encoding="utf-8") as f:
                f.write(tool_content)
            print("[OK] Fix bug 'added_date' in self_improve_tool.py")
        else:
            print("[SKIP] Bug 'added_date' gia' fixato")

if __name__ == "__main__":
    root = find_project_root()
    print(f"Directory: {root}")
    patch(root)
    print("\n=== FATTO! ===")
    print("Riavvia con: docker compose up -d --build")
    print("")
    print("Da ora nik29 salva AUTOMATICAMENTE una lezione ogni volta che:")
    print("  1. Un tool restituisce un errore (timeout, non trovato, ecc.)")
    print("  2. Il modello continua e risolve il problema")
    print("  3. La conversazione si chiude con successo")
    print("")
    print("NON dipende dal modello — e' il CODICE che forza il salvataggio.")
