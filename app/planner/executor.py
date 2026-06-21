"""
executor.py — Esecutore step-by-step di piani per nik29-coordinator.

Prende un piano generato dal TaskPlanner e lo esegue passo per passo,
riutilizzando l'infrastruttura tool esistente del coordinator.

Tra uno step e l'altro, inietta meta-istruzioni nei messaggi per guidare
GPT nell'esecuzione dello step corrente. Yield eventi compatibili con
process_message: "progress", "status", "response".

Limiti di sicurezza:
- Max 30 iterazioni tool totali (tutti gli step combinati)
- Max 3 retry per step fallito (poi skip + nota nel summary)
"""

import json
import asyncio
import logging
from typing import AsyncGenerator

from openai import AsyncOpenAI

logger = logging.getLogger("planner.executor")

# Limiti di sicurezza
MAX_TOTAL_ITERATIONS = 30
MAX_STEP_RETRIES = 3


class PlanExecutor:
    """
    Esegue un piano step-by-step riutilizzando l'infrastruttura del coordinator.

    Parametri:
        client: AsyncOpenAI client (condiviso col coordinator)
        execute_tool_fn: riferimento a coordinator._execute_tool
        tools_definition: lista TOOLS_DEFINITION del coordinator
        build_system_prompt_fn: funzione per costruire il system prompt
        route_model_fn: funzione route_model per scegliere il modello
        status_queue: asyncio.Queue per status updates
        progress_message_fn: funzione _progress_message del coordinator
        safe_truncate_fn: funzione _safe_truncate_messages del coordinator
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        execute_tool_fn,
        tools_definition: list,
        build_system_prompt_fn,
        route_model_fn,
        status_queue: asyncio.Queue,
        progress_message_fn,
        safe_truncate_fn,
    ):
        self.client = client
        self._execute_tool = execute_tool_fn
        self._tools_definition = tools_definition
        self._build_system_prompt = build_system_prompt_fn
        self._route_model = route_model_fn
        self._status_queue = status_queue
        self._progress_message = progress_message_fn
        self._safe_truncate = safe_truncate_fn

    async def execute_plan(
        self,
        plan: dict,
        messages: list,
        system_msg: dict,
        user_message: str,
        conversation_id: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Esegue il piano step-by-step.

        Yield eventi:
            {"type": "progress", "content": "📋 Step N/M: ..."}
            {"type": "status", "content": "..."}
            {"type": "response", "content": "risposta finale con summary"}

        Args:
            plan: dict con "task", "steps", "success_criteria"
            messages: lista messaggi conversazione (mutabile, viene estesa)
            system_msg: messaggio system prompt
            user_message: messaggio originale dell'utente
            conversation_id: ID conversazione
        """
        steps = plan.get("steps", [])
        total_steps = len(steps)
        total_iterations = 0
        completed_steps = []
        failed_steps = []
        error_log = []  # Per auto-reflect

        # Notifica inizio piano
        yield {
            "type": "progress",
            "content": f"📋 Piano generato: {total_steps} step da eseguire."
        }

        for step_idx, step in enumerate(steps):
            step_n = step.get("n", step_idx + 1)
            step_action = step.get("action", "azione non specificata")
            step_tool_hint = step.get("tool_hint")

            # Notifica progresso step
            yield {
                "type": "progress",
                "content": f"📋 Step {step_n}/{total_steps}: {step_action}"
            }

            # Inietta meta-istruzione per questo step
            meta_instruction = self._build_step_instruction(
                step=step,
                step_n=step_n,
                total_steps=total_steps,
                completed_steps=completed_steps,
                plan=plan,
            )
            messages.append({"role": "user", "content": meta_instruction})

            # Esegui lo step (loop tool interno)
            step_success = False
            step_retries = 0

            while step_retries < MAX_STEP_RETRIES:
                step_completed = False

                # Mini-loop tool per questo step (max iterazioni rimanenti)
                max_step_iters = min(10, MAX_TOTAL_ITERATIONS - total_iterations)
                if max_step_iters <= 0:
                    logger.warning("Limite iterazioni totali raggiunto")
                    failed_steps.append({
                        "n": step_n,
                        "action": step_action,
                        "reason": "Limite iterazioni totali raggiunto"
                    })
                    break

                for _iter in range(max_step_iters):
                    total_iterations += 1
                    api_messages = [system_msg] + self._safe_truncate(messages, max_messages=20)

                    try:
                        response = await self.client.chat.completions.create(
                            model=self._route_model(
                                user_message=user_message,
                                message_history=messages,
                            ),
                            messages=api_messages,
                            tools=self._tools_definition,
                            tool_choice="auto",
                            temperature=0.7,
                            max_tokens=4000,
                        )
                    except Exception as e:
                        logger.error(f"Errore LLM nello step {step_n}: {e}")
                        step_retries += 1
                        error_log.append({
                            "step": step_n,
                            "error": str(e),
                            "iteration": total_iterations
                        })
                        break

                    choice = response.choices[0]

                    if choice.message.tool_calls:
                        # Esegui tool calls
                        assistant_msg = {
                            "role": "assistant",
                            "content": choice.message.content or "",
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in choice.message.tool_calls
                            ],
                        }
                        messages.append(assistant_msg)

                        for tool_call in choice.message.tool_calls:
                            func_name = tool_call.function.name
                            try:
                                args = json.loads(tool_call.function.arguments)
                            except json.JSONDecodeError:
                                args = {}

                            # Yield progresso tool
                            yield {
                                "type": "progress",
                                "content": self._progress_message(func_name, args),
                            }

                            # Esegui tool
                            exec_task = asyncio.create_task(
                                self._execute_tool(func_name, args)
                            )

                            # Yield status updates durante esecuzione
                            while not exec_task.done():
                                try:
                                    status_msg = await asyncio.wait_for(
                                        self._status_queue.get(), timeout=1.0
                                    )
                                    yield {"type": "status", "content": status_msg}
                                except asyncio.TimeoutError:
                                    continue

                            result = exec_task.result()

                            # Svuota status residui
                            while not self._status_queue.empty():
                                try:
                                    status_msg = self._status_queue.get_nowait()
                                    yield {"type": "status", "content": status_msg}
                                except asyncio.QueueEmpty:
                                    break

                            # Aggiungi risultato
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": result,
                            })

                            # Track errori per auto-reflect
                            _error_keywords = [
                                "errore", "fallito", "timeout", "non trovato",
                                "non esiste", "bloccato", "rifiutato", "impossibile",
                                "failed", "error", "denied", "connection refused",
                            ]
                            _result_lower = (result or "").lower()[:500]
                            if any(kw in _result_lower for kw in _error_keywords):
                                error_log.append({
                                    "step": step_n,
                                    "tool": func_name,
                                    "error": result[:200],
                                    "iteration": total_iterations,
                                })

                    else:
                        # GPT ha risposto senza tool call → step completato
                        final_content = choice.message.content or ""
                        messages.append({"role": "assistant", "content": final_content})
                        step_completed = True
                        step_success = True
                        completed_steps.append({
                            "n": step_n,
                            "action": step_action,
                            "result_summary": final_content[:200],
                        })
                        break

                if step_completed:
                    break

                # Se non completato, retry
                if not step_success and step_retries < MAX_STEP_RETRIES:
                    step_retries += 1
                    logger.warning(
                        f"Step {step_n} retry {step_retries}/{MAX_STEP_RETRIES}"
                    )
                    # Aggiungi messaggio di retry
                    messages.append({
                        "role": "user",
                        "content": f"[SISTEMA] Lo step {step_n} non è stato completato. "
                        f"Riprova (tentativo {step_retries + 1}/{MAX_STEP_RETRIES}). "
                        f"Azione richiesta: {step_action}",
                    })

            # Se step fallito dopo tutti i retry
            if not step_success and step_n not in [s["n"] for s in failed_steps]:
                failed_steps.append({
                    "n": step_n,
                    "action": step_action,
                    "reason": f"Fallito dopo {MAX_STEP_RETRIES} tentativi",
                })
                # Nota nel flusso messaggi
                messages.append({
                    "role": "assistant",
                    "content": f"⚠️ Step {step_n} saltato: non completato dopo {MAX_STEP_RETRIES} tentativi.",
                })

            # Check limite totale
            if total_iterations >= MAX_TOTAL_ITERATIONS:
                logger.warning("Limite iterazioni totali raggiunto — interruzione piano")
                remaining = [
                    s for s in steps[step_idx + 1:]
                ]
                for rs in remaining:
                    failed_steps.append({
                        "n": rs.get("n", "?"),
                        "action": rs.get("action", "?"),
                        "reason": "Non eseguito (limite iterazioni)",
                    })
                break

        # === Genera risposta finale con summary ===
        summary = self._build_summary(plan, completed_steps, failed_steps, total_iterations)

        # Chiedi a GPT di generare una risposta finale naturale
        summary_response = await self._generate_final_response(
            plan=plan,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            messages=messages,
            system_msg=system_msg,
            user_message=user_message,
        )

        yield {"type": "response", "content": summary_response}

        # Restituisci anche error_log per auto-reflect (via attributo)
        self._last_error_log = error_log
        self._last_iterations = total_iterations

    def _build_step_instruction(
        self, step: dict, step_n: int, total_steps: int,
        completed_steps: list, plan: dict
    ) -> str:
        """Costruisce la meta-istruzione per guidare GPT nell'esecuzione di uno step."""
        parts = []
        parts.append(f"[PIANO AUTONOMO — Step {step_n}/{total_steps}]")
        parts.append(f"Task originale: {plan.get('task', '')}")
        parts.append(f"")
        parts.append(f"AZIONE DA ESEGUIRE ORA: {step.get('action', '')}")

        if step.get("tool_hint"):
            parts.append(f"Tool suggerito: {step['tool_hint']}")

        if completed_steps:
            parts.append(f"")
            parts.append("Step già completati:")
            for cs in completed_steps[-3:]:  # Ultimi 3 per contesto
                parts.append(f"  ✅ Step {cs['n']}: {cs['action']}")

        parts.append(f"")
        parts.append("Esegui SOLO questo step. Quando hai finito, rispondi con un breve riepilogo di cosa hai fatto.")

        return "\n".join(parts)

    def _build_summary(
        self, plan: dict, completed_steps: list,
        failed_steps: list, total_iterations: int
    ) -> str:
        """Costruisce un summary strutturato dell'esecuzione."""
        lines = []
        lines.append(f"## Riepilogo Esecuzione Piano")
        lines.append(f"**Task:** {plan.get('task', 'N/A')}")
        lines.append(f"**Iterazioni totali:** {total_iterations}")
        lines.append(f"")

        if completed_steps:
            lines.append(f"### ✅ Completati ({len(completed_steps)} step)")
            for cs in completed_steps:
                lines.append(f"- Step {cs['n']}: {cs['action']}")

        if failed_steps:
            lines.append(f"")
            lines.append(f"### ⚠️ Non completati ({len(failed_steps)} step)")
            for fs in failed_steps:
                lines.append(f"- Step {fs['n']}: {fs['action']} — {fs.get('reason', 'errore')}")

        lines.append(f"")
        lines.append(f"**Criterio di successo:** {plan.get('success_criteria', 'N/A')}")

        return "\n".join(lines)

    async def _generate_final_response(
        self, plan: dict, completed_steps: list, failed_steps: list,
        messages: list, system_msg: dict, user_message: str
    ) -> str:
        """
        Genera una risposta finale naturale che riassume cosa è stato fatto.
        Usa GPT per produrre un messaggio leggibile per l'utente.
        """
        # Costruisci un prompt di sintesi
        summary_prompt = (
            f"[PIANO COMPLETATO]\n"
            f"Task originale: {plan.get('task', user_message)}\n\n"
            f"Step completati: {len(completed_steps)}/{len(completed_steps) + len(failed_steps)}\n"
        )

        if completed_steps:
            summary_prompt += "\nCompletati:\n"
            for cs in completed_steps:
                summary_prompt += f"  ✅ {cs['action']}: {cs.get('result_summary', '')[:500]}\n"

        if failed_steps:
            summary_prompt += "\nNon completati:\n"
            for fs in failed_steps:
                summary_prompt += f"  ⚠️ {fs['action']}: {fs.get('reason', '')}\n"

        summary_prompt += (
            f"\nCriterio di successo: {plan.get('success_criteria', 'N/A')}\n\n"
            f"Genera una risposta COMPLETA per Nicola con TUTTO il contenuto raccolto. "
            f"NON dire solo 'ho fatto X' — MOSTRA i risultati: tabelle, elenchi, dati, confronti. "
            f"Stile: informale ma dettagliato. Usa markdown (titoli, bullet, tabelle). "
            f"Se ci sono step falliti, menzionali brevemente alla fine."
        )

        # Aggiungi ai messaggi e chiedi risposta finale
        final_messages = [system_msg] + self._safe_truncate(messages, max_messages=10)
        final_messages.append({"role": "user", "content": summary_prompt})

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4.1",  # Full model per summary dettagliato
                messages=final_messages,
                temperature=0.7,
                max_tokens=4000,
            )
            return response.choices[0].message.content or self._build_summary(
                plan, completed_steps, failed_steps, 0
            )
        except Exception as e:
            logger.error(f"Errore generazione risposta finale: {e}")
            # Fallback: summary strutturato
            return self._build_summary(plan, completed_steps, failed_steps, 0)

    @property
    def last_error_log(self) -> list:
        """Restituisce l'error log dell'ultima esecuzione (per auto-reflect)."""
        return getattr(self, "_last_error_log", [])

    @property
    def last_iterations(self) -> int:
        """Restituisce il numero di iterazioni dell'ultima esecuzione."""
        return getattr(self, "_last_iterations", 0)
