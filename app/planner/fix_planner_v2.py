#!/usr/bin/env python3
"""
fix_planner_v2.py — Fix per il planner autonomo di nik29-coordinator.

Risolve 2 problemi:
1. Classificatore troppo restrittivo: "Analizza X e dimmi Y" viene classificato SIMPLE
2. Summary finale troppo sintetico: dice "ho fatto" senza mostrare il contenuto

Uso: docker exec nik29-coordinator python3 /app/app/planner/fix_planner_v2.py
"""

import re
import os

PLANNER_PATH = "/app/app/planner/planner.py"
EXECUTOR_PATH = "/app/app/planner/executor.py"


def fix_planner():
    """Fix 1: Amplia i pattern del classificatore."""
    with open(PLANNER_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Fix 1a: Aggiungi "dimmi/mostrami/elencami/spiegami" ai research_action patterns
    # Il pattern attuale cerca: (analizza|confronta)...(e|poi|quindi)...(report|riassunto|documento|proposta)
    # Aggiungiamo un nuovo pattern: (analizza|confronta|controlla)...(e|poi)...(dimmi|mostrami|elencami|spiegami)
    old_research_patterns = """_RESEARCH_ACTION_PATTERNS = [
    re.compile(r"\\b(cerca|trova|ricerca).*\\b(e|poi|quindi)\\b.*(prepara|crea|scrivi|fai|genera)", re.IGNORECASE),
    re.compile(r"\\b(analizza|confronta).*\\b(e|poi|quindi)\\b.*(report|riassunto|documento|proposta)", re.IGNORECASE),
    re.compile(r"\\b(approfondita|completa|dettagliata)\\b.*\\b(report|analisi|documento|piano)\\b", re.IGNORECASE),
]"""

    new_research_patterns = """_RESEARCH_ACTION_PATTERNS = [
    re.compile(r"\\b(cerca|trova|ricerca).*\\b(e|poi|quindi)\\b.*(prepara|crea|scrivi|fai|genera|dimmi|mostrami)", re.IGNORECASE),
    re.compile(r"\\b(analizza|confronta|controlla|verifica).*\\b(e|poi|quindi)\\b.*(report|riassunto|documento|proposta|dimmi|mostrami|elencami|spiegami|cosa)", re.IGNORECASE),
    re.compile(r"\\b(approfondita|completa|dettagliata)\\b.*\\b(report|analisi|documento|piano)\\b", re.IGNORECASE),
    # Pattern: "analizza X e dimmi/mostrami Y"
    re.compile(r"\\b(analizza|esamina|studia|ispeziona)\\b.*\\b(e|poi)\\b.*\\b(dimmi|mostrami|elencami|spiegami|suggeriscimi)\\b", re.IGNORECASE),
    # Pattern: "cosa migliorare/cambiare/fare" (implica analisi + raccomandazione)
    re.compile(r"\\b(analizza|controlla|verifica)\\b.*\\b(cosa|come)\\b.*\\b(migliorare|cambiare|fare|ottimizzare|correggere)\\b", re.IGNORECASE),
]"""

    if old_research_patterns in content:
        content = content.replace(old_research_patterns, new_research_patterns)
        print("✅ Fix 1: Pattern classificatore ampliati")
    else:
        print("⚠️  Fix 1: Pattern non trovati (già fixati o struttura diversa)")
        # Fallback: prova a inserire i nuovi pattern
        if "_RESEARCH_ACTION_PATTERNS" in content and "cosa migliorare" not in content:
            # Aggiungi i nuovi pattern dopo l'ultimo esistente
            content = content.replace(
                'r"\\b(approfondita|completa|dettagliata)\\b.*\\b(report|analisi|documento|piano)\\b", re.IGNORECASE),\n]',
                'r"\\b(approfondita|completa|dettagliata)\\b.*\\b(report|analisi|documento|piano)\\b", re.IGNORECASE),\n'
                '    # Pattern: "analizza X e dimmi/mostrami Y"\n'
                '    re.compile(r"\\b(analizza|esamina|studia|ispeziona)\\b.*\\b(e|poi)\\b.*\\b(dimmi|mostrami|elencami|spiegami|suggeriscimi)\\b", re.IGNORECASE),\n'
                '    # Pattern: "cosa migliorare/cambiare/fare"\n'
                '    re.compile(r"\\b(analizza|controlla|verifica)\\b.*\\b(cosa|come)\\b.*\\b(migliorare|cambiare|fare|ottimizzare|correggere)\\b", re.IGNORECASE),\n]'
            )
            print("✅ Fix 1 (fallback): Nuovi pattern aggiunti")

    with open(PLANNER_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def fix_executor():
    """Fix 2: Summary finale mostra il contenuto completo."""
    with open(EXECUTOR_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Fix 2a: Cambia il prompt del summary
    old_prompt = (
        'f"Genera una risposta BREVE e DIRETTA per Nicola che riassuma cosa hai fatto. "\n'
        '            f"Stile: informale, conciso, come un collega. "\n'
        '            f"Se ci sono step falliti, menzionali brevemente."'
    )
    new_prompt = (
        'f"Genera una risposta COMPLETA per Nicola con TUTTO il contenuto raccolto. "\n'
        '            f"NON dire solo \'ho fatto X\' — MOSTRA i risultati: tabelle, elenchi, dati, confronti. "\n'
        '            f"Stile: informale ma dettagliato. Usa markdown (titoli, bullet, tabelle). "\n'
        '            f"Se ci sono step falliti, menzionali brevemente alla fine."'
    )

    if old_prompt in content:
        content = content.replace(old_prompt, new_prompt)
        print("✅ Fix 2a: Prompt summary cambiato (mostra contenuto completo)")
    else:
        # Try simpler match
        simple_old = 'Genera una risposta BREVE e DIRETTA per Nicola che riassuma cosa hai fatto.'
        simple_new = 'Genera una risposta COMPLETA per Nicola con TUTTO il contenuto raccolto. NON dire solo "ho fatto X" — MOSTRA i risultati: tabelle, elenchi, dati, confronti. Stile: informale ma dettagliato. Usa markdown (titoli, bullet, tabelle).'
        if simple_old in content:
            content = content.replace(simple_old, simple_new)
            print("✅ Fix 2a (simple): Prompt summary cambiato")
        else:
            print("⚠️  Fix 2a: Prompt summary non trovato")

    # Fix 2b: Alza max_tokens del summary finale (già fatto via sed, ma assicuriamoci)
    if "max_tokens=800" in content:
        content = content.replace("max_tokens=800", "max_tokens=4000")
        print("✅ Fix 2b: max_tokens summary 800 → 4000")
    elif "max_tokens=4000" in content:
        print("ℹ️  Fix 2b: max_tokens già a 4000")
    else:
        print("⚠️  Fix 2b: max_tokens non trovato")

    # Fix 2c: Aumenta result_summary da 100 a 500 chars (per dare più contesto al summary)
    if "result_summary', '')[:100]" in content:
        content = content.replace("result_summary', '')[:100]", "result_summary', '')[:500]")
        print("✅ Fix 2c: result_summary troncamento 100 → 500 chars")

    # Fix 2d: Usa gpt-4.1 invece di gpt-4.1-mini per il summary (più capace)
    if 'model="gpt-4.1-mini",  # Mini basta per il summary' in content:
        content = content.replace(
            'model="gpt-4.1-mini",  # Mini basta per il summary',
            'model="gpt-4.1",  # Full model per summary dettagliato'
        )
        print("✅ Fix 2d: Modello summary gpt-4.1-mini → gpt-4.1")

    with open(EXECUTOR_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def verify():
    """Verifica che i fix siano applicati correttamente."""
    print("\n🔍 Verifica post-fix:")

    # Test classificatore
    import importlib.util
    spec = importlib.util.spec_from_file_location("planner", PLANNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    test_cases = [
        ("Analizza il sito ildormire.com e dimmi cosa migliorare per la SEO", "COMPLEX"),
        ("Cerca i 5 migliori negozi online, confronta prezzi e preparami una tabella", "COMPLEX"),
        ("scontorna questa foto", "SIMPLE"),
        ("ciao", "SIMPLE"),
    ]

    all_ok = True
    for msg, expected in test_cases:
        result = mod.classify_message(msg)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_ok = False
        print(f"  {status} '{msg[:60]}...' → {result} (atteso: {expected})")

    # Test executor prompt
    with open(EXECUTOR_PATH, "r") as f:
        ex_content = f.read()

    checks = [
        ("MOSTRA i risultati" in ex_content, "Prompt mostra contenuto"),
        ("max_tokens=4000" in ex_content, "max_tokens=4000"),
        ('model="gpt-4.1"' in ex_content, "Modello gpt-4.1"),
    ]
    for ok, desc in checks:
        status = "✅" if ok else "❌"
        if not ok:
            all_ok = False
        print(f"  {status} {desc}")

    if all_ok:
        print("\n✅ Tutti i fix verificati con successo!")
    else:
        print("\n⚠️  Alcuni fix non sono stati applicati correttamente")


if __name__ == "__main__":
    print("🔧 Fix Planner v2 — Classificatore + Summary")
    print("=" * 50)
    fix_planner()
    fix_executor()
    verify()
