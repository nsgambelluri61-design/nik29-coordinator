"""
memory_watcher.py - Push immediato quando la memoria cambia

Monitora i file di memoria e fa push su GitHub appena qualcosa viene modificato.
- Debounce di 30 secondi (aspetta che le modifiche si stabilizzino)
- Se non c'è internet, riprova ogni 5 minuti finché non riesce
"""
import os
import time
import threading
import subprocess
import hashlib

MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
REPO_DIR = "/app"
BACKUP_DIR = f"{REPO_DIR}/backups"
DEBOUNCE_SECONDS = 30
CHECK_INTERVAL = 10
RETRY_INTERVAL = 300  # 5 minuti

WATCH_FILES = [
    "facts.json",
    "preferences.json",
    "lessons.json",
    "self_rules.json",
    "summaries.json",
    "projects.json",
    "semantic_index.json"
]


class MemoryWatcher:
    def __init__(self):
        self._last_hashes = {}
        self._last_change_time = 0
        self._push_pending = False
        self._push_failed = False  # Flag per retry
        self._lock = threading.Lock()
        self._running = False

    def _get_file_hash(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except (FileNotFoundError, PermissionError):
            return None

    def _check_changes(self):
        changed = False
        for filename in WATCH_FILES:
            filepath = os.path.join(MEMORY_DIR, filename)
            current_hash = self._get_file_hash(filepath)
            previous_hash = self._last_hashes.get(filename)
            if current_hash and current_hash != previous_hash:
                changed = True
                self._last_hashes[filename] = current_hash
        return changed

    def _do_backup_and_push(self):
        """Copia file e pusha. Se fallisce, segna per retry."""
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)

            # Copia file
            for filename in WATCH_FILES:
                src = os.path.join(MEMORY_DIR, filename)
                dst = os.path.join(BACKUP_DIR, filename)
                if os.path.exists(src):
                    with open(src, 'rb') as f_in:
                        data = f_in.read()
                    with open(dst, 'wb') as f_out:
                        f_out.write(data)

            # Timestamp
            timestamp = time.strftime("%Y-%m-%d_%H%M%S")
            with open(os.path.join(BACKUP_DIR, "last_backup.txt"), 'w') as f:
                f.write(timestamp)

            # Git commit
            date_str = time.strftime("%Y-%m-%d %H:%M")
            subprocess.run(
                ["git", "add", "backups/"],
                cwd=REPO_DIR, capture_output=True, timeout=10
            )
            result = subprocess.run(
                ["git", "commit", "-m", f"backup: auto-save {date_str}"],
                cwd=REPO_DIR, capture_output=True, timeout=10
            )

            if result.returncode != 0:
                # Nessuna modifica da committare
                self._push_failed = False
                return

            # Push
            push_result = subprocess.run(
                ["git", "push", "origin", "HEAD"],
                cwd=REPO_DIR, capture_output=True, timeout=30
            )

            if push_result.returncode == 0:
                print(f"[MEMORY_WATCHER] Backup pushato su GitHub ({date_str})")
                self._push_failed = False
            else:
                print(f"[MEMORY_WATCHER] Push fallito (no internet?). Riprovo tra 5 min...")
                self._push_failed = True

        except Exception as e:
            print(f"[MEMORY_WATCHER] Errore: {e}. Riprovo tra 5 min...")
            self._push_failed = True

    def _watch_loop(self):
        # Inizializza hash
        for filename in WATCH_FILES:
            filepath = os.path.join(MEMORY_DIR, filename)
            self._last_hashes[filename] = self._get_file_hash(filepath)

        print("[MEMORY_WATCHER] Monitoraggio memorie attivo")
        last_retry_time = 0

        while self._running:
            time.sleep(CHECK_INTERVAL)

            # Controlla modifiche
            if self._check_changes():
                with self._lock:
                    self._last_change_time = time.time()
                    self._push_pending = True

            # Debounce: pusha dopo 30 sec dall'ultima modifica
            with self._lock:
                if self._push_pending:
                    elapsed = time.time() - self._last_change_time
                    if elapsed >= DEBOUNCE_SECONDS:
                        self._push_pending = False
                        self._do_backup_and_push()

            # Retry se il push era fallito (ogni 5 minuti)
            if self._push_failed:
                if time.time() - last_retry_time >= RETRY_INTERVAL:
                    last_retry_time = time.time()
                    print("[MEMORY_WATCHER] Retry push...")
                    # Prova solo il push (il commit è già fatto)
                    try:
                        result = subprocess.run(
                            ["git", "push", "origin", "HEAD"],
                            cwd=REPO_DIR, capture_output=True, timeout=30
                        )
                        if result.returncode == 0:
                            print("[MEMORY_WATCHER] Retry riuscito! Backup su GitHub.")
                            self._push_failed = False
                        else:
                            print("[MEMORY_WATCHER] Ancora offline. Riprovo tra 5 min...")
                    except Exception:
                        pass

    def start(self):
        self._running = True
        thread = threading.Thread(target=self._watch_loop, daemon=True)
        thread.name = "MemoryWatcher"
        thread.start()
        print("[MEMORY_WATCHER] Thread avviato")

    def stop(self):
        self._running = False


_watcher = None

def start_memory_watcher():
    global _watcher
    if _watcher is None:
        _watcher = MemoryWatcher()
        _watcher.start()
    return _watcher

def stop_memory_watcher():
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None
