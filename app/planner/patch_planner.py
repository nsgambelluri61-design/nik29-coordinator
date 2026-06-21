"""
patch_planner.py — Patch idempotente per integrare il planner nel coordinator.

Questo script:
1. Legge /app/coordinator.py
2. Aggiunge l'import del planner in cima (dopo gli altri import)
3. Inserisce il check del planner dentro process_message
   (dopo il caricamento conversazione e system prompt, PRIMA del for loop)
4. Se il planner restituisce un piano → delega al PlanExecutor
5. Se il planner restituisce None → cade nel codice esistente (zero modifiche)

Idempotenza: controlla se il patch è già applicato prima di modificare.

Uso:
    python3 /app/planner/patch_planner.py
    # oppure
    python3 patch_planner.py --coordinator /app/coordinator.py
"""

import sys
import os
import re
import shutil
from datetime import datetime

# Path di default
DEFAULT_COORDINATOR_PATH = "/app/coordinator.py"

# Marker per idempotenza
PATCH_MARKER = "# === PLANNER INTEGRATION (auto-patched) ==="

# === IMPORT DA AGGIUNGERE ===
IMPORT_BLOCK = '''
# === PLANNER INTEGRATION (auto-patched) ===
from app.planner.planner import TaskPlanner
from app.planner.executor import PlanExecutor
'''

# === CODICE DA INSERIRE DENTRO process_message ===
# Questo blocco va inserito DOPO la riga che costruisce system_msg
# e PRIMA del "for iteration in range(15):"
PLANNER_CHECK_BLOCK = '''
        # === PLANNER INTEGRATION (auto-patched) ===
        # Classifica il messaggio: SIMPLE → procedi normalmente, COMPLEX → piano autonomo
        _planner = TaskPlanner(self.client)
        _plan = await _planner.analyze(user_message)

        if _plan is not None:
            # Task complesso: esegui piano step-by-step
            logger.info(f"Planner: task COMPLEX, piano con {len(_plan.get('steps', []))} step")
            _executor = PlanExecutor(
                client=self.client,
                execute_tool_fn=self._execute_tool,
                tools_definition=TOOLS_DEFINITION,
                build_system_prompt_fn=self._build_system_prompt,
                route_model_fn=route_model,
                status_queue=self._status_queue,
                progress_message_fn=self._progress_message,
                safe_truncate_fn=self._safe_truncate_messages,
            )
            async for event in _executor.execute_plan(
                plan=_plan,
                messages=messages,
                system_msg=system_msg,
                user_message=user_message,
                conversation_id=conversation_id,
            ):
                yield event

            # Salva conversazione dopo piano completato
            from app.memory import memory as _mem
            _mem.save_conversation(conversation_id, messages)

            # Auto-reflect se ci sono stati errori
            if _executor.last_error_log and _executor.last_iterations > 0:
                try:
                    _err_tools = list(set(e.get("tool", "unknown") for e in _executor.last_error_log))
                    _err_summary = _executor.last_error_log[0].get("error", "")[:150]
                    _lesson = f"Piano autonomo con errori in {', '.join(_err_tools)}: {_err_summary}"
                    import asyncio as _aio
                    _aio.create_task(_auto_save_lesson(
                        category="soluzione",
                        lesson=_lesson,
                        context=f"Planner auto-reflect, {len(_executor.last_error_log)} errori in {_executor.last_iterations} iterazioni"
                    ))
                except Exception:
                    pass

            # Auto-save apprendimenti
            persistent_memory.end_session(conversation_id, messages)
            return
        # === END PLANNER INTEGRATION ===

'''


def patch_coordinator(coordinator_path: str = DEFAULT_COORDINATOR_PATH) -> bool:
    """
    Applica il patch al coordinator.py.

    Returns:
        True se il patch è stato applicato, False se già presente.
    """
    if not os.path.exists(coordinator_path):
        print(f"ERRORE: File non trovato: {coordinator_path}")
        return False

    # Leggi il file
    with open(coordinator_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check idempotenza
    if PATCH_MARKER in content:
        print("✅ Patch già applicato. Nessuna modifica necessaria.")
        return False

    # === Backup ===
    backup_path = coordinator_path + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(coordinator_path, backup_path)
    print(f"📦 Backup creato: {backup_path}")

    # === 1. Aggiungi import ===
    # Inserisci dopo l'ultimo import esistente (prima della riga "logger = ...")
    import_anchor = "logger = logging.getLogger(\"coordinator\")"
    if import_anchor in content:
        content = content.replace(
            import_anchor,
            IMPORT_BLOCK.strip() + "\n\n" + import_anchor
        )
    else:
        # Fallback: inserisci prima della definizione TOOLS_DEFINITION
        fallback_anchor = "# Definizione dei tool per OpenAI function calling"
        if fallback_anchor in content:
            content = content.replace(
                fallback_anchor,
                IMPORT_BLOCK.strip() + "\n\n" + fallback_anchor
            )
        else:
            print("⚠️ Impossibile trovare punto di inserimento per import. Inserisco in cima.")
            content = IMPORT_BLOCK + "\n" + content

    # === 2. Inserisci planner check dentro process_message ===
    # Punto di inserimento: DOPO la riga "content = user_message + file_info"
    # e "messages.append({"role": "user", "content": content})"
    # e PRIMA di "# Loop di esecuzione tool"

    # Cerchiamo il pattern del commento del loop
    loop_comment = "# Loop di esecuzione tool (max 15 iterazioni per task complessi)"
    if loop_comment in content:
        content = content.replace(
            "        " + loop_comment,
            PLANNER_CHECK_BLOCK + "        " + loop_comment
        )
    else:
        # Fallback: cerca il "for iteration in range(15):"
        loop_line = "        for iteration in range(15):"
        if loop_line in content:
            content = content.replace(
                loop_line,
                PLANNER_CHECK_BLOCK + loop_line
            )
        else:
            print("ERRORE: Impossibile trovare il loop di esecuzione tool. Patch non applicato.")
            # Ripristina backup
            shutil.copy2(backup_path, coordinator_path)
            return False

    # === 3. Scrivi il file modificato ===
    with open(coordinator_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Patch applicato con successo a: {coordinator_path}")
    print(f"   - Import planner aggiunto")
    print(f"   - Check planner inserito in process_message")
    print(f"   - Backup disponibile: {backup_path}")
    return True


def verify_patch(coordinator_path: str = DEFAULT_COORDINATOR_PATH) -> bool:
    """Verifica che il patch sia stato applicato correttamente."""
    if not os.path.exists(coordinator_path):
        print(f"ERRORE: File non trovato: {coordinator_path}")
        return False

    with open(coordinator_path, "r", encoding="utf-8") as f:
        content = f.read()

    checks = [
        ("Import TaskPlanner", "from app.planner.planner import TaskPlanner" in content),
        ("Import PlanExecutor", "from app.planner.executor import PlanExecutor" in content),
        ("Planner check in process_message", "_planner = TaskPlanner(self.client)" in content),
        ("Executor instantiation", "PlanExecutor(" in content),
        ("Plan execution loop", "_executor.execute_plan(" in content),
        ("Fallthrough to existing code", "# === END PLANNER INTEGRATION ===" in content),
    ]

    all_ok = True
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
        if not result:
            all_ok = False

    if all_ok:
        print("\n✅ Patch verificato: tutte le componenti presenti.")
    else:
        print("\n❌ Patch incompleto: alcune componenti mancanti.")

    return all_ok


def unpatch_coordinator(coordinator_path: str = DEFAULT_COORDINATOR_PATH) -> bool:
    """
    Rimuove il patch dal coordinator (ripristina l'ultimo backup).
    """
    # Cerca il backup più recente
    backup_dir = os.path.dirname(coordinator_path)
    base_name = os.path.basename(coordinator_path)
    backups = sorted([
        f for f in os.listdir(backup_dir)
        if f.startswith(base_name + ".backup_")
    ])

    if not backups:
        print("ERRORE: Nessun backup trovato. Impossibile ripristinare.")
        return False

    latest_backup = os.path.join(backup_dir, backups[-1])
    shutil.copy2(latest_backup, coordinator_path)
    print(f"✅ Ripristinato da backup: {latest_backup}")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Patch nik29-coordinator per integrazione planner")
    parser.add_argument(
        "--coordinator", "-c",
        default=DEFAULT_COORDINATOR_PATH,
        help="Path al file coordinator.py"
    )
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verifica che il patch sia applicato"
    )
    parser.add_argument(
        "--unpatch", "-u",
        action="store_true",
        help="Rimuovi il patch (ripristina backup)"
    )

    args = parser.parse_args()

    if args.verify:
        verify_patch(args.coordinator)
    elif args.unpatch:
        unpatch_coordinator(args.coordinator)
    else:
        success = patch_coordinator(args.coordinator)
        if success:
            print("\n🔍 Verifica post-patch:")
            verify_patch(args.coordinator)
