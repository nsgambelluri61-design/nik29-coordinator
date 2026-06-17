"""
Tool ask_manus per nik29-coordinator.
Permette al coordinatore di chiedere aiuto a Manus (via API) quando non sa
fare qualcosa da solo, con il consenso esplicito dell'utente.

Sistema a 2 fasi:
- Fase 1 (propose): prepara la richiesta e chiede conferma all'utente
- Fase 2 (execute): esegue la richiesta dopo conferma, con polling asincrono

v2.1.0 - Timeout aumentato a 1200s (20 min) + status_callback per WebSocket updates

Autore: nik29-coordinator
Versione: 2.1.0
"""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

MANUS_API_BASE = "https://api.manus.ai"
MANUS_API_KEY = os.environ.get("MANUS_API_KEY", "")
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")

# Polling backoff: 5s, 10s, 20s, 30s, poi ogni 30s
POLL_INTERVALS = [5, 10, 20, 30]
POLL_MAX_SECONDS = 1200  # 20 minuti (era 600)

# Rate limit locale: max 10 task.create al minuto
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60

logger = logging.getLogger("manus_tool")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Eccezioni personalizzate
# ---------------------------------------------------------------------------

class ManusToolError(Exception): pass
class ManusAPIKeyMissing(ManusToolError): pass
class ManusAPIError(ManusToolError): pass
class ManusRateLimitError(ManusToolError): pass
class ManusTimeoutError(ManusToolError): pass

# ---------------------------------------------------------------------------
# Schema di output strutturato
# ---------------------------------------------------------------------------

STRUCTURED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": { "type": "string", "description": "The main answer/result" },
        "explanation": { "type": "string", "description": "How and why this solution works" },
        "lessons_learned": { 
            "type": "array", 
            "items": { "type": "string" },
            "description": "Key lessons nik29 should remember for the future"
        },
        "suggested_memory_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": { "type": "string" },
                    "value": { "type": "string" }
                },
                "required": ["key", "value"],
                "additionalProperties": False
            },
            "description": "Facts/preferences to save in nik29 memory"
        },
        "files_content": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {
                    "filename": { "type": "string" },
                    "content": { "type": "string" }
                },
                "required": ["filename", "content"],
                "additionalProperties": False
            },
            "description": "File contents to save (code fixes, configs, etc)"
        }
    },
    "required": ["answer", "explanation", "lessons_learned", "suggested_memory_updates", "files_content"],
    "additionalProperties": False
}

PROJECT_INSTRUCTION = """Sei Manus, assistente AI avanzato. Stai rispondendo a una richiesta del coordinatore nik29, un agente autonomo che gestisce task per Nicola.

## Chi è Nicola
- Nicola Sgambelluri, titolare de "Il Dormire" (materassi/cuscini/reti), Siderno (RC)
- Non ha competenze informatiche - le soluzioni devono essere pratiche e semplici da applicare
- Preferenze: italiano, informale, diretto, deploy singoli, test prima di pubblicare

## Cos'è nik29
- Coordinatore autonomo v0.5 in Docker (FastAPI, porta 4001)
- Tool: Shell, Web Search, File Manager, Memoria, create_tool (auto-evolutivo)
- Sub-agenti: immagini (Pillow+Rembg, porta 4000)
- Gira su Mac M4 Max (dev), futuro deploy su VPS Aruba

## Come rispondere
- Rispondi in modo strutturato (il sistema usa structured_output)
- Nella risposta includi SEMPRE: cosa hai fatto, perché funziona, cosa nik29 dovrebbe ricordare
- Se crei codice, includi il file completo (non frammenti)
- Se il task richiede modifiche a file esistenti, specifica esattamente quali righe cambiare
- Preferisci soluzioni semplici e robuste

## Architettura ildormire.com
- VPS Aruba (188.213.175.219, Ubuntu 24.04, 8CPU/16GB RAM)
- Stack: Node.js 22 + MySQL + PM2 + Nginx + SSL
- GitHub repo per il sito
- Prodotti solo da database (custom_products), NO file statici"""

# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class ManusTool:
    def __init__(self):
        self.pending_file = Path(MEMORY_DIR) / "pending_manus_requests.json"
        self.log_file = Path(MEMORY_DIR) / "manus_requests_log.json"
        self.project_file = Path(MEMORY_DIR) / "manus_project.json"
        self.memories_file = Path(MEMORY_DIR) / "memories.json"
        self.tools_dir = Path(MEMORY_DIR) / "tools"
        self._rate_limit_timestamps: list[float] = []
        self._ensure_files()

    def _ensure_files(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        os.makedirs(self.tools_dir, exist_ok=True)
        if not self.pending_file.exists():
            self._write_json(self.pending_file, {"pending": []})
        if not self.log_file.exists():
            self._write_json(self.log_file, {"requests": []})

    def _read_json(self, path: Path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_json(self, path: Path, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _check_rate_limit(self):
        now = datetime.now(timezone.utc).timestamp()
        self._rate_limit_timestamps = [
            ts for ts in self._rate_limit_timestamps
            if now - ts < RATE_LIMIT_WINDOW
        ]
        if len(self._rate_limit_timestamps) >= RATE_LIMIT_MAX:
            raise ManusRateLimitError(
                f"Rate limit raggiunto: max {RATE_LIMIT_MAX} richieste "
                f"ogni {RATE_LIMIT_WINDOW} secondi. Riprova tra qualche minuto."
            )

    def _record_rate_limit(self):
        self._rate_limit_timestamps.append(datetime.now(timezone.utc).timestamp())

    def _validate_api_key(self):
        if not MANUS_API_KEY:
            raise ManusAPIKeyMissing(
                "MANUS_API_KEY non configurata. "
                "Genera una chiave su: "
                "https://manus.im/app?show_settings=integrations&app_name=api "
                "e aggiungila al docker-compose.yml."
            )

    async def _get_or_create_project(self) -> str:
        """Recupera il project_id salvato o crea un nuovo progetto su Manus."""
        data = self._read_json(self.project_file)
        if "project_id" in data:
            return data["project_id"]

        url = f"{MANUS_API_BASE}/v2/project.create"
        headers = {
            "x-manus-api-key": MANUS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "name": "nik29-coordinator",
            "instruction": PROJECT_INSTRUCTION
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code != 200:
                raise ManusAPIError(f"Errore creazione progetto: {resp.text}")
                
            resp_data = resp.json()
            if not resp_data.get("ok"):
                raise ManusAPIError(f"API errore: {resp_data.get('error')}")
                
            project_obj = resp_data.get("project", {})
            project_id = project_obj.get("id") if isinstance(project_obj, dict) else None
            if not project_id:
                # Fallback: prova a livello root
                project_id = resp_data.get("project_id")
            if project_id:
                self._write_json(self.project_file, {"project_id": project_id})
                logger.info(f"Progetto Manus creato: {project_id}")
                return project_id
            raise ManusAPIError(f"Nessun project_id restituito. Risposta: {resp_data}")

    def _enrich_request(self, original_request: str) -> str:
        """Arricchisce la richiesta con il contesto dalla memoria."""
        memories = self._read_json(self.memories_file)
        recent_facts = []
        
        if isinstance(memories, dict) and "facts" in memories:
            recent_facts = memories.get("facts", [])[-10:]
        elif isinstance(memories, list):
            recent_facts = memories[-10:]
            
        facts_text = "\n".join(f"- {fact}" for fact in recent_facts) if recent_facts else "Nessun fatto in memoria."

        enriched = f"""## Richiesta
{original_request}

## Contesto
- Utente: Nicola, titolare de "Il Dormire" (materassi/cuscini), Siderno (RC)
- Progetto: nik29-coordinator v0.5, Docker container, FastAPI, porta 4001
- Architettura: Mac M4 Max (dev) → VPS Aruba (prod), Node.js + MySQL per ildormire.com
- Preferenze: deploy singoli, test prima di pubblicare, italiano, informale

## Memoria rilevante
{facts_text}
"""
        return enriched

    def propose(self, request: str, reason: str, urgency: str = "medium") -> str:
        self._validate_api_key()

        if urgency not in ("low", "medium", "high"):
            urgency = "medium"

        request_id = str(uuid.uuid4())[:8]

        proposal = {
            "id": request_id,
            "request": request,
            "reason": reason,
            "urgency": urgency,
            "status": "pending_confirmation",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "task_id": None,
            "result": None
        }

        data = self._read_json(self.pending_file)
        data.setdefault("pending", []).append(proposal)
        self._write_json(self.pending_file, data)

        logger.info(f"Proposta Manus creata: {request_id} - {request[:80]}")
        urgency_emoji = {"low": "\U0001f4cb", "medium": "\u26a1", "high": "\U0001f6a8"}.get(urgency, "\u26a1")

        return (
            f"{urgency_emoji} Ho preparato una richiesta per Manus.\n\n"
            f"**Cosa chiederò:** {request}\n"
            f"**Motivo:** {reason}\n"
            f"**Urgenza:** {urgency}\n"
            f"**ID richiesta:** {request_id}\n\n"
            f"\u26a0\ufe0f L'esecuzione consuma crediti Manus. Conferma per procedere."
        )

    async def execute(
        self,
        request_id: Optional[str] = None,
        status_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> str:
        """
        Esegue una richiesta Manus.
        
        Args:
            request_id: ID della richiesta (opzionale, usa l'ultima pendente)
            status_callback: Funzione async opzionale chiamata periodicamente
                             durante il polling per inviare aggiornamenti di stato
                             (es. "Manus sta lavorando... 3 minuti passati")
        """
        self._validate_api_key()
        self._check_rate_limit()

        data = self._read_json(self.pending_file)
        pending = data.get("pending", [])

        if not pending:
            return "\u274c Nessuna richiesta Manus pendente da eseguire."

        proposal = None
        if request_id:
            for p in pending:
                if p["id"] == request_id and p["status"] == "pending_confirmation":
                    proposal = p
                    break
            if not proposal:
                return f"\u274c Richiesta '{request_id}' non trovata o già eseguita."
        else:
            pending_proposals = [p for p in pending if p["status"] == "pending_confirmation"]
            if not pending_proposals:
                return "\u274c Nessuna richiesta Manus in attesa di conferma."
            proposal = pending_proposals[-1]

        proposal["status"] = "executing"
        self._write_json(self.pending_file, data)

        try:
            project_id = await self._get_or_create_project()
            enriched_request = self._enrich_request(proposal["request"])
            
            task_id, task_url = await self._create_task(enriched_request, project_id)
            proposal["task_id"] = task_id
            self._write_json(self.pending_file, data)

            self._record_rate_limit()
            logger.info(f"Task Manus creato: {task_id} per richiesta {proposal['id']}")

            # Invia status iniziale
            if status_callback:
                await status_callback(f"\U0001f680 Task Manus avviato. Polling in corso... (timeout: {POLL_MAX_SECONDS // 60} min)")

            result_dict = await self._poll_task(task_id, status_callback=status_callback)
            
            # Elabora il risultato strutturato
            if isinstance(result_dict, dict) and result_dict.get("success"):
                val = result_dict.get("value", {})
                answer = val.get("answer", "Nessuna risposta.")
                explanation = val.get("explanation", "")
                
                # Salva file
                files_saved = []
                for f in val.get("files_content", []) or []:
                    fname = f.get("filename")
                    fcontent = f.get("content")
                    if fname and fcontent:
                        fpath = self.tools_dir / fname
                        with open(fpath, "w", encoding="utf-8") as out_f:
                            out_f.write(fcontent)
                        files_saved.append(fname)
                
                # Formatta risultato
                final_result = f"\u2705 Manus ha completato il task.\n\n**Risposta:**\n{answer}\n\n**Spiegazione:**\n{explanation}"
                if files_saved:
                    final_result += f"\n\n**File salvati:** {', '.join(files_saved)}"
                
                proposal["result"] = final_result
            else:
                final_result = str(result_dict)
                proposal["result"] = final_result

            proposal["status"] = "completed"
            proposal["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json(self.pending_file, data)
            self._log_request(proposal)
            self._cleanup_pending(data)

            return final_result + f"\n\n\U0001f517 Task URL: {task_url}"

        except ManusTimeoutError:
            proposal["status"] = "timeout"
            proposal["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json(self.pending_file, data)
            self._log_request(proposal)
            return f"\u23f1\ufe0f Timeout: Manus non ha completato entro {POLL_MAX_SECONDS // 60} minuti."
        except Exception as e:
            proposal["status"] = "failed"
            proposal["error"] = str(e)
            proposal["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json(self.pending_file, data)
            self._log_request(proposal)
            return f"\u274c Errore: {str(e)}"

    def get_pending(self) -> str:
        data = self._read_json(self.pending_file)
        pending = [p for p in data.get("pending", []) if p["status"] == "pending_confirmation"]
        if not pending:
            return "Nessuna richiesta Manus in attesa di conferma."

        lines = ["\U0001f4cb **Richieste Manus pendenti:**\n"]
        for p in pending:
            urgency_emoji = {"low": "\U0001f4cb", "medium": "\u26a1", "high": "\U0001f6a8"}.get(p.get("urgency", "medium"), "\u26a1")
            lines.append(f"{urgency_emoji} **[{p['id']}]** {p['request'][:100]}\n   Motivo: {p['reason'][:80]}\n   Creata: {p['created_at']}\n")
        return "\n".join(lines)

    async def _create_task(self, request: str, project_id: str) -> tuple[str, str]:
        url = f"{MANUS_API_BASE}/v2/task.create"
        headers = {
            "x-manus-api-key": MANUS_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "project_id": project_id,
            "message": {
                "content": request
            },
            "structured_output_schema": STRUCTURED_OUTPUT_SCHEMA,
            "locale": "it",
            "hide_in_task_list": False,
            "agent_profile": "manus-1.6"
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException:
                raise ManusAPIError("Timeout nella connessione all'API Manus.")
            except httpx.ConnectError:
                raise ManusAPIError("Impossibile connettersi all'API Manus. Verifica la rete.")

            if resp.status_code == 429:
                raise ManusRateLimitError("Rate limit API Manus raggiunto.")
            if resp.status_code != 200:
                raise ManusAPIError(f"HTTP {resp.status_code}: {resp.text[:200]}")

            data = resp.json()
            if not data.get("ok"):
                error_info = data.get("error", {})
                raise ManusAPIError(f"API Manus errore: {error_info.get('message')}")

            task_id = data.get("task_id", "")
            task_url = data.get("task_url", f"https://manus.im/task/{task_id}")
            return task_id, task_url

    async def _poll_task(
        self,
        task_id: str,
        status_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ):
        """
        Polling del task con aggiornamenti di stato periodici.
        
        Args:
            task_id: ID del task Manus
            status_callback: Funzione async per inviare status updates al client
        """
        url = f"{MANUS_API_BASE}/v2/task.listMessages"
        headers = {"x-manus-api-key": MANUS_API_KEY}
        params = {"task_id": task_id, "order": "desc", "limit": 20}

        elapsed = 0
        poll_index = 0
        last_status_update = 0  # Secondi dall'ultimo status update inviato

        while elapsed < POLL_MAX_SECONDS:
            wait_time = POLL_INTERVALS[poll_index] if poll_index < len(POLL_INTERVALS) else 30
            await asyncio.sleep(wait_time)
            elapsed += wait_time
            poll_index += 1

            # Invia status update ogni ~60 secondi
            if status_callback and (elapsed - last_status_update) >= 60:
                minutes = elapsed // 60
                remaining = (POLL_MAX_SECONDS - elapsed) // 60
                await status_callback(
                    f"\u23f3 Manus sta lavorando... {minutes} min passati "
                    f"(timeout tra {remaining} min)"
                )
                last_status_update = elapsed

            async with httpx.AsyncClient(timeout=30) as client:
                try:
                    resp = await client.get(url, headers=headers, params=params)
                except Exception:
                    continue

                if resp.status_code == 429:
                    if status_callback:
                        await status_callback("\u26a0\ufe0f Rate limit API, attendo 60s...")
                    await asyncio.sleep(60)
                    elapsed += 60
                    continue
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not data.get("ok"):
                    continue

                events = data.get("data", [])
                status, result = self._parse_events(events)

                if status == "stopped":
                    if status_callback:
                        await status_callback("\u2705 Manus ha completato!")
                    return result
                elif status == "error":
                    raise ManusAPIError(f"Task fallito: {result}")
                elif status == "waiting":
                    return f"\u26a0\ufe0f Manus ha bisogno di input aggiuntivo: {result}\nTask ID: {task_id}"

        raise ManusTimeoutError(f"Task {task_id} non completato entro {POLL_MAX_SECONDS}s")

    def _parse_events(self, events: list):
        latest_status = "running"
        result_content = None
        waiting_description = ""

        for event in events:
            event_type = event.get("type", "")

            if event_type == "structured_output_result":
                result_content = event.get("structured_output_result")
                latest_status = "stopped"
                break
                
            if event_type == "status_update":
                status_data = event.get("status_update", {})
                agent_status = status_data.get("agent_status", "")

                if agent_status == "stopped":
                    latest_status = "stopped"
                elif agent_status == "error":
                    latest_status = "error"
                    result_content = status_data.get("error_message", "Errore sconosciuto")
                    break
                elif agent_status == "waiting":
                    status_detail = status_data.get("status_detail", {})
                    if status_detail.get("waiting_for_event_type") == "messageAskUser":
                        latest_status = "waiting"
                        result_content = status_detail.get("waiting_description", "Input richiesto")
                        break

        # Fallback a messaggi testuali se non c'è structured_output
        if latest_status == "stopped" and not result_content:
            for event in events:
                if event.get("type") == "assistant_message":
                    msg = event.get("assistant_message", {}).get("content", "")
                    if msg:
                        result_content = msg
                        break

        return latest_status, result_content

    def _log_request(self, proposal: dict):
        log_data = self._read_json(self.log_file)
        log_entry = {
            "id": proposal.get("id"),
            "request": proposal.get("request"),
            "status": proposal.get("status"),
            "task_id": proposal.get("task_id"),
            "created_at": proposal.get("created_at"),
            "completed_at": proposal.get("completed_at"),
            "error": proposal.get("error")
        }
        log_data.setdefault("requests", []).append(log_entry)
        log_data["requests"] = log_data["requests"][-200:]
        self._write_json(self.log_file, log_data)

    def _cleanup_pending(self, data: dict):
        pending = data.get("pending", [])
        active = [p for p in pending if p["status"] == "pending_confirmation"]
        completed = [p for p in pending if p["status"] != "pending_confirmation"]
        data["pending"] = active + completed[-5:]
        self._write_json(self.pending_file, data)

manus_tool = ManusTool()
