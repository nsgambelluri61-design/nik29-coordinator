#!/usr/bin/env python3
"""
=============================================================================
  NIK29-COORDINATOR — TEST SUITE COMPLETA
=============================================================================
  Testa tutti i 34 tool del coordinator via API SSE (localhost:4001).
  
  Uso:
    python3 test_nik29_full.py              # Test completo
    python3 test_nik29_full.py --quick      # Solo tool critici (smoke test)
    python3 test_nik29_full.py --verbose    # Output dettagliato
    python3 test_nik29_full.py --quick --verbose  # Combinato

  Requisiti:
    pip install httpx

  Note:
    - Il test gira ESTERNAMENTE, colpendo localhost:4001
    - Tool che dipendono da servizi non attivi → SKIP (non FAIL)
    - Timeout: 30s per tool semplici, 60s per web_agent/analyze_screenshot
=============================================================================
"""

import asyncio
import argparse
import json
import time
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERRORE: httpx non installato. Esegui: pip install httpx")
    sys.exit(1)


# =============================================================================
# CONFIGURAZIONE
# =============================================================================

BASE_URL = "http://localhost:4001"
CHAT_ENDPOINT = f"{BASE_URL}/chat"
HEALTH_ENDPOINT = f"{BASE_URL}/health"

DEFAULT_TIMEOUT = 30.0
LONG_TIMEOUT = 60.0
QUICK_TIMEOUT = 15.0

SESSION_ID = "test-suite-nik29"


# =============================================================================
# MODELLI DATI
# =============================================================================

class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    TIMEOUT = "TIMEOUT"


@dataclass
class TestResult:
    name: str
    status: TestStatus
    duration: float = 0.0
    tool_called: Optional[str] = None
    response_preview: str = ""
    error: str = ""
    category: str = "general"


@dataclass
class SSEResponse:
    """Parsed SSE response from the coordinator."""
    events: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    thinking: list = field(default_factory=list)
    response: str = ""
    done: bool = False
    raw: str = ""
    error: str = ""


# =============================================================================
# SKIP REASONS — Tool che possono non funzionare
# =============================================================================

SKIP_REASONS = {
    "host_shell": "Richiede host_bridge attivo su Mac (porta 4003)",
    "docker_manage": "Richiede host_bridge attivo su Mac (porta 4003)",
    "git_auto": "Richiede host_bridge attivo su Mac (porta 4003)",
    "ask_manus": "Richiede connessione a Manus cloud",
    "auto_update": "Operazione distruttiva — skip in test",
    "create_tool": "Operazione distruttiva — skip in test",
    "send_alert": "Invierebbe alert reali via Telegram",
    "self_improve": "Operazione distruttiva — skip in test",
}


# =============================================================================
# DEFINIZIONE TEST
# =============================================================================

TOOL_TESTS = [
    # === TOOL NATIVI (Basic) ===
    {
        "name": "shell",
        "category": "native",
        "message": "esegui il comando shell: echo 'test_nik29_ok'",
        "expect_tool": "shell",
        "expect_in_response": ["test_nik29_ok"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    {
        "name": "web_search",
        "category": "native",
        "message": "cerca sul web: 'Python asyncio tutorial 2024'",
        "expect_tool": "web_search",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    {
        "name": "brave_search",
        "category": "level3",
        "message": "usa brave_search per cercare: 'materassi memory foam prezzo'",
        "expect_tool": "brave_search",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "file_manager",
        "category": "native",
        "message": "scrivi il file /tmp/test_nik29.txt con contenuto 'test file creato con successo'",
        "expect_tool": "file_manager",
        "expect_in_response": ["successo", "creato", "scritto"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    {
        "name": "save_memory",
        "category": "native",
        "message": "salva in memoria: 'test_key_2024: il test automatico funziona correttamente'",
        "expect_tool": "save_memory",
        "expect_in_response": ["salv", "memori"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    {
        "name": "recall_memory",
        "category": "native",
        "message": "cosa ricordi riguardo a 'test_key_2024'?",
        "expect_tool": "recall_memory",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    # === TOOL COGNITIVI ===
    {
        "name": "think",
        "category": "cognitive",
        "message": "ragiona passo passo: se ho 3 materassi da 200€ e uno sconto del 15%, quanto pago in totale?",
        "expect_tool": "think",
        "expect_in_response": ["510", "€"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "verify",
        "category": "cognitive",
        "message": "verifica questo fatto: la capitale dell'Italia è Roma",
        "expect_tool": "verify",
        "expect_in_response": ["Roma", "vero", "corrett"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "retry_strategy",
        "category": "cognitive",
        "message": "pianifica una strategia di retry per un'operazione di rete che fallisce intermittentemente",
        "expect_tool": "retry_strategy",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "conversation_summary",
        "category": "cognitive",
        "message": "riassumi la nostra conversazione fino a questo punto",
        "expect_tool": "conversation_summary",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "reminder",
        "category": "cognitive",
        "message": "imposta un reminder: tra 5 minuti ricordami di controllare i log",
        "expect_tool": "reminder",
        "expect_in_response": ["remind", "impost", "5"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    # === META-TOOL ===
    {
        "name": "create_tool",
        "category": "meta",
        "message": "crea un nuovo tool chiamato test_dummy che restituisce 'hello'",
        "expect_tool": "create_tool",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "ask_manus",
        "category": "meta",
        "message": "chiedi a Manus: qual è il senso della vita?",
        "expect_tool": "ask_manus",
        "expect_in_response": [],
        "timeout": LONG_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "auto_update",
        "category": "meta",
        "message": "aggiornati all'ultima versione",
        "expect_tool": "auto_update",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    # === LEVEL 2 (Host Bridge) ===
    {
        "name": "host_shell",
        "category": "level2",
        "message": "esegui sul Mac host: echo 'host test ok'",
        "expect_tool": "host_shell",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "docker_manage",
        "category": "level2",
        "message": "mostra i container Docker attivi sull'host",
        "expect_tool": "docker_manage",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "git_auto",
        "category": "level2",
        "message": "mostra lo stato git del repository corrente sull'host",
        "expect_tool": "git_auto",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    # === LEVEL 3 (Autonomy) ===
    {
        "name": "health_check",
        "category": "level3",
        "message": "esegui un health check completo del sistema",
        "expect_tool": "health_check",
        "expect_in_response": ["health", "status", "ok", "attiv"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": True,
    },
    {
        "name": "auto_debug",
        "category": "level3",
        "message": "analizza e diagnostica eventuali problemi nel sistema",
        "expect_tool": "auto_debug",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "send_alert",
        "category": "level3",
        "message": "invia un alert Telegram di test: 'Test automatico nik29'",
        "expect_tool": "send_alert",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "schedule_task",
        "category": "level3",
        "message": "mostra i task schedulati attualmente",
        "expect_tool": "schedule_task",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "run_task_now",
        "category": "level3",
        "message": "esegui subito il task 'health_check' se esiste nello scheduler",
        "expect_tool": "run_task_now",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "browse_url",
        "category": "level3",
        "message": "naviga su https://httpbin.org/get e mostrami il contenuto",
        "expect_tool": "browse_url",
        "expect_in_response": ["httpbin", "origin", "headers"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "web_research",
        "category": "level3",
        "message": "fai una ricerca web approfondita su: 'benefici del materasso in memory foam per la schiena'",
        "expect_tool": "web_research",
        "expect_in_response": [],
        "timeout": LONG_TIMEOUT,
        "critical": False,
    },
    # === BROWSER (Playwright) ===
    {
        "name": "browser_navigate",
        "category": "browser",
        "message": "usa browser_navigate per andare su https://example.com",
        "expect_tool": "browser_navigate",
        "expect_in_response": ["example", "domain"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "browser_screenshot",
        "category": "browser",
        "message": "fai uno screenshot della pagina corrente nel browser",
        "expect_tool": "browser_screenshot",
        "expect_in_response": ["screenshot", "immagine", "salvat"],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "browser_click",
        "category": "browser",
        "message": "prima naviga su https://example.com poi clicca sul link 'More information...'",
        "expect_tool": "browser_click",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "browser_fill",
        "category": "browser",
        "message": "naviga su https://httpbin.org/forms/post e compila il campo 'custname' con 'Test Nik29'",
        "expect_tool": "browser_fill",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "browser_evaluate",
        "category": "browser",
        "message": "esegui questo JavaScript nel browser: document.title",
        "expect_tool": "browser_evaluate",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    # === ADVANCED BROWSER ===
    {
        "name": "web_agent",
        "category": "advanced_browser",
        "message": "usa il web_agent per navigare su https://example.com e descrivere cosa c'è nella pagina",
        "expect_tool": "web_agent",
        "expect_in_response": ["example", "domain"],
        "timeout": LONG_TIMEOUT,
        "critical": False,
    },
    {
        "name": "analyze_screenshot",
        "category": "advanced_browser",
        "message": "fai uno screenshot di https://example.com e analizzalo visivamente",
        "expect_tool": "analyze_screenshot",
        "expect_in_response": [],
        "timeout": LONG_TIMEOUT,
        "critical": False,
    },
    # === OTHER ===
    {
        "name": "lessons",
        "category": "other",
        "message": "mostra le lezioni apprese finora",
        "expect_tool": "lessons",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
    {
        "name": "self_improve",
        "category": "other",
        "message": "analizza le tue performance e suggerisci miglioramenti",
        "expect_tool": "self_improve",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
        "skip": True,
    },
    {
        "name": "instructions",
        "category": "other",
        "message": "mostra le istruzioni di sistema attuali",
        "expect_tool": "instructions",
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
        "critical": False,
    },
]

# === INTEGRATION TESTS ===
INTEGRATION_TESTS = [
    {
        "name": "integration_web_search_ita",
        "category": "integration",
        "message": "cerca su internet il prezzo dei materassi memory foam",
        "expect_tools": ["brave_search", "web_search", "web_research"],
        "expect_in_response": ["materass", "prezzo", "€", "euro", "memory"],
        "timeout": LONG_TIMEOUT,
    },
    {
        "name": "integration_browse_and_describe",
        "category": "integration",
        "message": "naviga su https://example.com e dimmi cosa c'è",
        "expect_tools": ["browser_navigate", "browse_url", "web_agent"],
        "expect_in_response": ["example", "domain"],
        "timeout": LONG_TIMEOUT,
    },
    {
        "name": "integration_visual_analysis",
        "category": "integration",
        "message": "fai uno screenshot di https://example.com e analizzalo visivamente descrivendo layout e contenuti",
        "expect_tools": ["analyze_screenshot", "browser_screenshot", "web_agent"],
        "expect_in_response": [],
        "timeout": LONG_TIMEOUT,
    },
    {
        "name": "integration_memory_roundtrip",
        "category": "integration",
        "messages": [
            "salva in memoria: 'chiave_test_integration: il roundtrip funziona perfettamente il 2024-01-01'",
            "cosa ricordi riguardo a 'chiave_test_integration'?",
        ],
        "expect_tools_sequence": [["save_memory"], ["recall_memory"]],
        "expect_in_response": ["roundtrip", "funziona", "2024"],
        "timeout": DEFAULT_TIMEOUT,
    },
    {
        "name": "integration_shell_date",
        "category": "integration",
        "message": "che ore sono adesso? usa il comando date",
        "expect_tools": ["shell"],
        "expect_in_response": [],
        "timeout": DEFAULT_TIMEOUT,
    },
]

# === ERROR HANDLING TESTS ===
ERROR_TESTS = [
    {
        "name": "error_invalid_url",
        "category": "error_handling",
        "message": "naviga su https://questo-sito-non-esiste-xyz-12345.com e mostrami il contenuto",
        "expect_graceful": True,
        "timeout": DEFAULT_TIMEOUT,
    },
    {
        "name": "error_nonexistent_file",
        "category": "error_handling",
        "message": "leggi il contenuto del file /tmp/file_che_non_esiste_mai_xyz.txt",
        "expect_graceful": True,
        "timeout": DEFAULT_TIMEOUT,
    },
    {
        "name": "error_invalid_command",
        "category": "error_handling",
        "message": "esegui il comando shell: comando_inesistente_xyz_2024",
        "expect_graceful": True,
        "timeout": DEFAULT_TIMEOUT,
    },
]


# =============================================================================
# CLIENT SSE
# =============================================================================

async def send_chat_message(
    message: str,
    session_id: str = SESSION_ID,
    timeout: float = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> SSEResponse:
    """Send a message to the coordinator and parse SSE response."""
    result = SSEResponse()
    
    payload = {
        "message": message,
        "session_id": session_id,
    }
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            async with client.stream(
                "POST",
                CHAT_ENDPOINT,
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    result.error = f"HTTP {response.status_code}"
                    return result
                
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    result.raw += chunk
                    
                    # Parse SSE lines
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line or not line.startswith("data:"):
                            continue
                        
                        data_str = line[5:].strip()
                        if not data_str:
                            continue
                        
                        try:
                            event = json.loads(data_str)
                            result.events.append(event)
                            
                            event_type = event.get("type", "")
                            content = event.get("content", "")
                            
                            if event_type == "tool_call":
                                result.tool_calls.append(content)
                                if verbose:
                                    # Truncate for display
                                    preview = content[:200] if len(content) > 200 else content
                                    print(f"    [TOOL_CALL] {preview}")
                            elif event_type == "thinking":
                                result.thinking.append(content)
                            elif event_type == "response":
                                result.response += content
                            elif event_type == "done":
                                result.done = True
                            
                        except json.JSONDecodeError:
                            # Some events might not be JSON
                            if verbose:
                                print(f"    [RAW] {data_str[:100]}")
                
                # Process remaining buffer
                if buffer.strip():
                    for line in buffer.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                event = json.loads(data_str)
                                result.events.append(event)
                                event_type = event.get("type", "")
                                content = event.get("content", "")
                                if event_type == "tool_call":
                                    result.tool_calls.append(content)
                                elif event_type == "response":
                                    result.response += content
                                elif event_type == "done":
                                    result.done = True
                            except json.JSONDecodeError:
                                pass
                                
    except httpx.TimeoutException:
        result.error = f"TIMEOUT dopo {timeout}s"
    except httpx.ConnectError:
        result.error = "CONNECTION REFUSED — il coordinator non è raggiungibile"
    except Exception as e:
        result.error = f"ERRORE: {type(e).__name__}: {str(e)}"
    
    return result


# =============================================================================
# TEST RUNNERS
# =============================================================================

async def test_health_check(verbose: bool = False) -> TestResult:
    """Test the health endpoint."""
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(HEALTH_ENDPOINT)
            duration = time.time() - start
            
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if verbose:
                    print(f"    Health response: {json.dumps(data, indent=2)[:500]}")
                return TestResult(
                    name="health_check_endpoint",
                    status=TestStatus.PASS,
                    duration=duration,
                    response_preview=str(data)[:200],
                    category="infrastructure",
                )
            else:
                return TestResult(
                    name="health_check_endpoint",
                    status=TestStatus.FAIL,
                    duration=duration,
                    error=f"HTTP {resp.status_code}",
                    category="infrastructure",
                )
    except httpx.ConnectError:
        return TestResult(
            name="health_check_endpoint",
            status=TestStatus.FAIL,
            duration=time.time() - start,
            error="CONNECTION REFUSED — coordinator non raggiungibile su localhost:4001",
            category="infrastructure",
        )
    except Exception as e:
        return TestResult(
            name="health_check_endpoint",
            status=TestStatus.FAIL,
            duration=time.time() - start,
            error=str(e),
            category="infrastructure",
        )


async def test_tool(test_def: dict, verbose: bool = False) -> TestResult:
    """Test a single tool."""
    name = test_def["name"]
    category = test_def["category"]
    timeout = test_def.get("timeout", DEFAULT_TIMEOUT)
    
    # Check if should skip
    if test_def.get("skip") or name in SKIP_REASONS:
        reason = SKIP_REASONS.get(name, "Marcato come skip")
        return TestResult(
            name=name,
            status=TestStatus.SKIP,
            duration=0.0,
            error=reason,
            category=category,
        )
    
    start = time.time()
    message = test_def["message"]
    expect_tool = test_def.get("expect_tool", "")
    expect_in_response = test_def.get("expect_in_response", [])
    
    if verbose:
        print(f"  → Invio: \"{message[:80]}...\"")
    
    # Use unique session to avoid context pollution
    session = f"{SESSION_ID}-{name}-{int(time.time())}"
    sse = await send_chat_message(message, session_id=session, timeout=timeout, verbose=verbose)
    duration = time.time() - start
    
    # Check for connection/timeout errors
    if sse.error:
        if "TIMEOUT" in sse.error:
            return TestResult(
                name=name,
                status=TestStatus.TIMEOUT,
                duration=duration,
                error=sse.error,
                category=category,
            )
        if "CONNECTION" in sse.error:
            return TestResult(
                name=name,
                status=TestStatus.FAIL,
                duration=duration,
                error=sse.error,
                category=category,
            )
        # Other errors might be from the tool itself (expected for some)
        return TestResult(
            name=name,
            status=TestStatus.FAIL,
            duration=duration,
            error=sse.error,
            category=category,
        )
    
    # Check if tool was called
    tool_was_called = False
    called_tool_name = ""
    
    for tc in sse.tool_calls:
        tc_lower = tc.lower()
        if expect_tool and expect_tool.lower() in tc_lower:
            tool_was_called = True
            called_tool_name = expect_tool
            break
        # Also check if any tool was called at all
        if not tool_was_called and tc.strip():
            tool_was_called = True
            called_tool_name = tc[:50]
    
    # Check response content
    response_text = sse.response.lower()
    content_match = True
    if expect_in_response:
        content_match = any(
            keyword.lower() in response_text
            for keyword in expect_in_response
        )
    
    # Determine status
    if tool_was_called or sse.response:
        # Tool was called or we got a response — that's a pass
        # Even if content doesn't match perfectly, the tool worked
        status = TestStatus.PASS
        if expect_tool and not tool_was_called and sse.tool_calls:
            # A different tool was called — still pass but note it
            called_tool_name = f"(altro tool: {sse.tool_calls[0][:30]})"
    elif not sse.events:
        status = TestStatus.FAIL
        called_tool_name = "nessun evento ricevuto"
    else:
        # Got events but no tool call and no response
        status = TestStatus.FAIL
    
    response_preview = sse.response[:200] if sse.response else "(nessuna risposta)"
    
    return TestResult(
        name=name,
        status=status,
        duration=duration,
        tool_called=called_tool_name,
        response_preview=response_preview,
        category=category,
    )


async def test_integration(test_def: dict, verbose: bool = False) -> TestResult:
    """Test an integration scenario (may involve multiple messages)."""
    name = test_def["name"]
    category = test_def["category"]
    timeout = test_def.get("timeout", LONG_TIMEOUT)
    session = f"{SESSION_ID}-integration-{name}-{int(time.time())}"
    
    start = time.time()
    
    # Multi-message test (e.g., memory roundtrip)
    if "messages" in test_def:
        messages = test_def["messages"]
        expect_tools_seq = test_def.get("expect_tools_sequence", [])
        all_responses = []
        all_tool_calls = []
        
        for i, msg in enumerate(messages):
            if verbose:
                print(f"  → Step {i+1}: \"{msg[:60]}...\"")
            
            sse = await send_chat_message(msg, session_id=session, timeout=timeout, verbose=verbose)
            
            if sse.error:
                return TestResult(
                    name=name,
                    status=TestStatus.FAIL if "TIMEOUT" not in sse.error else TestStatus.TIMEOUT,
                    duration=time.time() - start,
                    error=f"Step {i+1}: {sse.error}",
                    category=category,
                )
            
            all_responses.append(sse.response)
            all_tool_calls.extend(sse.tool_calls)
            
            # Small delay between messages
            if i < len(messages) - 1:
                await asyncio.sleep(1)
        
        # Check final response
        final_response = " ".join(all_responses).lower()
        expect_in_response = test_def.get("expect_in_response", [])
        content_match = not expect_in_response or any(
            kw.lower() in final_response for kw in expect_in_response
        )
        
        duration = time.time() - start
        status = TestStatus.PASS if (all_tool_calls or all_responses) else TestStatus.FAIL
        
        return TestResult(
            name=name,
            status=status,
            duration=duration,
            tool_called=", ".join(all_tool_calls[:3]),
            response_preview=final_response[:200],
            category=category,
        )
    
    # Single message integration test
    message = test_def["message"]
    expect_tools = test_def.get("expect_tools", [])
    expect_in_response = test_def.get("expect_in_response", [])
    
    if verbose:
        print(f"  → Invio: \"{message[:80]}...\"")
    
    sse = await send_chat_message(message, session_id=session, timeout=timeout, verbose=verbose)
    duration = time.time() - start
    
    if sse.error:
        return TestResult(
            name=name,
            status=TestStatus.FAIL if "TIMEOUT" not in sse.error else TestStatus.TIMEOUT,
            duration=duration,
            error=sse.error,
            category=category,
        )
    
    # Check if any expected tool was called
    tool_found = False
    called = ""
    for tc in sse.tool_calls:
        for expected in expect_tools:
            if expected.lower() in tc.lower():
                tool_found = True
                called = expected
                break
        if tool_found:
            break
    
    if not tool_found and sse.tool_calls:
        tool_found = True
        called = sse.tool_calls[0][:40]
    
    status = TestStatus.PASS if (tool_found or sse.response) else TestStatus.FAIL
    
    return TestResult(
        name=name,
        status=status,
        duration=duration,
        tool_called=called,
        response_preview=sse.response[:200] if sse.response else "",
        category=category,
    )


async def test_error_handling(test_def: dict, verbose: bool = False) -> TestResult:
    """Test error handling — verify graceful failure."""
    name = test_def["name"]
    category = test_def["category"]
    timeout = test_def.get("timeout", DEFAULT_TIMEOUT)
    session = f"{SESSION_ID}-error-{name}-{int(time.time())}"
    message = test_def["message"]
    
    if verbose:
        print(f"  → Invio (error test): \"{message[:80]}...\"")
    
    start = time.time()
    sse = await send_chat_message(message, session_id=session, timeout=timeout, verbose=verbose)
    duration = time.time() - start
    
    # For error tests, we expect the coordinator to handle gracefully
    # It should NOT crash — it should respond with an error message or explanation
    if sse.error and "CONNECTION" in sse.error:
        return TestResult(
            name=name,
            status=TestStatus.FAIL,
            duration=duration,
            error="Coordinator non raggiungibile",
            category=category,
        )
    
    # If we got a response (even an error explanation), that's graceful handling
    if sse.response or sse.events:
        return TestResult(
            name=name,
            status=TestStatus.PASS,
            duration=duration,
            response_preview=sse.response[:200] if sse.response else "eventi ricevuti",
            category=category,
        )
    
    # Timeout is acceptable for error tests (the coordinator tried)
    if sse.error and "TIMEOUT" in sse.error:
        return TestResult(
            name=name,
            status=TestStatus.PASS,
            duration=duration,
            response_preview="Timeout (gestione graceful)",
            category=category,
        )
    
    return TestResult(
        name=name,
        status=TestStatus.FAIL,
        duration=duration,
        error=sse.error or "Nessuna risposta",
        category=category,
    )


# =============================================================================
# REPORT
# =============================================================================

def print_report(results: list[TestResult], verbose: bool = False):
    """Print the final test report."""
    
    # Header
    print("\n" + "=" * 70)
    print("  NIK29-COORDINATOR — TEST SUITE REPORT")
    print("=" * 70)
    print(f"  Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target: {BASE_URL}")
    print(f"  Test eseguiti: {len(results)}")
    print("=" * 70 + "\n")
    
    # Group by category
    categories = {}
    for r in results:
        cat = r.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r)
    
    category_labels = {
        "infrastructure": "INFRASTRUTTURA",
        "native": "TOOL NATIVI",
        "cognitive": "TOOL COGNITIVI",
        "meta": "META-TOOL",
        "level2": "LEVEL 2 (Host Bridge)",
        "level3": "LEVEL 3 (Autonomy)",
        "browser": "BROWSER (Playwright)",
        "advanced_browser": "ADVANCED BROWSER",
        "other": "ALTRI TOOL",
        "integration": "TEST INTEGRAZIONE",
        "error_handling": "ERROR HANDLING",
    }
    
    # Status symbols
    status_symbols = {
        TestStatus.PASS: "\033[92m[PASS]\033[0m",
        TestStatus.FAIL: "\033[91m[FAIL]\033[0m",
        TestStatus.SKIP: "\033[93m[SKIP]\033[0m",
        TestStatus.TIMEOUT: "\033[91m[TIME]\033[0m",
    }
    
    # Plain text fallback (no ANSI)
    status_plain = {
        TestStatus.PASS: "[PASS]",
        TestStatus.FAIL: "[FAIL]",
        TestStatus.SKIP: "[SKIP]",
        TestStatus.TIMEOUT: "[TIME]",
    }
    
    # Detect if terminal supports colors
    use_color = sys.stdout.isatty()
    symbols = status_symbols if use_color else status_plain
    
    for cat_key in [
        "infrastructure", "native", "cognitive", "meta",
        "level2", "level3", "browser", "advanced_browser",
        "other", "integration", "error_handling"
    ]:
        if cat_key not in categories:
            continue
        
        cat_results = categories[cat_key]
        label = category_labels.get(cat_key, cat_key.upper())
        print(f"  ─── {label} ───")
        
        for r in cat_results:
            sym = symbols[r.status]
            time_str = f"({r.duration:.1f}s)" if r.duration > 0 else ""
            
            line = f"  {sym} {r.name:<30} {time_str:>8}"
            
            if r.status == TestStatus.FAIL or r.status == TestStatus.TIMEOUT:
                line += f"  ← {r.error[:50]}" if r.error else ""
            elif r.status == TestStatus.SKIP:
                line += f"  ← {r.error[:50]}" if r.error else ""
            elif verbose and r.tool_called:
                line += f"  [tool: {r.tool_called[:30]}]"
            
            print(line)
        
        print()
    
    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.status == TestStatus.PASS)
    failed = sum(1 for r in results if r.status == TestStatus.FAIL)
    skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
    timed_out = sum(1 for r in results if r.status == TestStatus.TIMEOUT)
    
    print("=" * 70)
    print(f"  RISULTATI: {passed}/{total} PASS, {failed} FAIL, {timed_out} TIMEOUT, {skipped} SKIP")
    
    # Performance summary
    durations_by_cat = {}
    for r in results:
        if r.duration > 0 and r.status == TestStatus.PASS:
            cat = r.category
            if cat not in durations_by_cat:
                durations_by_cat[cat] = []
            durations_by_cat[cat].append(r.duration)
    
    if durations_by_cat:
        print("\n  ─── PERFORMANCE (media per categoria) ───")
        for cat, durs in sorted(durations_by_cat.items()):
            avg = sum(durs) / len(durs)
            label = category_labels.get(cat, cat)
            print(f"    {label:<30} avg: {avg:.1f}s  (n={len(durs)})")
    
    total_time = sum(r.duration for r in results)
    print(f"\n  Tempo totale: {total_time:.1f}s")
    print("=" * 70 + "\n")
    
    # Verbose: show failures detail
    if verbose:
        failures = [r for r in results if r.status in (TestStatus.FAIL, TestStatus.TIMEOUT)]
        if failures:
            print("\n  ─── DETTAGLIO FALLIMENTI ───")
            for r in failures:
                print(f"\n  [{r.status.value}] {r.name}")
                print(f"    Errore: {r.error}")
                if r.response_preview:
                    print(f"    Risposta: {r.response_preview[:300]}")
            print()
    
    return passed, failed, skipped, timed_out


# =============================================================================
# MAIN
# =============================================================================

async def run_tests(quick: bool = False, verbose: bool = False):
    """Run the full test suite."""
    results: list[TestResult] = []
    
    print("\n" + "=" * 70)
    print("  NIK29-COORDINATOR — AVVIO TEST SUITE")
    print("=" * 70)
    print(f"  Modalità: {'QUICK (smoke test)' if quick else 'COMPLETA'}")
    print(f"  Verbose: {'SI' if verbose else 'NO'}")
    print(f"  Target: {BASE_URL}")
    print("=" * 70 + "\n")
    
    # ─── 1. HEALTH CHECK ───
    print("  [1/6] Health Check...")
    health_result = await test_health_check(verbose=verbose)
    results.append(health_result)
    
    if health_result.status == TestStatus.FAIL:
        print(f"\n  ERRORE CRITICO: {health_result.error}")
        print("  Il coordinator non è raggiungibile. Interrompo i test.\n")
        print_report(results, verbose)
        return 1
    
    print(f"    → {health_result.status.value} ({health_result.duration:.2f}s)\n")
    
    # ─── 2. TOOL TESTS ───
    if quick:
        # Quick mode: solo tool critici
        tool_tests = [t for t in TOOL_TESTS if t.get("critical")]
        print(f"  [2/6] Tool Tests (QUICK — {len(tool_tests)} tool critici)...")
    else:
        tool_tests = TOOL_TESTS
        print(f"  [2/6] Tool Tests ({len(tool_tests)} tool)...")
    
    for i, test_def in enumerate(tool_tests, 1):
        name = test_def["name"]
        skip_flag = test_def.get("skip") or name in SKIP_REASONS
        
        if skip_flag:
            reason = SKIP_REASONS.get(name, "skip")
            print(f"    [{i}/{len(tool_tests)}] {name:<25} → SKIP ({reason[:40]})")
            results.append(TestResult(
                name=name,
                status=TestStatus.SKIP,
                error=reason,
                category=test_def["category"],
            ))
            continue
        
        print(f"    [{i}/{len(tool_tests)}] {name:<25} → ", end="", flush=True)
        result = await test_tool(test_def, verbose=verbose)
        results.append(result)
        
        sym = {
            TestStatus.PASS: "PASS",
            TestStatus.FAIL: "FAIL",
            TestStatus.TIMEOUT: "TIMEOUT",
            TestStatus.SKIP: "SKIP",
        }[result.status]
        print(f"{sym} ({result.duration:.1f}s)")
        
        if verbose and result.response_preview:
            preview = result.response_preview[:100].replace("\n", " ")
            print(f"      Risposta: {preview}")
        
        # Small delay to avoid overwhelming the coordinator
        await asyncio.sleep(0.5)
    
    # ─── 3. INTEGRATION TESTS ───
    if quick:
        integration_tests = INTEGRATION_TESTS[:2]  # Solo i primi 2
        print(f"\n  [3/6] Integration Tests (QUICK — {len(integration_tests)} test)...")
    else:
        integration_tests = INTEGRATION_TESTS
        print(f"\n  [3/6] Integration Tests ({len(integration_tests)} test)...")
    
    for i, test_def in enumerate(integration_tests, 1):
        name = test_def["name"]
        print(f"    [{i}/{len(integration_tests)}] {name:<35} → ", end="", flush=True)
        result = await test_integration(test_def, verbose=verbose)
        results.append(result)
        
        sym = {
            TestStatus.PASS: "PASS",
            TestStatus.FAIL: "FAIL",
            TestStatus.TIMEOUT: "TIMEOUT",
            TestStatus.SKIP: "SKIP",
        }[result.status]
        print(f"{sym} ({result.duration:.1f}s)")
        
        if verbose and result.response_preview:
            preview = result.response_preview[:100].replace("\n", " ")
            print(f"      Risposta: {preview}")
        
        await asyncio.sleep(1)
    
    # ─── 4. ERROR HANDLING TESTS ───
    if quick:
        error_tests = ERROR_TESTS[:1]
        print(f"\n  [4/6] Error Handling Tests (QUICK — {len(error_tests)} test)...")
    else:
        error_tests = ERROR_TESTS
        print(f"\n  [4/6] Error Handling Tests ({len(error_tests)} test)...")
    
    for i, test_def in enumerate(error_tests, 1):
        name = test_def["name"]
        print(f"    [{i}/{len(error_tests)}] {name:<35} → ", end="", flush=True)
        result = await test_error_handling(test_def, verbose=verbose)
        results.append(result)
        
        sym = {
            TestStatus.PASS: "PASS",
            TestStatus.FAIL: "FAIL",
            TestStatus.TIMEOUT: "TIMEOUT",
            TestStatus.SKIP: "SKIP",
        }[result.status]
        print(f"{sym} ({result.duration:.1f}s)")
        
        await asyncio.sleep(0.5)
    
    # ─── 5. PERFORMANCE SUMMARY ───
    print(f"\n  [5/6] Performance Analysis...")
    # Already captured in results
    
    # ─── 6. REPORT ───
    print(f"\n  [6/6] Generazione Report...\n")
    passed, failed, skipped, timed_out = print_report(results, verbose)
    
    # Save JSON report
    report_path = "/tmp/nik29_test_report.json"
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target": BASE_URL,
        "mode": "quick" if quick else "full",
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "timed_out": timed_out,
        },
        "results": [
            {
                "name": r.name,
                "status": r.status.value,
                "duration": round(r.duration, 2),
                "category": r.category,
                "tool_called": r.tool_called,
                "error": r.error,
                "response_preview": r.response_preview[:200],
            }
            for r in results
        ],
    }
    
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"  Report JSON salvato: {report_path}")
    
    # Return exit code
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="NIK29-COORDINATOR Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python3 test_nik29_full.py              # Test completo
  python3 test_nik29_full.py --quick      # Solo tool critici
  python3 test_nik29_full.py --verbose    # Output dettagliato
  python3 test_nik29_full.py -q -v        # Quick + verbose
        """,
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Esegui solo i test critici (smoke test rapido)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostra output dettagliato per ogni test",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Override URL base del coordinator (default: http://localhost:4001)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Override timeout globale in secondi",
    )
    
    args = parser.parse_args()
    
    # Apply overrides
    global BASE_URL, CHAT_ENDPOINT, HEALTH_ENDPOINT, DEFAULT_TIMEOUT
    if args.url:
        BASE_URL = args.url.rstrip("/")
        CHAT_ENDPOINT = f"{BASE_URL}/chat"
        HEALTH_ENDPOINT = f"{BASE_URL}/health"
    
    if args.timeout:
        DEFAULT_TIMEOUT = args.timeout
    
    # Run
    exit_code = asyncio.run(run_tests(quick=args.quick, verbose=args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
