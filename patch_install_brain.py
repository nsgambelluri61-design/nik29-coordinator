#!/usr/bin/env python3
"""
=============================================================================
  NIK29 BRAIN TRANSPLANT - Installer
=============================================================================
  Installa il pacchetto completo "cervello" per nik29-coordinator:
  - System prompt riscritto con conoscenza profonda
  - Memoria pre-popolata (fatti, lezioni, preferenze, regole)
  - Modello forzato su gpt-4.1

  Uso:
    cd ~/Downloads/nik29-coordinator-v0.6.0
    python3 patch_install_brain.py

  I file del brain (system_prompt.txt, facts.json, ecc.) devono essere
  nella stessa directory di questo script.
=============================================================================
"""
import os
import sys
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_DIR = Path.cwd()

if not (PROJECT_DIR / "docker-compose.yml").exists():
    print("ERRORE: Esegui dalla root del progetto nik29-coordinator!")
    print("  cd ~/Downloads/nik29-coordinator-v0.6.0")
    print("  python3 patch_install_brain.py")
    sys.exit(1)

print("=" * 60)
print("  NIK29 BRAIN TRANSPLANT - Installazione")
print("=" * 60)
print(f"\n  Progetto: {PROJECT_DIR}")
print(f"  Script:   {SCRIPT_DIR}\n")

SOURCE_FILES = {
    "system_prompt.txt": PROJECT_DIR / "config" / "system_prompt.txt",
    "facts.json": PROJECT_DIR / "data" / "memory" / "facts.json",
    "lessons.json": PROJECT_DIR / "data" / "memory" / "lessons.json",
    "preferences.json": PROJECT_DIR / "data" / "memory" / "preferences.json",
    "self_rules.json": PROJECT_DIR / "data" / "memory" / "self_rules.json",
}

(PROJECT_DIR / "config").mkdir(parents=True, exist_ok=True)
(PROJECT_DIR / "data" / "memory").mkdir(parents=True, exist_ok=True)

print("[1/3] Installazione file cervello...\n")

installed = 0
for filename, dest_path in SOURCE_FILES.items():
    src = SCRIPT_DIR / filename
    if src.exists():
        if dest_path.exists():
            backup = dest_path.with_suffix(dest_path.suffix + ".bak_pre_brain")
            shutil.copy2(dest_path, backup)
            print(f"  Backup: {dest_path.name} -> {backup.name}")
        shutil.copy2(src, dest_path)
        print(f"  + {filename} -> {dest_path.relative_to(PROJECT_DIR)}")
        installed += 1
    else:
        print(f"  ERRORE: {filename} non trovato in {SCRIPT_DIR}")

print(f"\n  File installati: {installed}/{len(SOURCE_FILES)}")

print("\n[2/3] Configurazione modello GPT-4.1 fisso...\n")

env_path = PROJECT_DIR / ".env"
env_var = "OPENAI_MODEL_FORCE=gpt-4.1"

if env_path.exists():
    content = env_path.read_text(encoding="utf-8")
    if "OPENAI_MODEL_FORCE=" in content:
        lines = content.split('\n')
        new_lines = [env_var if l.startswith("OPENAI_MODEL_FORCE=") else l for l in lines]
        env_path.write_text('\n'.join(new_lines), encoding="utf-8")
        print(f"  ~ Aggiornato OPENAI_MODEL_FORCE=gpt-4.1 in .env")
    else:
        with open(env_path, "a", encoding="utf-8") as f:
            if not content.endswith('\n'):
                f.write('\n')
            f.write(f"{env_var}\n")
        print(f"  + Aggiunto OPENAI_MODEL_FORCE=gpt-4.1 a .env")
else:
    print(f"  ATTENZIONE: .env non trovato! Aggiungi manualmente:")
    print(f"  echo 'OPENAI_MODEL_FORCE=gpt-4.1' >> .env")

print("\n[3/3] Riepilogo...\n")
print("  Installato:")
print("  - System prompt completo con conoscenza profonda")
print("  - 25 fatti su Nicola e il business")
print("  - 15 lezioni tecniche apprese")
print("  - 10 preferenze operative")
print("  - 10 regole auto-imposte")
print("  - Modello forzato: gpt-4.1 (niente piu mini)")
print("\n" + "=" * 60)
print("  ORA ESEGUI:")
print("")
print("  docker compose build && docker compose up -d")
print("")
print("  Poi testa con:")
print('  "cerca su internet i prezzi dei materassi Emma Sleep"')
print('  "fai uno screenshot di https://ildormire.com"')
print('  "che versione sei?"')
print("=" * 60 + "\n")
