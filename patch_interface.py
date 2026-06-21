#!/usr/bin/env python3
"""
patch_interface.py - Script per aggiornare l'interfaccia web di nik29-coordinator.

Questo script:
1. Cerca la directory del progetto nik29-coordinator
2. Crea un backup dell'index.html esistente
3. Copia la nuova interfaccia al posto di quella vecchia
4. Verifica che il file sia stato copiato correttamente

Uso:
    python3 patch_interface.py [percorso_progetto]

Se non viene specificato il percorso, lo script cerca in posizioni comuni.
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path


def find_project_dir(custom_path=None):
    """Trova la directory del progetto nik29-coordinator."""
    if custom_path:
        path = Path(custom_path)
        if path.exists():
            return path
        print(f"ERRORE: Il percorso specificato non esiste: {custom_path}")
        sys.exit(1)

    # Percorsi comuni dove potrebbe trovarsi il progetto
    common_paths = [
        Path.home() / "nik29-coordinator",
        Path.home() / "projects" / "nik29-coordinator",
        Path("/root") / "nik29-coordinator",
        Path("/opt") / "nik29-coordinator",
        Path.cwd() / "nik29-coordinator",
        Path.cwd(),
    ]

    for path in common_paths:
        static_dir = path / "static"
        if static_dir.exists():
            return path

    return None


def backup_file(file_path):
    """Crea un backup del file con timestamp."""
    if not file_path.exists():
        print(f"  Nessun file esistente da backuppare: {file_path}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"index.html.backup_{timestamp}"
    backup_path = file_path.parent / backup_name

    shutil.copy2(file_path, backup_path)
    print(f"  Backup creato: {backup_path}")
    return backup_path


def patch_interface(project_dir):
    """Esegue il patching dell'interfaccia."""
    static_dir = project_dir / "static"
    target_file = static_dir / "index.html"
    
    # Il nuovo file si trova nella stessa directory dello script
    script_dir = Path(__file__).parent
    source_file = script_dir / "static" / "index.html"

    if not source_file.exists():
        print(f"ERRORE: File sorgente non trovato: {source_file}")
        sys.exit(1)

    # Crea la directory static se non esiste
    static_dir.mkdir(parents=True, exist_ok=True)

    # Backup
    print("\n[1/3] Creazione backup...")
    backup_path = backup_file(target_file)

    # Copia
    print("\n[2/3] Installazione nuova interfaccia...")
    shutil.copy2(source_file, target_file)
    print(f"  Copiato: {source_file} -> {target_file}")

    # Verifica
    print("\n[3/3] Verifica...")
    if target_file.exists():
        source_size = source_file.stat().st_size
        target_size = target_file.stat().st_size
        if source_size == target_size:
            print(f"  OK - File installato correttamente ({target_size:,} bytes)")
        else:
            print(f"  ATTENZIONE: Dimensioni diverse (sorgente: {source_size}, destinazione: {target_size})")
    else:
        print("  ERRORE: Il file non e' stato copiato!")
        sys.exit(1)

    return backup_path


def main():
    print("=" * 60)
    print("  nik29-coordinator - Aggiornamento Interfaccia Web")
    print("  Versione: 2.0 (Modern Dark Theme)")
    print("=" * 60)

    # Determina il percorso del progetto
    custom_path = sys.argv[1] if len(sys.argv) > 1 else None
    project_dir = find_project_dir(custom_path)

    if project_dir is None:
        print("\nERRORE: Impossibile trovare la directory del progetto.")
        print("Specifica il percorso come argomento:")
        print("  python3 patch_interface.py /percorso/a/nik29-coordinator")
        sys.exit(1)

    print(f"\nDirectory progetto: {project_dir}")

    # Conferma
    response = input("\nProcedere con l'aggiornamento? [S/n]: ").strip().lower()
    if response and response not in ('s', 'si', 'y', 'yes', ''):
        print("Operazione annullata.")
        sys.exit(0)

    # Esegui patch
    backup_path = patch_interface(project_dir)

    # Istruzioni finali
    print("\n" + "=" * 60)
    print("  AGGIORNAMENTO COMPLETATO!")
    print("=" * 60)
    print(f"\n  Nuova interfaccia installata in:")
    print(f"    {project_dir / 'static' / 'index.html'}")
    if backup_path:
        print(f"\n  Backup disponibile in:")
        print(f"    {backup_path}")
    print(f"\n  Per ripristinare il backup:")
    if backup_path:
        print(f"    cp {backup_path} {project_dir / 'static' / 'index.html'}")
    print(f"\n  Riavvia il server per applicare le modifiche:")
    print(f"    docker restart nik29-coordinator")
    print(f"    # oppure: pm2 restart nik29-coordinator")
    print()


if __name__ == "__main__":
    main()
