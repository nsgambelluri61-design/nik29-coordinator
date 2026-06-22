"""
Client per comunicare con i sub-agenti registrati.
Gestisce il registro agenti e le chiamate HTTP.
"""
import os
import io
import json
import base64
import logging
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger("agent_client")

AGENTS_CONFIG = os.environ.get("AGENTS_CONFIG", "/data/memory/agents.json")
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/data/workspace")
HOST_URL = os.environ.get("HOST_URL", "http://localhost:4001")

# Dimensione massima immagine prima dell'invio (lato lungo in pixel)
MAX_IMAGE_DIMENSION = 1500

DEFAULT_AGENTS = [
    {
        "name": "immagini",
        "description": "Agente immagini autonomo: analisi Vision, editing, scontorno, composizione, pipeline",
        "url": "http://nik29-images:4002",
        "capabilities": ["analyze", "edit", "remove_bg", "composite", "pipeline"]
    }
]


class AgentRegistry:
    """Registro dei sub-agenti disponibili."""

    def __init__(self):
        self._agents: list = []
        self._load()

    def _load(self):
        """Carica la configurazione degli agenti."""
        if os.path.exists(AGENTS_CONFIG):
            try:
                with open(AGENTS_CONFIG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._agents = data.get("agents", [])
                    return
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        # Default
        self._agents = DEFAULT_AGENTS
        self._save()

    def _save(self):
        """Salva la configurazione degli agenti."""
        os.makedirs(os.path.dirname(AGENTS_CONFIG), exist_ok=True)
        with open(AGENTS_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"agents": self._agents}, f, ensure_ascii=False, indent=2)

    def list_agents(self) -> list:
        """Lista tutti gli agenti registrati."""
        return self._agents

    def get_agent(self, name: str) -> Optional[dict]:
        """Recupera un agente per nome."""
        for agent in self._agents:
            if agent["name"] == name:
                return agent
        return None

    def reload(self):
        """Ricarica la configurazione."""
        self._load()


def _resize_image_if_needed(image_bytes: bytes, max_dim: int = MAX_IMAGE_DIMENSION) -> bytes:
    """
    Ridimensiona l'immagine se supera max_dim pixel sul lato lungo.
    Restituisce i bytes dell'immagine (JPEG quality 85) ridimensionata,
    oppure i bytes originali se gia' entro i limiti.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        
        if max(w, h) <= max_dim:
            return image_bytes  # Gia' piccola abbastanza
        
        # Calcola nuove dimensioni mantenendo aspect ratio
        if w > h:
            new_w = max_dim
            new_h = int(h * (max_dim / w))
        else:
            new_h = max_dim
            new_w = int(w * (max_dim / h))
        
        img = img.resize((new_w, new_h), Image.LANCZOS)
        
        # Converti in RGB se necessario (per JPEG)
        if img.mode in ('RGBA', 'P'):
            # Per immagini con trasparenza, salva come PNG
            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            buf.seek(0)
            logger.info(f"Immagine ridimensionata: {w}x{h} -> {new_w}x{new_h} (PNG, {len(buf.getvalue())} bytes)")
            return buf.getvalue()
        else:
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            buf.seek(0)
            logger.info(f"Immagine ridimensionata: {w}x{h} -> {new_w}x{new_h} (JPEG, {len(buf.getvalue())} bytes)")
            return buf.getvalue()
    except ImportError:
        logger.warning("PIL non disponibile, invio immagine originale")
        return image_bytes
    except Exception as e:
        logger.warning(f"Errore ridimensionamento: {e}, invio immagine originale")
        return image_bytes


def _resolve_file_to_base64(file_info: dict) -> Optional[dict]:
    """
    Converte un file (da URL locale o path) in formato base64
    compatibile con nik29-images /task endpoint.
    Ridimensiona automaticamente le immagini grandi.
    """
    name = file_info.get("name", "file.jpg")
    url = file_info.get("url", "")
    data = file_info.get("data", "")

    # Se ha gia' il campo data in base64, ridimensiona se necessario
    if data:
        raw = base64.b64decode(data)
        resized = _resize_image_if_needed(raw)
        return {"name": name, "data": base64.b64encode(resized).decode("utf-8")}

    # Prova a risolvere il file dal workspace locale
    # URL tipo: http://localhost:4001/files/nomefile.jpg
    file_bytes = None
    if "/files/" in url:
        filename = url.split("/files/")[-1]
        filepath = os.path.join(WORKSPACE_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                file_bytes = f.read()

    # Prova con il nome del file direttamente nel workspace
    if file_bytes is None:
        filepath = os.path.join(WORKSPACE_DIR, name)
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                file_bytes = f.read()

    # Cerca qualsiasi file immagine recente nel workspace
    if file_bytes is None:
        workspace = Path(WORKSPACE_DIR)
        if workspace.exists():
            image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            image_files = [
                f for f in workspace.iterdir()
                if f.suffix.lower() in image_extensions
            ]
            if image_files:
                latest = max(image_files, key=lambda f: f.stat().st_mtime)
                with open(latest, "rb") as f:
                    file_bytes = f.read()
                name = latest.name

    if file_bytes:
        resized = _resize_image_if_needed(file_bytes)
        b64 = base64.b64encode(resized).decode("utf-8")
        return {"name": name, "data": b64}

    logger.warning(f"Impossibile risolvere file: {name} (url: {url})")
    return None


def _save_output_files(output_files: list) -> list:
    """
    Salva i file di output (base64) nel workspace e restituisce
    una lista di dict con name e url per ogni file salvato.
    """
    saved = []
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    for file_info in output_files:
        name = file_info.get("name", "output.png")
        data_b64 = file_info.get("data", "")

        if not data_b64:
            logger.warning(f"output_file '{name}' senza campo data, skip")
            continue

        # Decodifica e salva
        try:
            file_bytes = base64.b64decode(data_b64)
            filepath = os.path.join(WORKSPACE_DIR, name)
            with open(filepath, "wb") as f:
                f.write(file_bytes)
            
            # Costruisci URL accessibile dal browser
            file_url = f"{HOST_URL}/files/{name}"
            saved.append({"name": name, "url": file_url})
            logger.info(f"Salvato output file: {filepath} ({len(file_bytes)} bytes)")
        except Exception as e:
            logger.error(f"Errore salvando output file '{name}': {e}")

    return saved


def _build_image_markdown(saved_files: list) -> str:
    """
    Costruisce il markdown con preview e link download per i file salvati.
    """
    if not saved_files:
        return ""

    parts = []
    for f in saved_files:
        name = f["name"]
        url = f["url"]
        # Markdown image per preview inline + link download
        parts.append(f"\n\n![{name}]({url})\n[⬇ Scarica {name}]({url})")

    return "".join(parts)


class AgentClient:
    """Client HTTP per comunicare con i sub-agenti."""

    def __init__(self):
        self.registry = AgentRegistry()

    async def send_task(self, agent_name: str, instruction: str, files: list = None) -> str:
        """Invia un task a un sub-agente."""
        agent = self.registry.get_agent(agent_name)
        if not agent:
            return f"Agente '{agent_name}' non trovato. Agenti disponibili: {[a['name'] for a in self.registry.list_agents()]}"

        url = f"{agent['url']}/task"

        # Converti i file in base64 per nik29-images (con ridimensionamento)
        resolved_files = []
        if files:
            for file_info in files:
                resolved = _resolve_file_to_base64(file_info)
                if resolved:
                    resolved_files.append(resolved)

        # Se non ci sono file risolti, cerca l'immagine piu' recente nel workspace
        if not resolved_files:
            workspace = Path(WORKSPACE_DIR)
            if workspace.exists():
                image_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
                image_files = [
                    f for f in workspace.iterdir()
                    if f.suffix.lower() in image_extensions
                ]
                if image_files:
                    latest = max(image_files, key=lambda f: f.stat().st_mtime)
                    with open(latest, "rb") as f:
                        raw = f.read()
                    resized = _resize_image_if_needed(raw)
                    b64 = base64.b64encode(resized).decode("utf-8")
                    resolved_files.append({"name": latest.name, "data": b64})
                    logger.info(f"Auto-incluso file recente (ridimensionato): {latest.name}")

        payload = {
            "instruction": instruction,
            "files": resolved_files
        }

        # Log payload size per debug
        payload_size = len(json.dumps(payload))
        logger.info(f"Invio task a '{agent_name}': payload {payload_size} bytes, {len(resolved_files)} file(s)")

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    result_text = data.get("result", "Task completato senza risultato.")

                    # --- NUOVO: gestione output_files ---
                    output_files = data.get("output_files", [])
                    if output_files:
                        saved_files = _save_output_files(output_files)
                        if saved_files:
                            image_markdown = _build_image_markdown(saved_files)
                            result_text += image_markdown
                            logger.info(
                                f"Agente '{agent_name}' ha prodotto {len(saved_files)} file: "
                                f"{[f['name'] for f in saved_files]}"
                            )
                    # --- FINE NUOVO ---

                    # --- FIX_IMAGE_PREVIEW_APPLIED ---
                    # Fallback a 3 livelli: genera markdown inline anche quando
                    # nik29-images non restituisce output_files espliciti.
                    if not output_files:
                        import re as _re
                        import os as _os
                        import pathlib as _pl

                        # Livello 1: path assoluto /data/workspace/nome.png nel testo
                        ws_paths = _re.findall(
                            r'(/(?:data|app/data)/workspace/[^\s\)\]]+\.(?:png|jpg|jpeg|gif|webp))',
                            result_text, _re.IGNORECASE
                        )
                        for wp in ws_paths:
                            fname = _os.path.basename(wp)
                            furl  = f"{HOST_URL}/files/{fname}"
                            if furl not in result_text and _os.path.exists(wp):
                                result_text += f"\n\n![{fname}]({furl})\n[⬇ Scarica {fname}]({furl})"
                                logger.info(f"[FIX_IMAGE_PREVIEW] markdown da path: {wp}")

                        # Livello 2: nome file immagine nel testo, verificato nel workspace
                        if not ws_paths:
                            img_names = _re.findall(
                                r'\b([a-zA-Z0-9_\-\.]+\.(?:png|jpg|jpeg|gif|webp))\b',
                                result_text, _re.IGNORECASE
                            )
                            for fname in list(dict.fromkeys(img_names)):
                                fpath = _os.path.join(WORKSPACE_DIR, fname)
                                if _os.path.exists(fpath):
                                    furl = f"{HOST_URL}/files/{fname}"
                                    if furl not in result_text:
                                        result_text += f"\n\n![{fname}]({furl})\n[⬇ Scarica {fname}]({furl})"
                                        logger.info(f"[FIX_IMAGE_PREVIEW] markdown da nome: {fname}")

                        # Livello 3: parole chiave → file più recente nel workspace
                        if not ws_paths and "![" not in result_text:
                            _kws = ["scontorn", "rimoss", "sfondo", "background",
                                    "rembg", "processata", "elaborata", "completato",
                                    "successo", "output", "risultato"]
                            if any(kw in result_text.lower() for kw in _kws):
                                ws = _pl.Path(WORKSPACE_DIR)
                                if ws.exists():
                                    _exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                                    _imgs = [f for f in ws.iterdir()
                                             if f.is_file() and f.suffix.lower() in _exts]
                                    if _imgs:
                                        latest = max(_imgs, key=lambda f: f.stat().st_mtime)
                                        furl = f"{HOST_URL}/files/{latest.name}"
                                        result_text += f"\n\n![{latest.name}]({furl})\n[⬇ Scarica {latest.name}]({furl})"
                                        logger.info(f"[FIX_IMAGE_PREVIEW] markdown da file recente: {latest.name}")
                    # --- FINE FIX_IMAGE_PREVIEW_APPLIED ---

                    return result_text
                else:
                    return f"Errore dall'agente {agent_name}: HTTP {resp.status_code} - {resp.text[:200]}"
        except httpx.ConnectError:
            return f"Impossibile connettersi all'agente '{agent_name}' ({agent['url']}). Verifica che sia in esecuzione."
        except httpx.TimeoutException:
            return f"Timeout nella comunicazione con l'agente '{agent_name}' (timeout 180s superato). Il task potrebbe essere troppo complesso."
        except httpx.RemoteProtocolError:
            return f"L'agente '{agent_name}' si e' disconnesso durante l'elaborazione. Possibile crash per memoria insufficiente. Riprova con un'immagine piu' piccola."
        except Exception as e:
            return f"Errore comunicazione con '{agent_name}': {str(e)}"

    async def check_all_agents_health(self) -> dict:
        """Controlla lo stato di salute di tutti gli agenti."""
        results = {}
        for agent in self.registry.list_agents():
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"{agent['url']}/health")
                    results[agent["name"]] = resp.status_code == 200
            except Exception:
                results[agent["name"]] = False
        return results


# Singleton
agent_client = AgentClient()
