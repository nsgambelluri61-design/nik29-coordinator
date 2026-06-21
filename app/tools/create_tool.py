"""
Meta-tool: create_tool
Permette al coordinatore nik29 di creare NUOVI tool Python a runtime
quando scopre che gli manca una capacità specifica.

Flusso:
1. propose() → prepara la proposta e chiede conferma utente
2. generate() → genera il codice con LLM, valida, salva
3. test() → esegue test a 3 livelli (syntax, import, execute)
4. list_custom() → lista tool custom attivi

Sicurezza:
- Pattern vietati (os.system, subprocess shell=True, eval, exec, __import__)
- Max 5 tool custom attivi
- Scrittura solo in /app/app/tools/ e /data/memory/
- Test obbligatorio prima dell'attivazione

Autore: nik29-coordinator
Versione: 2.0.0
"""

import os
import re
import ast
import json
import uuid
import logging
import importlib
import importlib.util
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from openai import AsyncOpenAI


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
TOOLS_DIR = "/app/app/tools"
REGISTRY_FILE = Path(MEMORY_DIR) / "custom_tools.json"
MAX_CUSTOM_TOOLS = 5

# Pattern di codice vietato (sicurezza)
FORBIDDEN_PATTERNS = [
    (r"os\.system", "os.system non permesso"),
    (r"subprocess\.(call|run|Popen).*shell\s*=\s*True", "subprocess con shell=True non permesso"),
    (r"\beval\b\(", "eval() non permesso"),
    (r"\bexec\b\(", "exec() non permesso"),
    (r"__import__", "__import__ non permesso"),
]

# Logging
logger = logging.getLogger("create_tool")
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Template per i tool generati
# ---------------------------------------------------------------------------

TOOL_TEMPLATE = '''"""
Tool: {name}
Descrizione: {description}
Creato da: nik29-coordinator (auto-generato)
Data: {datetime}
Capabilities: {capabilities}
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger("{name}_tool")


class {class_name}Tool:
    """Tool per {description}"""

    def __init__(self):
        """Inizializzazione del tool."""
        pass

    async def execute(self, action: str, **kwargs) -> str:
        """
        Esegue l'azione richiesta.

        Args:
            action: Nome dell'azione da eseguire
            **kwargs: Parametri specifici dell'azione

        Returns:
            Risultato dell'esecuzione come stringa
        """
        try:
            method = getattr(self, f"_action_{{action}}", None)
            if method is None:
                return f"Azione '{{action}}' non supportata. Azioni disponibili: {{self.list_actions()}}"
            return await method(**kwargs)
        except Exception as e:
            return f"Errore in {{action}}: {{str(e)}}"

    def list_actions(self) -> list:
        """Lista le azioni disponibili."""
        return [
            m.replace("_action_", "")
            for m in dir(self)
            if m.startswith("_action_")
        ]

{methods_code}
'''

# Prompt per la generazione del codice via LLM
GENERATION_PROMPT = """Sei un generatore di tool Python per un coordinatore AI (nik29-coordinator).
Devi generare SOLO i metodi di azione per un tool, seguendo queste regole.

## REGOLE ASSOLUTE:
1. Usa ESATTAMENTE 4 spazi per l'indentazione (niente tab).
2. Segui un template di struttura di classe rigido: ogni metodo generato deve iniziare con 4 spazi.
3. Mantieni le funzioni brevi e semplici. Evita condizionali annidati complessi.
4. Includi type hints (suggerimenti di tipo) nei parametri e nei valori di ritorno.
5. Ogni metodo di azione deve essere `async def _action_{{nome}}(self, **kwargs) -> str:`
6. I metodi devono restituire SEMPRE una stringa con il risultato.
7. NON usare: os.system, subprocess con shell=True, eval(), exec(), __import__.
8. Puoi importare SOLO: json, re, os.path, pathlib, httpx, asyncio, math, hashlib, base64, urllib.parse.
9. NON scrivere file fuori da /app/app/tools/ e /data/memory/.
10. Gestisci SEMPRE le eccezioni con try/except.
11. Ogni metodo deve avere un docstring.

## TOOL DA GENERARE:
- Nome: {name}
- Descrizione: {description}
- Capabilities (azioni): {capabilities}

## FORMATO OUTPUT:
Restituisci SOLO il codice Python dei metodi, senza la classe wrapper.
Ogni metodo deve iniziare con ESATTAMENTE 4 spazi di indentazione (poiché andrà dentro una classe).
Includi gli import necessari IN CIMA (prima dei metodi, con 0 indentazione).

Esempio di output:
```python
import httpx

    async def _action_fetch_url(self, **kwargs) -> str:
        \"\"\"Scarica il contenuto di un URL.\"\"\"
        url: str = kwargs.get("url", "")
        if not url:
            return "Errore: parametro 'url' richiesto"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                return f"Status: {{resp.status_code}}\\nContenuto (primi 2000 char):\\n{{resp.text[:2000]}}"
        except Exception as e:
            return f"Errore nel fetch: {{str(e)}}"
```

Genera ora i metodi per il tool richiesto:"""


# ---------------------------------------------------------------------------
# Classe principale
# ---------------------------------------------------------------------------

class CreateToolTool:
    """
    Meta-tool che permette al coordinatore di creare nuovi tool a runtime.
    Gestisce proposta, generazione, validazione, test e registrazione.
    """

    def __init__(self):
        self.client = AsyncOpenAI()
        self._ensure_registry()
        self._proposals: dict = {}  # name → proposal data (in-memory)

    # ------------------------------------------------------------------
    # Inizializzazione
    # ------------------------------------------------------------------

    def _ensure_registry(self):
        """Crea il file di registro se non esiste."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        if not REGISTRY_FILE.exists():
            self._write_registry({"tools": [], "version": "1.0"})

    def _read_registry(self) -> dict:
        """Legge il registro dei tool custom."""
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"tools": [], "version": "1.0"}

    def _write_registry(self, data: dict):
        """Scrive il registro dei tool custom."""
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # FASE 1: Proposta
    # ------------------------------------------------------------------

    def propose(self, name: str, description: str, capabilities: list, reason: str) -> str:
        """
        Propone la creazione di un nuovo tool. Non crea nulla.
        Salva la proposta in memoria e restituisce un messaggio per l'utente.

        Args:
            name: Nome del tool (snake_case)
            description: Cosa fa il tool
            capabilities: Lista di azioni che il tool può fare
            reason: Perché serve questo tool

        Returns:
            Messaggio di proposta per l'utente
        """
        # Validazione nome
        if not re.match(r"^[a-z][a-z0-9_]{2,30}$", name):
            return (
                "❌ Nome tool non valido. Deve essere snake_case, "
                "3-31 caratteri, iniziare con lettera minuscola."
            )

        # Controlla se esiste già
        registry = self._read_registry()
        existing_names = [t["name"] for t in registry.get("tools", [])]
        if name in existing_names:
            return f"❌ Un tool con nome '{name}' esiste già. Scegli un altro nome."

        # Controlla limite
        active_tools = [t for t in registry.get("tools", []) if t["status"] == "active"]
        if len(active_tools) >= MAX_CUSTOM_TOOLS:
            return (
                f"❌ Limite raggiunto: max {MAX_CUSTOM_TOOLS} tool custom attivi. "
                f"Disabilita un tool esistente prima di crearne uno nuovo.\n"
                f"Tool attivi: {', '.join(t['name'] for t in active_tools)}"
            )

        # Controlla che non sia un tool built-in
        builtin_names = ["shell", "web_search", "file_manager", "delegate_task",
                         "save_memory", "recall_memory", "ask_manus_propose",
                         "ask_manus_execute", "ask_manus_pending",
                         "create_tool_propose", "create_tool_generate",
                         "create_tool_test", "create_tool_list"]
        if name in builtin_names:
            return f"❌ '{name}' è un tool built-in e non può essere sovrascritto."

        # Salva proposta
        proposal = {
            "name": name,
            "description": description,
            "capabilities": capabilities,
            "reason": reason,
            "proposed_at": datetime.now(timezone.utc).isoformat(),
            "status": "proposed"
        }
        self._proposals[name] = proposal

        # Messaggio per l'utente
        caps_list = "\n".join(f"  - {c}" for c in capabilities)
        return (
            f"🛠️ **Proposta nuovo tool: `{name}`**\n\n"
            f"**Descrizione:** {description}\n"
            f"**Azioni disponibili:**\n{caps_list}\n"
            f"**Motivo:** {reason}\n\n"
            f"⚠️ Se l'utente conferma, genererò il codice con AI, "
            f"lo validerò e lo testerò prima di attivarlo.\n"
            f"Vuoi che proceda con la creazione?"
        )

    # ------------------------------------------------------------------
    # FASE 2: Generazione
    # ------------------------------------------------------------------

    async def generate(self, name: str) -> str:
        """
        Genera il codice del tool, lo valida e lo salva.
        Richiede che il tool sia stato precedentemente proposto.

        Args:
            name: Nome del tool da generare

        Returns:
            Risultato della generazione
        """
        # Verifica che esista una proposta
        proposal = self._proposals.get(name)
        if not proposal:
            return (
                f"❌ Nessuna proposta trovata per '{name}'. "
                f"Usa create_tool_propose prima."
            )

        if proposal["status"] != "proposed":
            return f"❌ Il tool '{name}' è già stato generato (stato: {proposal['status']})."

        description = proposal["description"]
        capabilities = proposal["capabilities"]
        class_name = self._to_class_name(name)

        logger.info(f"Generazione codice per tool: {name}")
        
        # 1. Genera il codice con LLM (con retry mechanism)
        max_retries = 3
        methods_code = ""
        full_code = ""
        syntax_error = None
        security_check = None
        last_error = ""

        for attempt in range(max_retries):
            try:
                methods_code = await self._generate_code_with_llm(
                    name, description, capabilities, retry=(attempt > 0), error_feedback=last_error
                )
            except Exception as e:
                return f"❌ Errore nella generazione del codice: {str(e)}"

            # 2. Validazione sicurezza (pattern vietati)
            security_check = self._check_security(methods_code)
            if security_check:
                last_error = f"Il codice generato contiene pattern vietati:\n{security_check}"
                logger.warning(f"Tentativo {attempt+1}: {last_error}")
                continue

            # 3. Costruisci il file completo
            full_code = self._build_full_code(
                name, description, capabilities, class_name, methods_code
            )

            # 4. Validazione syntax (ast.parse) - Livello 1
            syntax_error = self._validate_syntax(full_code)
            if not syntax_error:
                break  # Sintassi corretta, esci dal ciclo
            
            last_error = f"Errore di sintassi:\n{syntax_error}"
            logger.warning(f"Tentativo {attempt+1}: {last_error}")

        if security_check:
            return (
                f"❌ Il codice generato contiene pattern vietati anche dopo {max_retries} tentativi:\n"
                f"{security_check}\n"
                f"Generazione annullata per sicurezza."
            )

        if syntax_error:
            return (
                f"❌ Errore di sintassi anche dopo {max_retries} tentativi:\n"
                f"```\n{syntax_error}\n```\n"
                f"Generazione fallita. Prova a riformulare le capabilities."
            )

        # 5. Salva il file
        file_path = os.path.join(TOOLS_DIR, f"{name}_tool.py")
        try:
            os.makedirs(TOOLS_DIR, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_code)
        except Exception as e:
            return f"❌ Errore nel salvataggio del file: {str(e)}"

        # 6. Aggiorna il registro
        registry = self._read_registry()
        tool_entry = {
            "name": name,
            "description": description,
            "capabilities": capabilities,
            "class_name": class_name,
            "file_path": file_path,
            "module_name": f"app.tools.{name}_tool",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_test",  # Non ancora attivo fino al test
            "reason": proposal["reason"],
            "test_result": None
        }
        registry.setdefault("tools", []).append(tool_entry)
        self._write_registry(registry)

        # Aggiorna stato proposta
        proposal["status"] = "generated"

        logger.info(f"Tool {name} generato e salvato in {file_path}")

        return (
            f"✅ **Tool `{name}` generato con successo!**\n\n"
            f"📄 File: `{file_path}`\n"
            f"📦 Classe: `{class_name}Tool`\n"
            f"🔧 Azioni: {', '.join(capabilities)}\n\n"
            f"⚠️ Il tool è in stato `pending_test`. "
            f"Esegui `create_tool_test` per attivarlo.\n"
            f"**Livelli test:**\n"
            f"  ✅ Livello 1 (syntax): PASSATO\n"
            f"  ⏳ Livello 2 (import): da testare\n"
            f"  ⏳ Livello 3 (execute): da testare\n"
            f"  ⏳ Livello 4 (test umano): dopo attivazione"
        )

    # ------------------------------------------------------------------
    # FASE 3: Test
    # ------------------------------------------------------------------

    async def test(self, name: str) -> str:
        """
        Esegue test a 3 livelli su un tool generato.
        Se tutti passano, attiva il tool.

        Args:
            name: Nome del tool da testare

        Returns:
            Risultato dei test
        """
        # Trova il tool nel registro
        registry = self._read_registry()
        tool_entry = None
        for t in registry.get("tools", []):
            if t["name"] == name:
                tool_entry = t
                break

        if not tool_entry:
            return f"❌ Tool '{name}' non trovato nel registro."

        if tool_entry["status"] == "active":
            return f"ℹ️ Tool '{name}' è già attivo."

        file_path = tool_entry["file_path"]
        class_name = tool_entry["class_name"]
        module_name = tool_entry["module_name"]

        results = []

        # --- Livello 1: Syntax check ---
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            ast.parse(code)
            results.append("✅ Livello 1 (syntax): PASSATO")
        except SyntaxError as e:
            results.append(f"❌ Livello 1 (syntax): FALLITO - {e}")
            tool_entry["test_result"] = "failed_syntax"
            self._write_registry(registry)
            return "\n".join(results)

        # --- Livello 2: Import check ---
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            results.append("✅ Livello 2 (import): PASSATO")
        except Exception as e:
            results.append(f"❌ Livello 2 (import): FALLITO - {e}")
            tool_entry["test_result"] = "failed_import"
            self._write_registry(registry)
            return "\n".join(results)

        # --- Livello 3: Execute check ---
        try:
            tool_class = getattr(module, f"{class_name}Tool")
            tool_instance = tool_class()
            # Prova a chiamare list_actions
            actions = tool_instance.list_actions()
            if not actions:
                results.append("⚠️ Livello 3 (execute): ATTENZIONE - nessuna azione trovata")
            else:
                # Prova la prima azione con kwargs vuoti (deve gestire l'errore)
                first_action = actions[0]
                result = await tool_instance.execute(first_action)
                # Se non crasha, è ok (anche se restituisce errore per parametri mancanti)
                results.append(
                    f"✅ Livello 3 (execute): PASSATO - "
                    f"azioni: {', '.join(actions)}"
                )
        except Exception as e:
            results.append(f"❌ Livello 3 (execute): FALLITO - {e}")
            tool_entry["test_result"] = "failed_execute"
            self._write_registry(registry)
            return "\n".join(results)

        # --- Tutti i test passati: attiva il tool ---
        tool_entry["status"] = "active"
        tool_entry["test_result"] = "passed"
        tool_entry["activated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_registry(registry)

        results.append("")
        results.append(
            f"🎉 **Tool `{name}` ATTIVATO!**\n"
            f"Il tool è ora disponibile per l'uso.\n"
            f"⏳ Livello 4 (test umano): chiedi all'utente di provarlo."
        )

        logger.info(f"Tool {name} attivato con successo")

        return "\n".join(results)

    # ------------------------------------------------------------------
    # Lista tool custom
    # ------------------------------------------------------------------

    def list_custom(self) -> str:
        """
        Lista tutti i tool custom creati.

        Returns:
            Stringa formattata con la lista dei tool
        """
        registry = self._read_registry()
        tools = registry.get("tools", [])

        if not tools:
            return "📋 Nessun tool custom creato."

        lines = ["📋 **Tool custom registrati:**\n"]
        for t in tools:
            status_emoji = {
                "active": "🟢",
                "disabled": "🔴",
                "pending_test": "🟡",
            }.get(t["status"], "⚪")

            lines.append(
                f"{status_emoji} **{t['name']}** - {t['description']}\n"
                f"   Stato: {t['status']} | "
                f"Creato: {t.get('created_at', 'N/A')[:10]} | "
                f"File: {t['file_path']}\n"
                f"   Azioni: {', '.join(t.get('capabilities', []))}\n"
            )

        active_count = len([t for t in tools if t["status"] == "active"])
        lines.append(f"\n📊 Attivi: {active_count}/{MAX_CUSTOM_TOOLS}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Disabilitazione tool
    # ------------------------------------------------------------------

    def disable(self, name: str) -> str:
        """
        Disabilita un tool custom (non lo elimina).

        Args:
            name: Nome del tool da disabilitare

        Returns:
            Messaggio di conferma
        """
        registry = self._read_registry()
        for t in registry.get("tools", []):
            if t["name"] == name:
                if t["status"] == "disabled":
                    return f"ℹ️ Tool '{name}' è già disabilitato."
                t["status"] = "disabled"
                t["disabled_at"] = datetime.now(timezone.utc).isoformat()
                self._write_registry(registry)
                return f"✅ Tool '{name}' disabilitato."

        return f"❌ Tool '{name}' non trovato."

    # ------------------------------------------------------------------
    # Metodi interni
    # ------------------------------------------------------------------

    async def _generate_code_with_llm(
        self, name: str, description: str, capabilities: list, retry: bool = False, error_feedback: str = ""
    ) -> str:
        """
        Genera il codice dei metodi del tool usando LLM.

        Args:
            name: Nome del tool
            description: Descrizione
            capabilities: Lista di azioni
            retry: Se True, aggiunge istruzioni extra per evitare errori
            error_feedback: Messaggio di errore del tentativo precedente

        Returns:
            Codice Python dei metodi
        """
        prompt = GENERATION_PROMPT.format(
            name=name,
            description=description,
            capabilities=json.dumps(capabilities, ensure_ascii=False)
        )

        if retry:
            prompt += (
                f"\n\n⚠️ ATTENZIONE: il tentativo precedente ha fallito con questo errore:\n{error_feedback}\n\n"
                "Assicurati che:\n"
                "- Usi ESATTAMENTE 4 spazi per l'indentazione iniziale dei metodi (dentro la classe).\n"
                "- Non usi tabulazioni per l'indentazione.\n"
                "- Le f-string siano corrette (usa {{ e }} per le graffe letterali).\n"
                "- I docstring siano chiusi correttamente.\n"
                "- Non ci siano import dentro i metodi, solo all'inizio.\n"
            )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Sei un generatore di codice Python. Restituisci SOLO codice, senza spiegazioni o markdown fence."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3000
            )
            code = response.choices[0].message.content or ""

            # Pulisci eventuali fence markdown
            code = self._clean_code_output(code)

            return code

        except Exception as e:
            raise RuntimeError(f"Errore chiamata LLM: {str(e)}")

    def _clean_code_output(self, code: str) -> str:
        """Rimuove fence markdown e whitespace extra dall'output LLM."""
        # Rimuovi ```python ... ```
        code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
        code = re.sub(r"\n```\s*$", "", code, flags=re.MULTILINE)
        # Rimuovi ``` iniziali/finali residui
        code = code.strip("`").strip()
        return code

    def _check_security(self, code: str) -> Optional[str]:
        """
        Controlla che il codice non contenga pattern vietati.

        Returns:
            None se sicuro, stringa con errore se non sicuro
        """
        violations = []
        for pattern, message in FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                violations.append(f"  - {message}")

        if violations:
            return "\n".join(violations)
        return None

    def _validate_syntax(self, code: str) -> Optional[str]:
        """
        Valida la sintassi Python con ast.parse.

        Returns:
            None se valido, stringa con errore se non valido
        """
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"Linea {e.lineno}: {e.msg}"

    def _to_class_name(self, snake_name: str) -> str:
        """Converte snake_case in PascalCase."""
        return "".join(word.capitalize() for word in snake_name.split("_"))

    def _build_full_code(
        self, name: str, description: str, capabilities: list,
        class_name: str, methods_code: str
    ) -> str:
        """
        Costruisce il file Python completo del tool.

        Separa gli import extra (generati dall'LLM) dal codice dei metodi
        e li inserisce in cima al file.
        """
        # Separa import dai metodi
        extra_imports = []
        method_lines = []
        for line in methods_code.split("\n"):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                # Verifica che non sia un import vietato
                if not any(re.search(p, line) for p, _ in FORBIDDEN_PATTERNS):
                    extra_imports.append(stripped)
            else:
                method_lines.append(line)

        # Ricostruisci i metodi con indentazione corretta
        methods_clean = "\n".join(method_lines).strip()

        # Assicura indentazione a 4 spazi per i metodi e sostituisci i tab
        indented_methods = self._ensure_indentation(methods_clean)

        # Costruisci il file
        now = datetime.now(timezone.utc).isoformat()
        caps_str = ", ".join(capabilities)

        # Import extra in cima
        extra_imports_str = ""
        if extra_imports:
            extra_imports_str = "\n".join(sorted(set(extra_imports))) + "\n"

        full_code = TOOL_TEMPLATE.format(
            name=name,
            description=description,
            datetime=now,
            capabilities=caps_str,
            class_name=class_name,
            methods_code=indented_methods
        )

        # Inserisci import extra dopo gli import standard del template
        if extra_imports_str:
            full_code = full_code.replace(
                "logger = logging.getLogger",
                f"{extra_imports_str}\nlogger = logging.getLogger"
            )

        return full_code

    def _ensure_indentation(self, code: str) -> str:
        """
        Assicura che i metodi abbiano indentazione corretta (4 spazi).
        I metodi devono essere dentro una classe. Sostituisce i tab con 4 spazi.
        """
        # Sostituisci i tab con 4 spazi prima di elaborare
        code = code.replace("\t", "    ")
        
        lines = code.split("\n")
        result = []
        for line in lines:
            if not line.strip():
                result.append("")
            elif line.strip().startswith("async def _action_") or \
                 line.strip().startswith("def _action_"):
                # Metodo: deve avere 4 spazi
                result.append("    " + line.strip())
            elif result and any(
                r.strip().startswith("async def _action_") or
                r.strip().startswith("def _action_")
                for r in result[-10:] if r.strip()
            ):
                # Corpo del metodo: deve avere almeno 8 spazi
                stripped = line.strip()
                if stripped:
                    # Calcola indentazione relativa
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent < 4:
                        result.append("        " + stripped)
                    else:
                        # Mantieni indentazione relativa ma con base 8
                        extra = current_indent - 4
                        result.append("        " + " " * extra + stripped)
                else:
                    result.append("")
            else:
                result.append("    " + line.strip() if line.strip() else "")

        return "\n".join(result)

    # ------------------------------------------------------------------
    # Caricamento dinamico dei tool custom (usato dal coordinator)
    # ------------------------------------------------------------------

    @staticmethod
    def load_custom_tools() -> list:
        """
        Carica i tool custom attivi dal registro.
        Restituisce una lista di dizionari con:
        - definition: OpenAI tool definition (per TOOLS_DEFINITION)
        - instance: istanza del tool (per _execute_tool)
        - name: nome del tool

        Chiamato dal coordinator all'avvio.
        """
        if not REGISTRY_FILE.exists():
            return []

        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        loaded = []
        for tool_entry in registry.get("tools", []):
            if tool_entry["status"] != "active":
                continue

            name = tool_entry["name"]
            file_path = tool_entry["file_path"]
            class_name = tool_entry["class_name"]
            description = tool_entry["description"]
            capabilities = tool_entry.get("capabilities", [])

            try:
                # Import dinamico
                spec = importlib.util.spec_from_file_location(
                    f"app.tools.{name}_tool", file_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                tool_class = getattr(module, f"{class_name}Tool")
                instance = tool_class()

                # Costruisci la definizione OpenAI
                # Parametri: action (enum delle capabilities) + kwargs generici
                definition = {
                    "type": "function",
                    "function": {
                        "name": f"custom_{name}",
                        "description": f"[Tool custom] {description}. Azioni: {', '.join(capabilities)}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": capabilities,
                                },
                                "params": {
                                    "type": "object",
                                    "description": "Parametri per l'azione (dipendono dall'azione scelta)",
                                    "additionalProperties": True
                                }
                            },
                            "required": ["action"]
                        }
                    }
                }

                loaded.append({
                    "definition": definition,
                    "instance": instance,
                    "name": name
                })

                logger.info(f"Tool custom caricato: {name}")

            except Exception as e:
                logger.error(f"Errore caricamento tool custom '{name}': {e}")
                continue

        return loaded


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

create_tool = CreateToolTool()
