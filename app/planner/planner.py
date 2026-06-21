"""
planner.py — Classificatore e generatore di piani per nik29-coordinator.

Classifica i messaggi utente in SIMPLE o COMPLEX usando euristiche veloci
(nessuna chiamata LLM per la classificazione). Per i task COMPLEX, genera
un piano strutturato JSON tramite una singola chiamata a GPT-4.1.

Integrazione: il coordinator chiama classify_message() prima del loop.
Se il risultato è None → flusso standard (SIMPLE).
Se il risultato è un dict plan → delega al PlanExecutor.
"""

import re
import json
import logging
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger("planner")

# ============================================================
# CLASSIFICATORE EURISTICO (zero LLM calls)
# ============================================================

# Verbi d'azione italiani che indicano task operativi
_ACTION_VERBS = [
    r"\b(fai|crea|genera|scrivi|implementa|costruisci|prepara|configura|installa)\b",
    r"\b(cerca|trova|analizza|controlla|verifica|confronta|ricerca)\b",
    r"\b(modifica|aggiorna|cambia|correggi|sistema|ottimizza|migliora)\b",
    r"\b(pubblica|deploya|carica|invia|manda|spedisci)\b",
    r"\b(elimina|rimuovi|cancella|disattiva|ferma|stoppa)\b",
    r"\b(testa|prova|lancia|esegui|avvia|attiva)\b",
]
_ACTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _ACTION_VERBS]

# Pattern che indicano task multi-step
_MULTI_STEP_PATTERNS = [
    # Congiunzioni sequenziali
    re.compile(r"\b(e\s+poi|poi|dopo|quindi|infine|successivamente|per\s+prima\s+cosa)\b", re.IGNORECASE),
    # Elenchi numerati o con trattini
    re.compile(r"(?:^|\n)\s*[\-\*\d]+[\.\)]\s+", re.MULTILINE),
    # Richieste esplicite di piano/sequenza
    re.compile(r"\b(step[\s-]by[\s-]step|passo[\s-]passo|in\s+ordine|uno\s+per\s+uno)\b", re.IGNORECASE),
    # Virgole che separano azioni ("crea X, aggiorna Y, verifica Z")
    re.compile(r"\b(fai|crea|cerca|trova|controlla|aggiorna|genera|implementa|analizza|modifica|correggi)\b[^,]{3,50},\s*\b(fai|crea|cerca|trova|controlla|aggiorna|genera|implementa|analizza|modifica|correggi)\b", re.IGNORECASE),
]

# Pattern che indicano ricerca + azione combinata
_RESEARCH_ACTION_PATTERNS = [
    re.compile(r"\b(cerca|trova|ricerca).*\b(e|poi|quindi)\b.*(prepara|crea|scrivi|fai|genera|dimmi|mostrami)", re.IGNORECASE),
    re.compile(r"\b(analizza|confronta|controlla|verifica).*\b(e|poi|quindi)\b.*(report|riassunto|documento|proposta|dimmi|mostrami|elencami|spiegami|cosa)", re.IGNORECASE),
    re.compile(r"\b(approfondita|completa|dettagliata)\b.*\b(report|analisi|documento|piano)\b", re.IGNORECASE),
    # Pattern: "analizza X e dimmi/mostrami Y"
    re.compile(r"\b(analizza|esamina|studia|ispeziona)\b.*\b(e|poi)\b.*\b(dimmi|mostrami|elencami|spiegami|suggeriscimi)\b", re.IGNORECASE),
    # Pattern: "cosa migliorare/cambiare/fare" (implica analisi + raccomandazione)
    re.compile(r"\b(analizza|controlla|verifica)\b.*\b(cosa|come)\b.*\b(migliorare|cambiare|fare|ottimizzare|correggere)\b", re.IGNORECASE),
]

# Pattern che indicano creazione di qualcosa complesso
_COMPLEX_CREATION_PATTERNS = [
    re.compile(r"\b(crea|genera|costruisci|implementa)\s+(un|una|il|la)\s+\w+\s+(che|con|dove|per)\b", re.IGNORECASE),
    re.compile(r"\b(sistema|modulo|applicazione|pipeline|workflow|agente|bot)\b", re.IGNORECASE),
    # Creazione con monitoraggio/automazione
    re.compile(r"\b(monitora|automatizza|schedula|notifica|avvisa)\b", re.IGNORECASE),
]

# Pattern espliciti che forzano SIMPLE (saluti, domande brevi, comandi singoli)
_SIMPLE_FORCE_PATTERNS = [
    re.compile(r"^(ciao|hey|buongiorno|buonasera|salve|ok|grazie|perfetto|ottimo|bene)\b", re.IGNORECASE),
    re.compile(r"^(che\s+ore|che\s+giorno|che\s+versione|come\s+stai|chi\s+sei)\b", re.IGNORECASE),
    re.compile(r"^(si|no|va\s+bene|confermo|annulla)\s*[.!?]?\s*$", re.IGNORECASE),
]


def classify_message(message: str) -> str:
    """
    Classifica un messaggio come 'SIMPLE' o 'COMPLEX'.
    Usa solo euristiche — nessuna chiamata LLM.

    Returns:
        'SIMPLE' o 'COMPLEX'
    """
    text = message.strip()

    # Forza SIMPLE per saluti, conferme, domande banali
    for pattern in _SIMPLE_FORCE_PATTERNS:
        if pattern.search(text):
            return "SIMPLE"

    # Conta verbi d'azione presenti
    action_count = sum(1 for p in _ACTION_PATTERNS if p.search(text))

    # Check multi-step esplicito
    has_multi_step = any(p.search(text) for p in _MULTI_STEP_PATTERNS)

    # Check ricerca + azione
    has_research_action = any(p.search(text) for p in _RESEARCH_ACTION_PATTERNS)

    # Check creazione complessa
    has_complex_creation = any(p.search(text) for p in _COMPLEX_CREATION_PATTERNS)

    # === Regole di classificazione ===

    # Regola 1: Multi-step esplicito con almeno 2 azioni
    if has_multi_step and action_count >= 2:
        logger.info(f"COMPLEX: multi-step + {action_count} azioni")
        return "COMPLEX"

    # Regola 2: Ricerca + azione combinata
    if has_research_action:
        logger.info("COMPLEX: ricerca + azione combinata")
        return "COMPLEX"

    # Regola 3: Creazione complessa con almeno 1 azione
    if has_complex_creation and action_count >= 1:
        logger.info("COMPLEX: creazione complessa")
        return "COMPLEX"

    # Regola 4: Messaggio lungo con molte azioni
    if len(text) > 200 and action_count >= 3:
        logger.info(f"COMPLEX: messaggio lungo ({len(text)} chars) + {action_count} azioni")
        return "COMPLEX"

    # Regola 5: 4+ verbi d'azione in qualsiasi messaggio
    if action_count >= 4:
        logger.info(f"COMPLEX: {action_count} azioni rilevate")
        return "COMPLEX"

    # Default: SIMPLE
    return "SIMPLE"


# ============================================================
# GENERATORE DI PIANI (una singola chiamata LLM)
# ============================================================

# Prompt di pianificazione in italiano (matching personalità nik29)
_PLANNING_SYSTEM_PROMPT = """Sei il modulo di pianificazione di nik29. Il tuo compito è analizzare una richiesta complessa dell'utente e scomporla in un piano di esecuzione strutturato.

REGOLE:
- Genera un piano JSON con step chiari, sequenziali e atomici.
- Ogni step deve essere eseguibile con UN tool o una serie breve di tool correlati.
- Sii specifico: non scrivere "cerca informazioni" ma "cerca X usando web_research".
- Il campo tool_hint suggerisce quale tool usare (può essere null se non ovvio).
- Il campo success_criteria descrive come verificare che il task sia completato.
- Massimo 8 step per piano (se servono di più, raggruppa le azioni correlate).
- Minimo 2 step (se ne basta 1, non è un task complesso).

TOOL DISPONIBILI (per tool_hint):
- shell: comandi sistema
- host_shell: comandi sul Mac host
- web_research: ricerca web rapida (1-2 pagine)
- deep_research: ricerca approfondita (10-20 pagine)
- brave_search: risultati rapidi senza leggere pagine
- browse_url: apri un URL specifico
- file_manager: leggi/scrivi/lista file
- delegate_task: delega a sub-agente (immagini, SEO, social)
- save_memory / recall_memory: memoria persistente
- git_auto: operazioni git
- docker_manage: gestione container Docker
- health_check: controllo stato servizi
- browser_navigate / browser_click / browser_fill: automazione browser
- web_agent: navigazione autonoma multi-step
- analyze_screenshot: analisi visiva pagina web
- create_tool_propose/generate: creazione nuovi tool

FORMATO OUTPUT (JSON puro, nient'altro):
{
  "task": "richiesta originale dell'utente",
  "steps": [
    {"n": 1, "action": "descrizione chiara dell'azione", "tool_hint": "nome_tool o null"},
    {"n": 2, "action": "...", "tool_hint": "..."}
  ],
  "success_criteria": "come sapere che il task è completato"
}"""

_PLANNING_USER_TEMPLATE = """Analizza questa richiesta e genera un piano di esecuzione strutturato:

RICHIESTA: {message}

Rispondi SOLO con il JSON del piano, senza altro testo."""


class TaskPlanner:
    """
    Classificatore + generatore di piani per il coordinator.

    Uso:
        planner = TaskPlanner(client)
        plan = await planner.analyze(user_message)
        if plan is None:
            # task semplice, procedi normalmente
        else:
            # task complesso, usa PlanExecutor
    """

    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def analyze(self, message: str) -> Optional[dict]:
        """
        Analizza il messaggio utente.

        Returns:
            None se il task è SIMPLE (il coordinator procede normalmente).
            dict con il piano se il task è COMPLEX.
        """
        classification = classify_message(message)

        if classification == "SIMPLE":
            logger.debug(f"Task classificato SIMPLE: {message[:80]}...")
            return None

        logger.info(f"Task classificato COMPLEX: {message[:80]}...")
        plan = await self._generate_plan(message)
        return plan

    async def _generate_plan(self, message: str) -> Optional[dict]:
        """
        Genera un piano strutturato tramite una singola chiamata a GPT-4.1.
        Temperature 0.3 per output deterministico.

        Returns:
            dict con il piano, o None se la generazione fallisce.
        """
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": _PLANNING_SYSTEM_PROMPT},
                    {"role": "user", "content": _PLANNING_USER_TEMPLATE.format(message=message)},
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content or ""

            # Parse JSON
            plan = json.loads(content)

            # Validazione minima
            if "steps" not in plan or not isinstance(plan["steps"], list):
                logger.error(f"Piano invalido (manca 'steps'): {content[:200]}")
                return None

            if len(plan["steps"]) < 2:
                logger.warning("Piano con meno di 2 step — fallback a SIMPLE")
                return None

            # Assicura che il campo task sia presente
            if "task" not in plan:
                plan["task"] = message

            # Assicura success_criteria
            if "success_criteria" not in plan:
                plan["success_criteria"] = "Task completato con successo"

            logger.info(f"Piano generato: {len(plan['steps'])} step")
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"Errore parsing JSON piano: {e}")
            return None
        except Exception as e:
            logger.error(f"Errore generazione piano: {e}")
            return None
