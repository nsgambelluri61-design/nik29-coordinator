"""
custom_tools_loader.py
======================
Bridge tra i tool generati dal servizio self_evolution (porta 4005)
e il sistema di dispatch del nik29-coordinator.

I tool self_evolution sono funzioni async standalone:
    async def tool_name(param1: str, param2: int = 5) -> dict:
        ...

Questo modulo:
1. Legge il registry (/app/app/tools/custom/registry.json)
2. Importa dinamicamente ogni tool attivo
3. Genera le OpenAI function definitions (schema derivato da inspect)
4. Espone handlers callable direttamente: handlers[name](**args)

Uso nel coordinator:
    from app.custom_tools_loader import evo_loader
    # All'avvio:
    evo_loader.load()
    TOOLS_DEFINITION.extend(evo_loader.definitions)
    # Nel dispatch:
    if name in evo_loader.handlers:
        result = await evo_loader.handlers[name](**args)
    # Dopo creazione nuovo tool:
    evo_loader.reload()
"""

import json
import inspect
import logging
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, get_type_hints

logger = logging.getLogger("custom_tools_loader")

# === CONFIGURAZIONE ===

REGISTRY_PATH = Path("/app/app/tools/custom/registry.json")
CUSTOM_TOOLS_DIR = Path("/app/app/tools/custom")


# === MAPPING TIPI PYTHON → JSON SCHEMA ===

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "string",
}


def _python_type_to_json_schema(annotation) -> str:
    """Converte un'annotazione Python nel tipo JSON Schema corrispondente."""
    if annotation is inspect.Parameter.empty:
        return "string"
    # Gestisci Optional[X] e Union
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        # typing.Optional[X] = Union[X, None]
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _TYPE_MAP.get(non_none[0], "string")
        return "string"
    return _TYPE_MAP.get(annotation, "string")


def _build_parameters_schema(func: Callable) -> dict:
    """
    Costruisce lo schema JSON dei parametri a partire dalla signature della funzione.
    Esclude parametri con default (opzionali) dal 'required'.
    """
    sig = inspect.signature(func)
    properties = {}
    required = []

    # Tenta di ottenere type hints (più affidabili delle annotations nella sig)
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    for param_name, param in sig.parameters.items():
        # Ignora 'return' e parametri speciali
        if param_name in ("self", "cls"):
            continue

        annotation = hints.get(param_name, param.annotation)
        json_type = _python_type_to_json_schema(annotation)

        prop: Dict[str, Any] = {"type": json_type}

        # Aggiungi descrizione dal docstring se possibile (best effort)
        prop["description"] = f"Parametro '{param_name}'"

        # Default value
        if param.default is not inspect.Parameter.empty:
            if param.default is not None:
                prop["default"] = param.default
        else:
            # Nessun default → required
            required.append(param_name)

        properties[param_name] = prop

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _build_tool_definition(name: str, description: str, func: Callable) -> dict:
    """Costruisce la definizione OpenAI function-calling per un tool self_evolution."""
    parameters_schema = _build_parameters_schema(func)

    return {
        "type": "function",
        "function": {
            "name": f"custom_{name}",
            "description": f"[Tool self_evolution] {description}",
            "parameters": parameters_schema,
        },
    }


class SelfEvolutionToolsLoader:
    """
    Loader singleton per i tool generati da self_evolution.
    Mantiene definitions e handlers sincronizzati col registry.
    """

    def __init__(self):
        self.definitions: List[dict] = []
        self.handlers: Dict[str, Callable] = {}
        self._loaded_names: List[str] = []

    def load(self) -> None:
        """Carica (o ricarica) tutti i tool attivi dal registry self_evolution."""
        self.definitions.clear()
        self.handlers.clear()
        self._loaded_names.clear()

        registry = self._read_registry()
        if not registry:
            logger.info("[evo_loader] Nessun tool self_evolution trovato nel registry")
            return

        for entry in registry:
            if not entry.get("active", False):
                continue

            name = entry.get("name", "")
            if not name:
                continue

            try:
                func = self._import_tool(name, entry)
                if func is None:
                    continue

                description = entry.get("description", f"Tool custom: {name}")
                definition = _build_tool_definition(name, description, func)

                self.definitions.append(definition)
                self.handlers[name] = func
                self._loaded_names.append(name)
                logger.info(f"[evo_loader] ✓ Tool caricato: {name}")

            except Exception as e:
                logger.error(f"[evo_loader] ✗ Errore caricamento '{name}': {e}")
                continue

        logger.info(
            f"[evo_loader] Caricati {len(self._loaded_names)} tool self_evolution: "
            f"{', '.join(self._loaded_names) if self._loaded_names else '(nessuno)'}"
        )

    def reload(self) -> None:
        """
        Ricarica i tool self_evolution.
        Invalida i moduli dalla cache sys.modules per forzare il reimport.
        """
        # Rimuovi moduli cached per forzare reimport
        for name in self._loaded_names:
            module_key = f"custom_tool_{name}"
            if module_key in sys.modules:
                del sys.modules[module_key]

        self.load()

    def get_tool_names(self) -> List[str]:
        """Ritorna i nomi dei tool attualmente caricati."""
        return list(self._loaded_names)

    def get_info(self) -> str:
        """Ritorna una stringa descrittiva per il system prompt."""
        if not self._loaded_names:
            return ""
        lines = []
        for name in self._loaded_names:
            func = self.handlers.get(name)
            desc = ""
            if func and func.__doc__:
                desc = func.__doc__.strip().split("\n")[0]
            lines.append(f"- **custom_{name}**: {desc}")
        return "\n".join(lines)

    # === METODI INTERNI ===

    def _read_registry(self) -> list:
        """Legge il registry JSON. Ritorna lista vuota se non esiste o è corrotto."""
        if not REGISTRY_PATH.exists():
            logger.debug(f"[evo_loader] Registry non trovato: {REGISTRY_PATH}")
            return []

        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                logger.warning("[evo_loader] Registry non è una lista, ignorato")
                return []
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"[evo_loader] Errore lettura registry: {e}")
            return []

    def _import_tool(self, name: str, entry: dict) -> Optional[Callable]:
        """
        Importa dinamicamente un tool e ritorna la funzione async principale.
        Ritorna None se l'import fallisce.
        """
        # Determina il path del file
        file_path = entry.get("file_path", "")
        if file_path:
            tool_path = Path(file_path)
        else:
            tool_path = CUSTOM_TOOLS_DIR / f"{name}.py"

        if not tool_path.exists():
            logger.warning(f"[evo_loader] File non trovato per '{name}': {tool_path}")
            return None

        # Import dinamico con nome univoco per evitare collisioni
        module_name = f"custom_tool_{name}"

        try:
            # Rimuovi dalla cache se presente (per reload)
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, str(tool_path))
            if spec is None or spec.loader is None:
                logger.error(f"[evo_loader] Impossibile creare spec per '{name}'")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        except Exception as e:
            logger.error(f"[evo_loader] Import fallito per '{name}': {e}")
            # Rimuovi modulo parziale dalla cache
            sys.modules.pop(module_name, None)
            return None

        # La funzione principale ha lo stesso nome del tool
        if not hasattr(module, name):
            logger.error(
                f"[evo_loader] Funzione '{name}' non trovata nel modulo {tool_path}"
            )
            return None

        func = getattr(module, name)

        # Verifica che sia callable
        if not callable(func):
            logger.error(f"[evo_loader] '{name}' non è callable")
            return None

        # Verifica che sia async (warning se non lo è, ma wrappa comunque)
        if not inspect.iscoroutinefunction(func):
            logger.warning(
                f"[evo_loader] '{name}' non è async — wrapping in coroutine"
            )
            original_func = func

            async def _async_wrapper(**kwargs):
                return original_func(**kwargs)

            _async_wrapper.__doc__ = original_func.__doc__
            _async_wrapper.__name__ = original_func.__name__
            # Preserva la signature per lo schema
            _async_wrapper.__wrapped__ = original_func
            return _async_wrapper

        return func


# === SINGLETON ===

evo_loader = SelfEvolutionToolsLoader()


# === FUNZIONI DI CONVENIENZA ===

def load() -> None:
    """Carica i tool self_evolution. Chiamare all'avvio del coordinator."""
    evo_loader.load()


def reload() -> None:
    """Ricarica i tool self_evolution. Chiamare dopo creazione di un nuovo tool."""
    evo_loader.reload()


def get_definitions() -> List[dict]:
    """Ritorna le definizioni OpenAI dei tool caricati."""
    return evo_loader.definitions


def get_handlers() -> Dict[str, Callable]:
    """Ritorna il dict dei handler: {name: async_function}."""
    return evo_loader.handlers
