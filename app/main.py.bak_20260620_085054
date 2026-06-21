"""
nik29-coordinator - Main Application
FastAPI + WebSocket + Frontend Chat inline + Endpoints

v0.6.0 - Tool cognitivi, self-improve, auto-update, instructions
"""

import os
import uuid
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Set
from fastapi import FastAPI, UploadFile, File, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse

from app.coordinator import coordinator
from app.agent_client import agent_client
from app.memory import memory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/data/workspace")
HOST_URL = os.environ.get("HOST_URL", "http://localhost:4001")

app = FastAPI(title="nik29-coordinator", version="0.6.0")

# Assicura che workspace esista
os.makedirs(WORKSPACE_DIR, exist_ok=True)


# ============================================================
# WEBSOCKET CONNECTION MANAGER
# ============================================================

class ConnectionManager:
    """Gestisce le connessioni WebSocket attive e i task in background."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.background_tasks: Dict[str, Set[asyncio.Task]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.background_tasks.setdefault(session_id, set())
        logger.info(f"WebSocket connesso: {session_id}")

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)
        tasks = self.background_tasks.pop(session_id, set())
        for task in tasks:
            task.cancel()
        logger.info(f"WebSocket disconnesso: {session_id}")

    async def send_event(self, session_id: str, event: dict):
        """Invia un evento JSON al client via WebSocket. Non crasha se disconnesso."""
        ws = self.active_connections.get(session_id)
        if ws:
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.warning(f"Invio WS fallito per {session_id}: {e}")
                self.active_connections.pop(session_id, None)

    def add_task(self, session_id: str, task: asyncio.Task):
        """Registra un task in background per una sessione."""
        self.background_tasks.setdefault(session_id, set()).add(task)
        task.add_done_callback(lambda t: self._task_done(session_id, t))

    def _task_done(self, session_id: str, task: asyncio.Task):
        tasks = self.background_tasks.get(session_id)
        if tasks:
            tasks.discard(task)

    def is_connected(self, session_id: str) -> bool:
        return session_id in self.active_connections


manager = ConnectionManager()

# Store per task asincroni
_async_tasks: Dict[str, dict] = {}


# ============================================================
# ENDPOINTS API
# ============================================================

@app.get("/health")
async def health():
    """Health check con versione e stato."""
    return {
        "status": "ok",
        "service": "nik29-coordinator",
        "version": "0.6.0",
        "active_connections": len(manager.active_connections),
        "pending_tasks": len(_async_tasks)
    }


@app.get("/agents")
async def list_agents():
    """Lista sub-agenti registrati."""
    return {"agents": agent_client.registry.list_agents()}


@app.get("/agents/health")
async def agents_health():
    """Stato di salute di tutti i sub-agenti."""
    health_status = await agent_client.check_all_agents_health()
    return {"agents_health": health_status}


@app.post("/chat")
async def chat(request: Request):
    """
    Endpoint POST /chat (backward compatible).
    Riceve messaggio e restituisce stream di eventi SSE.
    """
    body = await request.json()
    user_message = body.get("message", "")
    conversation_id = body.get("conversation_id", str(uuid.uuid4()))
    uploaded_files = body.get("files", [])

    if not user_message.strip():
        return JSONResponse({"error": "Messaggio vuoto"}, status_code=400)

    async def event_stream():
        async for event in coordinator.process_message(
            user_message=user_message,
            conversation_id=conversation_id,
            uploaded_files=uploaded_files
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Status di un task asincrono."""
    task_info = _async_tasks.get(task_id)
    if not task_info:
        return JSONResponse({"error": "Task non trovato"}, status_code=404)
    return task_info


# ============================================================
# WEBSOCKET ENDPOINT
# ============================================================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint per chat non-bloccante.

    Il client invia messaggi JSON:
        {"message": "...", "conversation_id": "...", "files": [...]}

    Il server risponde con eventi JSON:
        {"type": "progress"|"response"|"error"|"status"|"done", "content": "...", "message_id": "..."}

    Caratteristiche:
    - Il client puo' inviare nuovi messaggi ANCHE mentre una risposta precedente e' in corso
    - Le operazioni lunghe (ask_manus_execute) girano in background con aggiornamenti status
    - Ping/pong keep-alive gestito nativamente da Starlette
    """
    await manager.connect(websocket, session_id)

    # Invia conferma connessione
    await manager.send_event(session_id, {
        "type": "status",
        "content": "Connesso a nik29 v0.6.0 via WebSocket",
        "session_id": session_id
    })

    try:
        while True:
            raw = await websocket.receive_text()

            # Gestisci ping manuale dal client
            if raw == "ping":
                await websocket.send_text("pong")
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_event(session_id, {
                    "type": "error",
                    "content": "JSON non valido"
                })
                continue

            user_message = data.get("message", "").strip()
            conversation_id = data.get("conversation_id", str(uuid.uuid4()))
            uploaded_files = data.get("files", [])
            message_id = data.get("message_id", str(uuid.uuid4())[:8])

            if not user_message:
                await manager.send_event(session_id, {
                    "type": "error",
                    "content": "Messaggio vuoto",
                    "message_id": message_id
                })
                continue

            # Lancia il processing in background
            task = asyncio.create_task(
                _process_ws_message(
                    session_id=session_id,
                    message_id=message_id,
                    user_message=user_message,
                    conversation_id=conversation_id,
                    uploaded_files=uploaded_files
                )
            )
            manager.add_task(session_id, task)

            # Conferma ricezione immediata
            await manager.send_event(session_id, {
                "type": "status",
                "content": "Messaggio ricevuto, elaboro...",
                "message_id": message_id
            })

    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"Errore WebSocket {session_id}: {e}")
        manager.disconnect(session_id)


async def _process_ws_message(
    session_id: str,
    message_id: str,
    user_message: str,
    conversation_id: str,
    uploaded_files: list
):
    """
    Processa un messaggio in background e invia eventi via WebSocket.
    Questa funzione gira come asyncio.Task, permettendo al WebSocket
    di continuare a ricevere nuovi messaggi.
    """
    # Registra come task asincrono
    task_id = f"task_{message_id}"
    _async_tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "message_id": message_id,
        "session_id": session_id,
        "started_at": str(asyncio.get_event_loop().time())
    }

    try:
        async for event in coordinator.process_message(
            user_message=user_message,
            conversation_id=conversation_id,
            uploaded_files=uploaded_files
        ):
            event["message_id"] = message_id

            if not manager.is_connected(session_id):
                logger.info(f"Client {session_id} disconnesso, interrompo task {message_id}")
                _async_tasks[task_id]["status"] = "cancelled"
                return

            await manager.send_event(session_id, event)

        # Segnala completamento
        await manager.send_event(session_id, {
            "type": "done",
            "content": "",
            "message_id": message_id
        })
        _async_tasks[task_id]["status"] = "completed"

    except asyncio.CancelledError:
        logger.info(f"Task {message_id} cancellato per sessione {session_id}")
        _async_tasks[task_id]["status"] = "cancelled"
    except Exception as e:
        logger.error(f"Errore processing {message_id}: {e}", exc_info=True)
        await manager.send_event(session_id, {
            "type": "error",
            "content": f"Errore elaborazione: {str(e)}",
            "message_id": message_id
        })
        _async_tasks[task_id]["status"] = "error"
    finally:
        # Cleanup task vecchi (mantieni ultimi 50)
        if len(_async_tasks) > 50:
            keys = sorted(_async_tasks.keys())
            for k in keys[:-50]:
                _async_tasks.pop(k, None)


# ============================================================
# FILE ENDPOINTS
# ============================================================

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload file nel workspace."""
    filename = file.filename or f"upload_{uuid.uuid4().hex[:8]}"
    safe_name = "".join(c for c in filename if c.isalnum() or c in ".-_")
    if not safe_name:
        safe_name = f"file_{uuid.uuid4().hex[:8]}"

    filepath = Path(WORKSPACE_DIR) / safe_name
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "filename": safe_name,
        "url": f"{HOST_URL}/files/{safe_name}",
        "size": len(content)
    }


@app.get("/files/{filepath:path}")
async def serve_file(filepath: str):
    """Serve file dal workspace."""
    full_path = Path(WORKSPACE_DIR) / filepath
    if not full_path.exists() or not full_path.is_file():
        return JSONResponse({"error": "File non trovato"}, status_code=404)
    return FileResponse(full_path)


@app.post("/agents/reload")
async def reload_agents():
    """Ricarica la configurazione degli agenti."""
    agent_client.registry.reload()
    return {"status": "ok", "agents": agent_client.registry.list_agents()}


# ============================================================
# FRONTEND HTML (WebSocket version)
# ============================================================

FRONTEND_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>nik29 - Coordinatore Autonomo v0.6</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-tertiary: #0f3460;
            --bg-input: #1e2a4a;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0b0;
            --text-muted: #6a6a7a;
            --accent: #4fc3f7;
            --accent-hover: #29b6f6;
            --success: #66bb6a;
            --error: #ef5350;
            --warning: #ffa726;
            --border: #2a2a4e;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            overflow: hidden;
        }
        .sidebar {
            width: 240px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 16px;
        }
        .sidebar h2 { font-size: 1.1rem; margin-bottom: 16px; color: var(--accent); }
        .sidebar .version { font-size: 0.7rem; color: var(--text-muted); margin-bottom: 12px; }
        .main { flex: 1; display: flex; flex-direction: column; }
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .message {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.5;
            font-size: 0.9rem;
            word-wrap: break-word;
        }
        .message.user {
            align-self: flex-end;
            background: var(--bg-tertiary);
            border: 1px solid var(--accent);
        }
        .message.assistant {
            align-self: flex-start;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
        }
        .message.progress {
            align-self: flex-start;
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.8rem;
            padding: 4px 16px;
        }
        .message.error {
            align-self: flex-start;
            background: rgba(239, 83, 80, 0.1);
            border: 1px solid var(--error);
            color: var(--error);
        }
        .input-area {
            padding: 16px 20px;
            border-top: 1px solid var(--border);
            display: flex;
            gap: 8px;
            align-items: flex-end;
        }
        .input-area textarea {
            flex: 1;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-primary);
            font-size: 0.9rem;
            resize: none;
            min-height: 42px;
            max-height: 150px;
            outline: none;
        }
        .input-area textarea:focus { border-color: var(--accent); }
        .input-area button {
            background: var(--accent);
            color: #000;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            cursor: pointer;
            font-weight: 600;
        }
        .input-area button:hover { background: var(--accent-hover); }
        #agents-list { margin-top: 12px; }
        .agent-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 0;
            font-size: 0.8rem;
        }
        .agent-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }
        .agent-dot.online { background: var(--success); }
        .agent-dot.offline { background: var(--error); }
        pre { background: #0d1117; padding: 8px; border-radius: 6px; overflow-x: auto; font-size: 0.8rem; }
        code { font-family: 'SF Mono', Menlo, monospace; }
        #upload-indicator { display: none; font-size: 0.75rem; color: var(--warning); padding: 4px 0; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2>nik29</h2>
        <div class="version">v0.6.0 - Coordinatore Autonomo</div>
        <button onclick="newChat()" style="width:100%;padding:8px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;cursor:pointer;margin-bottom:12px;">+ Nuova Chat</button>
        <div style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:4px;">Sub-agenti:</div>
        <div id="agents-list"></div>
    </div>
    <div class="main">
        <div class="messages" id="messages">
            <div class="message assistant">Ciao! Sono nik29 v0.6.0, il tuo coordinatore autonomo. Come posso aiutarti?</div>
        </div>
        <div id="upload-indicator"></div>
        <div class="input-area">
            <input type="file" id="file-input" style="display:none" onchange="handleFileSelect(event)">
            <button onclick="document.getElementById('file-input').click()" style="background:var(--bg-tertiary);color:var(--text-secondary);padding:10px 12px;">+</button>
            <textarea id="input" placeholder="Scrivi un messaggio..." onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
            <button onclick="sendMessage()">Invia</button>
        </div>
    </div>
    <script>
        let ws = null;
        let conversationId = 'conv_' + Math.random().toString(36).substr(2, 12);
        let uploadedFiles = [];
        let progressElements = {};

        function connectWebSocket() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const sessionId = 'session_' + Math.random().toString(36).substr(2, 8);
            ws = new WebSocket(protocol + '//' + location.host + '/ws/' + sessionId);
            ws.onopen = () => console.log('WS connesso');
            ws.onmessage = (event) => {
                try { handleWsEvent(JSON.parse(event.data)); } catch(e) { console.error(e); }
            };
            ws.onclose = () => { console.log('WS disconnesso'); setTimeout(connectWebSocket, 3000); };
            ws.onerror = (e) => console.error('WS errore:', e);
        }

        function handleWsEvent(event) {
            const msgId = event.message_id || 'default';
            if (event.type === 'progress' || event.type === 'status') {
                if (!progressElements[msgId]) {
                    progressElements[msgId] = addMessage('progress', event.content);
                } else {
                    progressElements[msgId].innerHTML = renderMarkdown(event.content);
                }
            } else if (event.type === 'response') {
                delete progressElements[msgId];
                addMessage('assistant', event.content);
            } else if (event.type === 'error') {
                delete progressElements[msgId];
                addMessage('error', event.content);
            } else if (event.type === 'done') {
                delete progressElements[msgId];
            }
        }

        function sendMessage() {
            const input = document.getElementById('input');
            const text = input.value.trim();
            if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
            const messageId = 'msg_' + Math.random().toString(36).substr(2, 8);
            addMessage('user', text);
            ws.send(JSON.stringify({
                message: text,
                conversation_id: conversationId,
                files: uploadedFiles,
                message_id: messageId
            }));
            input.value = '';
            input.style.height = 'auto';
            uploadedFiles = [];
            document.getElementById('upload-indicator').style.display = 'none';
        }

        function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 150) + 'px'; }
        function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }
        function newChat() {
            conversationId = 'conv_' + Math.random().toString(36).substr(2, 12);
            uploadedFiles = [];
            Object.keys(progressElements).forEach(k => delete progressElements[k]);
            document.getElementById('messages').innerHTML = '<div class="message assistant">Nuova conversazione iniziata. Come posso aiutarti?</div>';
        }
        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const resp = await fetch('/upload', { method: 'POST', body: formData });
                const data = await resp.json();
                uploadedFiles.push({ name: data.filename, url: data.url });
                const indicator = document.getElementById('upload-indicator');
                indicator.style.display = 'block';
                indicator.textContent = uploadedFiles.map(f => f.name).join(', ');
            } catch (err) { addMessage('error', 'Errore upload: ' + err.message); }
            event.target.value = '';
        }
        function addMessage(type, content) {
            const container = document.getElementById('messages');
            const div = document.createElement('div');
            div.className = 'message ' + type;
            div.innerHTML = renderMarkdown(content);
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
            return div;
        }
        function renderMarkdown(text) {
            if (!text) return '';
            return text
                .replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre><code>$2</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\*([^*]+)\\*/g, '<em>$1</em>')
                .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, '<a href="$2" target="_blank">$1</a>')
                .replace(/^### (.+)$/gm, '<h3>$1</h3>')
                .replace(/^## (.+)$/gm, '<h2>$1</h2>')
                .replace(/^# (.+)$/gm, '<h1>$1</h1>')
                .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
                .replace(/^- (.+)$/gm, '<li>$1</li>')
                .replace(/\\n/g, '<br>');
        }
        async function loadAgents() {
            try {
                const [agentsResp, healthResp] = await Promise.all([fetch('/agents'), fetch('/agents/health')]);
                const agentsData = await agentsResp.json();
                const healthData = await healthResp.json();
                const container = document.getElementById('agents-list');
                container.innerHTML = '';
                if (agentsData.agents.length === 0) {
                    container.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:8px;">Nessun sub-agente</div>';
                    return;
                }
                for (const agent of agentsData.agents) {
                    const isOnline = healthData.agents_health[agent.name];
                    container.innerHTML += '<div class="agent-item"><div class="agent-dot '+(isOnline?'online':'offline')+'"></div><div>'+agent.name+'</div></div>';
                }
            } catch (err) { console.error('Errore caricamento agenti:', err); }
        }
        connectWebSocket();
        loadAgents();
        setInterval(loadAgents, 30000);
        document.getElementById('input').focus();
    </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def frontend():
    """Serve il frontend della chat."""
    return HTMLResponse(content=open("/app/static/index.html").read())
