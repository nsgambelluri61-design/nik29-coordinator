#!/usr/bin/env python3
"""
patch_fix_self_improve.py — Fixa il bug nel passaggio parametri di self_improve.
Il coordinator non passava 'reason' e 'task_summary', quindi reflect e add_rule fallivano.
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
    
    # Fix 1: Il coordinator passa parametri sbagliati a self_improve
    old_call = '''            elif name == "self_improve":
                return await self.self_improve_tool.execute(
                    action=args.get("action", "reflect"),
                    task_description=args.get("task_description"),
                    outcome=args.get("outcome"),
                    rule=args.get("rule")
                )'''
    
    new_call = '''            elif name == "self_improve":
                return await self.self_improve_tool.execute(
                    action=args.get("action", "reflect"),
                    task_summary=args.get("task_summary", args.get("task_description", "")),
                    rule=args.get("rule", ""),
                    reason=args.get("reason", args.get("outcome", ""))
                )'''
    
    if "task_summary=args.get(\"task_summary\"" in content:
        print("[SKIP] Fix self_improve gia' applicato")
        return
    
    if old_call in content:
        content = content.replace(old_call, new_call)
        with open(coord_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK] Fix self_improve applicato in coordinator.py")
        print("     Ora passa correttamente: task_summary, rule, reason")
    else:
        # Prova con regex piu' flessibile
        import re
        pattern = r'(\s+elif name == "self_improve":\s+return await self\.self_improve_tool\.execute\()[^)]+\)'
        replacement = '''            elif name == "self_improve":
                return await self.self_improve_tool.execute(
                    action=args.get("action", "reflect"),
                    task_summary=args.get("task_summary", args.get("task_description", "")),
                    rule=args.get("rule", ""),
                    reason=args.get("reason", args.get("outcome", ""))
                )'''
        new_content = re.sub(pattern, replacement, content, count=1)
        if new_content != content:
            with open(coord_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print("[OK] Fix self_improve applicato (regex) in coordinator.py")
        else:
            print("[ERRORE] Pattern non trovato in coordinator.py")
            print("         Cerco manualmente...")
            # Fallback: cerca e sostituisci la riga specifica
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'self.self_improve_tool.execute(' in line:
                    # Trova il blocco e sostituiscilo
                    start = i - 1  # elif name == "self_improve":
                    end = i
                    while end < len(lines) and ')' not in lines[end]:
                        end += 1
                    end += 1  # include la riga con )
                    new_block = [
                        '            elif name == "self_improve":',
                        '                return await self.self_improve_tool.execute(',
                        '                    action=args.get("action", "reflect"),',
                        '                    task_summary=args.get("task_summary", args.get("task_description", "")),',
                        '                    rule=args.get("rule", ""),',
                        '                    reason=args.get("reason", args.get("outcome", ""))',
                        '                )'
                    ]
                    lines[start:end] = new_block
                    with open(coord_path, "w", encoding="utf-8") as f:
                        f.write('\n'.join(lines))
                    print("[OK] Fix self_improve applicato (fallback) in coordinator.py")
                    break
            else:
                print("[ERRORE] Non riesco a trovare self_improve_tool.execute nel file")
                sys.exit(1)

if __name__ == "__main__":
    root = find_project_root()
    print(f"Directory: {root}")
    patch(root)
    print("\nFATTO! Riavvia con: docker compose up -d --build")
    print("Ora self_improve funziona correttamente per salvare lezioni e regole.")
