"""
think_tool.py - Tool cognitivo di pianificazione per nik29-coordinator.

Genera piani step-by-step per task complessi e valuta il prossimo passo
dato lo stato attuale. NON chiama altri tool — restituisce solo testo strutturato.

Azioni:
  - plan: Dato un task, genera un piano step-by-step
  - evaluate: Dato un piano e lo stato attuale, decide il prossimo passo
"""

import json
import os
from datetime import datetime

# Path persistenza
MEMORY_DIR = os.environ.get("MEMORY_DIR", "/data/memory")
PLANS_FILE = os.path.join(MEMORY_DIR, "plans.json")

# --- TOOL DEFINITION (OpenAI function calling) ---
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "think",
        "description": "Tool cognitivo di pianificazione. Genera piani step-by-step per task complessi o valuta il prossimo passo. Non produce output visibile all'utente.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["plan", "evaluate"],
                    "description": "Azione da eseguire: 'plan' per generare un piano, 'evaluate' per decidere il prossimo passo"
                },
                "task": {
                    "type": "string",
                    "description": "Descrizione del task da pianificare (per action=plan)"
                },
                "plan_id": {
                    "type": "string",
                    "description": "ID del piano da valutare (per action=evaluate)"
                },
                "current_state": {
                    "type": "string",
                    "description": "Stato attuale dell'esecuzione (per action=evaluate)"
                },
                "context": {
                    "type": "string",
                    "description": "Contesto aggiuntivo per la pianificazione"
                }
            },
            "required": ["action"]
        }
    }
}


def _load_plans() -> dict:
    """Carica i piani salvati da file JSON."""
    try:
        if os.path.exists(PLANS_FILE):
            with open(PLANS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {"plans": []}


def _save_plans(data: dict):
    """Salva i piani su file JSON."""
    os.makedirs(os.path.dirname(PLANS_FILE), exist_ok=True)
    with open(PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _generate_plan_id() -> str:
    """Genera un ID univoco per il piano."""
    return f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _create_plan(task: str, context: str = "") -> dict:
    """Crea un piano strutturato per il task dato."""
    plan = {
        "id": _generate_plan_id(),
        "task": task,
        "context": context,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "steps": [],
        "current_step": 0
    }

    # Analisi del task per generare steps
    steps = []

    # Step 1: Comprensione
    steps.append({
        "n": 1,
        "action": "ANALIZZA",
        "description": f"Comprendi il task: {task}",
        "status": "pending",
        "dependencies": []
    })

    # Step 2: Verifica prerequisiti
    steps.append({
        "n": 2,
        "action": "VERIFICA_PREREQUISITI",
        "description": "Controlla che tutti i dati e le risorse necessarie siano disponibili",
        "status": "pending",
        "dependencies": [1]
    })

    # Step 3: Esecuzione principale
    steps.append({
        "n": 3,
        "action": "ESEGUI",
        "description": f"Esegui l'azione principale per: {task}",
        "status": "pending",
        "dependencies": [2]
    })

    # Step 4: Verifica risultato
    steps.append({
        "n": 4,
        "action": "VERIFICA_RISULTATO",
        "description": "Verifica che il risultato sia corretto e completo",
        "status": "pending",
        "dependencies": [3]
    })

    # Step 5: Comunicazione
    steps.append({
        "n": 5,
        "action": "COMUNICA",
        "description": "Comunica il risultato all'utente",
        "status": "pending",
        "dependencies": [4]
    })

    plan["steps"] = steps
    return plan


def _evaluate_plan(plan_id: str, current_state: str, plans_data: dict) -> str:
    """Valuta lo stato del piano e suggerisce il prossimo passo."""
    # Cerca il piano
    plan = None
    for p in plans_data.get("plans", []):
        if p["id"] == plan_id:
            plan = p
            break

    if not plan:
        return f"ERRORE: Piano '{plan_id}' non trovato. Piani disponibili: {[p['id'] for p in plans_data.get('plans', [])]}"

    steps = plan.get("steps", [])
    current_step = plan.get("current_step", 0)

    # Trova il prossimo step da eseguire
    next_step = None
    for step in steps:
        if step["status"] == "pending":
            next_step = step
            break

    if not next_step:
        return f"PIANO COMPLETATO: Tutti gli step del piano '{plan_id}' sono stati eseguiti."

    # Valuta lo stato corrente
    evaluation = f"VALUTAZIONE PIANO '{plan_id}':\n"
    evaluation += f"- Task: {plan['task']}\n"
    evaluation += f"- Stato attuale: {current_state}\n"
    evaluation += f"- Progresso: {current_step}/{len(steps)} step completati\n"
    evaluation += f"\nPROSSIMO PASSO:\n"
    evaluation += f"- Step {next_step['n']}: [{next_step['action']}] {next_step['description']}\n"

    # Controlla dipendenze
    deps = next_step.get("dependencies", [])
    if deps:
        deps_status = []
        for dep_n in deps:
            dep_step = next((s for s in steps if s["n"] == dep_n), None)
            if dep_step:
                deps_status.append(f"  Step {dep_n}: {dep_step['status']}")
        evaluation += f"- Dipendenze: \n" + "\n".join(deps_status) + "\n"

    return evaluation


class ThinkTool:
    """Tool cognitivo di pianificazione."""

    def __init__(self):
        self.name = "think"

    async def execute(self, action: str, **kwargs) -> str:
        """Esegue l'azione richiesta."""
        try:
            if action == "plan":
                return await self._plan(**kwargs)
            elif action == "evaluate":
                return await self._evaluate(**kwargs)
            else:
                return f"ERRORE: Azione '{action}' non supportata. Usa 'plan' o 'evaluate'."
        except Exception as e:
            return f"ERRORE think_tool: {str(e)}"

    async def _plan(self, task: str = "", context: str = "", **kwargs) -> str:
        """Genera un piano step-by-step per il task."""
        if not task:
            return "ERRORE: Parametro 'task' richiesto per l'azione 'plan'."

        # Genera il piano
        plan = _create_plan(task, context)

        # Salva
        plans_data = _load_plans()
        plans_data["plans"].append(plan)

        # Mantieni solo gli ultimi 50 piani
        if len(plans_data["plans"]) > 50:
            plans_data["plans"] = plans_data["plans"][-50:]

        _save_plans(plans_data)

        # Formatta output
        output = f"PIANO GENERATO: {plan['id']}\n"
        output += f"Task: {task}\n"
        if context:
            output += f"Contesto: {context}\n"
        output += f"\nSTEPS:\n"
        for step in plan["steps"]:
            output += f"  {step['n']}. [{step['action']}] {step['description']}\n"
        output += f"\nUsa think(action='evaluate', plan_id='{plan['id']}', current_state='...') per valutare il progresso."

        return output

    async def _evaluate(self, plan_id: str = "", current_state: str = "", **kwargs) -> str:
        """Valuta il piano e suggerisce il prossimo passo."""
        if not plan_id:
            # Se non c'è plan_id, usa l'ultimo piano
            plans_data = _load_plans()
            if plans_data["plans"]:
                plan_id = plans_data["plans"][-1]["id"]
            else:
                return "ERRORE: Nessun piano trovato. Crea prima un piano con action='plan'."

        if not current_state:
            current_state = "non specificato"

        plans_data = _load_plans()
        return _evaluate_plan(plan_id, current_state, plans_data)


# --- Helper per uso esterno ---
def get_think_context() -> str:
    """Restituisce un riassunto dei piani attivi per il contesto del coordinator."""
    plans_data = _load_plans()
    active_plans = [p for p in plans_data.get("plans", []) if p.get("status") == "active"]

    if not active_plans:
        return ""

    context = "PIANI ATTIVI:\n"
    for plan in active_plans[-3:]:  # Ultimi 3
        context += f"- {plan['id']}: {plan['task']} (step {plan.get('current_step', 0)}/{len(plan.get('steps', []))})\n"

    return context
