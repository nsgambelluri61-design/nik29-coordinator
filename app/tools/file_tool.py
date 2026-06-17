"""
Tool File Manager per nik29-coordinator.
Gestisce operazioni su file nel workspace in modo sicuro.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("file_tool")

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/data/workspace")
MAX_READ_SIZE = 50000  # 50KB max per lettura


class FileManagerTool:
    """Gestisce file nel workspace del coordinatore."""

    def __init__(self):
        os.makedirs(WORKSPACE_DIR, exist_ok=True)

    def _resolve_path(self, path: Optional[str]) -> Path:
        """Risolve un percorso relativo al workspace in modo sicuro."""
        if not path:
            return Path(WORKSPACE_DIR)

        # Rimuovi eventuali .. per evitare path traversal
        clean_path = path.lstrip("/").replace("..", "")
        resolved = Path(WORKSPACE_DIR) / clean_path

        # Verifica che il path risolto sia dentro il workspace
        try:
            resolved.resolve().relative_to(Path(WORKSPACE_DIR).resolve())
        except ValueError:
            raise ValueError(f"Percorso non consentito: {path}")

        return resolved

    async def execute(self, action: str, path: Optional[str] = None, content: Optional[str] = None) -> str:
        """
        Esegue un'operazione su file.

        Args:
            action: "read", "write", "list", "delete", "info"
            path: Percorso del file (relativo al workspace)
            content: Contenuto da scrivere (solo per write)

        Returns:
            Risultato dell'operazione come stringa
        """
        try:
            if action == "list":
                return self._list(path)
            elif action == "read":
                return self._read(path)
            elif action == "write":
                return self._write(path, content)
            elif action == "delete":
                return self._delete(path)
            elif action == "info":
                return self._info(path)
            else:
                return f"Azione non supportata: {action}. Usa: read, write, list, delete, info"
        except ValueError as e:
            return f"Errore: {str(e)}"
        except Exception as e:
            return f"Errore file_manager: {str(e)}"

    def _list(self, path: Optional[str]) -> str:
        """Lista file e directory."""
        target = self._resolve_path(path)

        if not target.exists():
            return f"Percorso non trovato: {path or '/'}"

        if target.is_file():
            return f"{target.name} ({target.stat().st_size} bytes)"

        items = []
        try:
            for item in sorted(target.iterdir()):
                if item.is_dir():
                    items.append(f"  [DIR]  {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"  [FILE] {item.name} ({size} bytes)")
        except PermissionError:
            return "Errore: permesso negato."

        if not items:
            return f"Directory vuota: {path or '/'}"

        header = f"Contenuto di: {path or '/'}\n"
        return header + "\n".join(items)

    def _read(self, path: Optional[str]) -> str:
        """Legge il contenuto di un file."""
        if not path:
            return "Errore: specificare il percorso del file da leggere."

        target = self._resolve_path(path)

        if not target.exists():
            return f"File non trovato: {path}"

        if target.is_dir():
            return f"'{path}' e' una directory. Usa action='list' per vederne il contenuto."

        size = target.stat().st_size
        if size > MAX_READ_SIZE:
            return f"File troppo grande ({size} bytes, max {MAX_READ_SIZE}). Usa shell con 'head' o 'tail'."

        try:
            content = target.read_text(encoding="utf-8")
            return f"--- {path} ({size} bytes) ---\n{content}"
        except UnicodeDecodeError:
            return f"File binario ({size} bytes). Non leggibile come testo."

    def _write(self, path: Optional[str], content: Optional[str]) -> str:
        """Scrive contenuto in un file."""
        if not path:
            return "Errore: specificare il percorso del file da scrivere."

        if content is None:
            return "Errore: specificare il contenuto da scrivere."

        target = self._resolve_path(path)

        # Crea directory padre se non esiste
        target.parent.mkdir(parents=True, exist_ok=True)

        target.write_text(content, encoding="utf-8")
        size = target.stat().st_size
        return f"File scritto: {path} ({size} bytes)"

    def _delete(self, path: Optional[str]) -> str:
        """Elimina un file."""
        if not path:
            return "Errore: specificare il percorso del file da eliminare."

        target = self._resolve_path(path)

        if not target.exists():
            return f"File non trovato: {path}"

        if target.is_dir():
            return "Non e' possibile eliminare directory. Usa shell con 'rm -r'."

        target.unlink()
        return f"File eliminato: {path}"

    def _info(self, path: Optional[str]) -> str:
        """Informazioni su un file."""
        if not path:
            return "Errore: specificare il percorso."

        target = self._resolve_path(path)

        if not target.exists():
            return f"Non trovato: {path}"

        stat = target.stat()
        info_lines = [
            f"Nome: {target.name}",
            f"Tipo: {'directory' if target.is_dir() else 'file'}",
            f"Dimensione: {stat.st_size} bytes",
            f"Percorso completo: {target}",
        ]

        if target.is_file():
            info_lines.append(f"Estensione: {target.suffix or 'nessuna'}")

        return "\n".join(info_lines)
