"""
Tool auto-update per nik29-coordinator.
Controlla e applica aggiornamenti dal repository GitHub.

Flusso:
1. check() → controlla se c'è una nuova versione disponibile
2. update() → scarica e applica l'aggiornamento (con backup)
3. rollback() → ripristina la versione precedente dal backup
4. status() → mostra versione corrente e info

Autore: nik29-coordinator
Versione: 1.0.0
"""

import os
import json
import shutil
import tarfile
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("auto_update_tool")

MANIFEST_URL = os.environ.get(
    "MANIFEST_URL",
    "https://raw.githubusercontent.com/nsgambelluri61-design/nik29-coordinator/main/manifest.json"
)
LOCAL_MANIFEST = Path("/app/manifest.json")
BACKUP_DIR = Path("/data/memory/backups")
UPDATE_LOG = Path("/data/memory/update_log.json")


# ---------------------------------------------------------------------------
# Definizione OpenAI tool
# ---------------------------------------------------------------------------

AUTO_UPDATE_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "auto_update",
        "description": (
            "Gestisce l'auto-aggiornamento del coordinatore. "
            "Azioni: check (controlla nuova versione), update (applica aggiornamento), "
            "rollback (ripristina versione precedente), status (info versione corrente)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["check", "update", "rollback", "status"],
                    "description": "Azione da eseguire"
                }
            },
            "required": ["action"]
        }
    }
}


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class AutoUpdateTool:
    """Gestisce l'auto-aggiornamento del coordinatore da GitHub."""

    def __init__(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        self._ensure_log()

    def _ensure_log(self):
        """Crea il file di log se non esiste."""
        if not UPDATE_LOG.exists():
            self._write_json(UPDATE_LOG, {"updates": []})

    def _read_json(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_json(self, path: Path, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_current_version(self) -> str:
        """Legge la versione corrente dal manifest locale."""
        if LOCAL_MANIFEST.exists():
            data = self._read_json(LOCAL_MANIFEST)
            return data.get("version", "unknown")
        return "unknown"

    async def execute(self, action: str) -> str:
        """Esegue l'azione richiesta."""
        if action == "check":
            return await self._check()
        elif action == "update":
            return await self._update()
        elif action == "rollback":
            return await self._rollback()
        elif action == "status":
            return self._status()
        else:
            return f"Azione non supportata: {action}. Usa: check, update, rollback, status"

    async def _check(self) -> str:
        """Controlla se c'è una nuova versione disponibile."""
        current = self._get_current_version()

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(MANIFEST_URL)
                if resp.status_code != 200:
                    return f"Errore nel controllo aggiornamenti: HTTP {resp.status_code}"

                remote_manifest = resp.json()
        except Exception as e:
            return f"Errore nel controllo aggiornamenti: {str(e)}"

        remote_version = remote_manifest.get("version", "unknown")
        changelog = remote_manifest.get("changelog", [])
        min_version = remote_manifest.get("min_version", "0.0.0")

        if remote_version == current:
            return f"Sei aggiornato alla versione {current}."

        if self._version_compare(remote_version, current) > 0:
            changelog_str = "\n".join(f"  - {c}" for c in changelog)
            return (
                f"Nuova versione disponibile: **{remote_version}** (attuale: {current})\n\n"
                f"**Changelog:**\n{changelog_str}\n\n"
                f"**Versione minima richiesta:** {min_version}\n"
                f"Usa `auto_update` con action=update per aggiornare."
            )
        else:
            return f"Versione corrente ({current}) e' piu' recente del remoto ({remote_version})."

    async def _update(self) -> str:
        """Scarica e applica l'aggiornamento."""
        current = self._get_current_version()

        # 1. Scarica manifest remoto
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(MANIFEST_URL)
                if resp.status_code != 200:
                    return f"Errore download manifest: HTTP {resp.status_code}"
                remote_manifest = resp.json()
        except Exception as e:
            return f"Errore download manifest: {str(e)}"

        remote_version = remote_manifest.get("version", "unknown")
        download_url = remote_manifest.get("download_url", "")

        if not download_url:
            return "Errore: URL di download non trovato nel manifest."

        if remote_version == current:
            return f"Sei gia' alla versione {current}. Nessun aggiornamento necessario."

        # 2. Backup corrente
        backup_name = f"backup_v{current}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        backup_path = BACKUP_DIR / backup_name
        try:
            shutil.copytree("/app", str(backup_path), dirs_exist_ok=True)
            logger.info(f"Backup creato: {backup_path}")
        except Exception as e:
            return f"Errore durante il backup: {str(e)}. Aggiornamento annullato."

        # 3. Scarica il tar.gz
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(download_url)
                if resp.status_code != 200:
                    return f"Errore download aggiornamento: HTTP {resp.status_code}"

                tar_path = Path("/tmp/nik29_update.tar.gz")
                with open(tar_path, "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            return f"Errore download: {str(e)}. Backup disponibile in {backup_path}."

        # 4. Estrai e applica
        try:
            extract_dir = Path("/tmp/nik29_update_extracted")
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(extract_dir)

            # Trova la directory root dell'archivio
            contents = list(extract_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                source_dir = contents[0]
            else:
                source_dir = extract_dir

            # Copia i file aggiornati
            for item in ["app", "config", "manifest.json", "requirements.txt"]:
                src = source_dir / item
                dst = Path("/app") / item
                if src.exists():
                    if src.is_dir():
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)

            # Cleanup
            shutil.rmtree(extract_dir, ignore_errors=True)
            tar_path.unlink(missing_ok=True)

        except Exception as e:
            # Rollback automatico
            logger.error(f"Errore durante l'aggiornamento: {e}. Rollback in corso...")
            try:
                shutil.copytree(str(backup_path), "/app", dirs_exist_ok=True)
                return f"Errore aggiornamento: {str(e)}. Rollback automatico eseguito."
            except Exception as rb_err:
                return f"CRITICO: Errore aggiornamento ({e}) E rollback fallito ({rb_err}). Backup in {backup_path}."

        # 5. Log aggiornamento
        log_data = self._read_json(UPDATE_LOG)
        log_data.setdefault("updates", []).append({
            "from_version": current,
            "to_version": remote_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "backup_path": str(backup_path),
            "status": "success"
        })
        log_data["updates"] = log_data["updates"][-50:]
        self._write_json(UPDATE_LOG, log_data)

        return (
            f"Aggiornamento completato: {current} -> {remote_version}\n\n"
            f"Backup salvato in: {backup_path}\n"
            f"Riavvia il container per applicare le modifiche:\n"
            f"`docker compose restart nik29-coordinator`"
        )

    async def _rollback(self) -> str:
        """Ripristina l'ultima versione dal backup."""
        if not BACKUP_DIR.exists():
            return "Nessun backup disponibile."

        backups = sorted(BACKUP_DIR.iterdir(), reverse=True)
        if not backups:
            return "Nessun backup disponibile."

        latest_backup = backups[0]

        try:
            shutil.copytree(str(latest_backup), "/app", dirs_exist_ok=True)

            # Log
            log_data = self._read_json(UPDATE_LOG)
            log_data.setdefault("updates", []).append({
                "action": "rollback",
                "from_backup": str(latest_backup),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success"
            })
            self._write_json(UPDATE_LOG, log_data)

            return (
                f"Rollback completato da: {latest_backup.name}\n"
                f"Riavvia il container per applicare:\n"
                f"`docker compose restart nik29-coordinator`"
            )
        except Exception as e:
            return f"Errore durante il rollback: {str(e)}"

    def _status(self) -> str:
        """Mostra lo stato corrente."""
        current = self._get_current_version()
        log_data = self._read_json(UPDATE_LOG)
        updates = log_data.get("updates", [])

        backups = []
        if BACKUP_DIR.exists():
            backups = sorted([b.name for b in BACKUP_DIR.iterdir()], reverse=True)[:5]

        lines = [
            f"**Versione corrente:** {current}",
            f"**Manifest URL:** {MANIFEST_URL}",
            f"**Aggiornamenti eseguiti:** {len(updates)}",
        ]

        if updates:
            last = updates[-1]
            lines.append(f"**Ultimo aggiornamento:** {last.get('timestamp', 'N/A')[:19]}")

        if backups:
            lines.append(f"\n**Backup disponibili:** {len(backups)}")
            for b in backups[:3]:
                lines.append(f"  - {b}")

        return "\n".join(lines)

    @staticmethod
    def _version_compare(v1: str, v2: str) -> int:
        """Confronta due versioni semver. Ritorna >0 se v1>v2, <0 se v1<v2, 0 se uguali."""
        def parse(v):
            try:
                return [int(x) for x in v.split(".")]
            except (ValueError, AttributeError):
                return [0, 0, 0]

        parts1 = parse(v1)
        parts2 = parse(v2)

        for a, b in zip(parts1, parts2):
            if a > b:
                return 1
            if a < b:
                return -1
        return len(parts1) - len(parts2)


# Singleton
auto_update_tool = AutoUpdateTool()
