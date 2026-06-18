#!/usr/bin/env python3
import argparse
import json
import time
import sys
import httpx
from typing import List, Dict, Any

API_URL = "http://localhost:4001/chat"
SESSION_ID = "test-human"
TIMEOUT = 60.0

SCENARIOS = {
    1: {
        "title": "Mattina — Controllo sito e competitor",
        "messages": [
            {
                "text": "buongiorno nik29, controlla se ildormire.com è online e funziona",
                "keywords": ["online", "funziona", "sito", "ildormire"],
                "expected_tools": ["health_check", "browse_url"]
            },
            {
                "text": "cerca su internet quanto costano i materassi memory foam dei concorrenti tipo Emma, Kipli, InMaterassi",
                "keywords": ["prezz", "euro", "emma", "kipli", "inmaterassi", "cost"],
                "expected_tools": ["brave_search", "web_research"]
            },
            {
                "text": "fai uno screenshot di https://ildormire.com e dimmi come appare la homepage oggi",
                "keywords": ["screenshot", "appare", "homepage", "ildormire"],
                "expected_tools": ["analyze_screenshot", "take_screenshot", "browse_url"]
            }
        ]
    },
    2: {
        "title": "Ricerca di mercato",
        "messages": [
            {
                "text": "usa il web agent per navigare su https://www.emmasleep.it e scopri i loro prezzi dei materassi matrimoniali",
                "keywords": ["prezz", "euro", "emma", "matrimonial"],
                "expected_tools": ["web_agent", "browse_url"]
            },
            {
                "text": "salva in memoria: Emma Sleep materasso matrimoniale costa circa 600-900 euro, competitor principale",
                "keywords": ["salvat", "memoria", "ricord", "emma"],
                "expected_tools": ["save_memory"]
            },
            {
                "text": "cosa ricordi sui competitor e i loro prezzi?",
                "keywords": ["emma", "prezz", "competitor", "ricord"],
                "expected_tools": ["recall_memory"]
            }
        ]
    },
    3: {
        "title": "Gestione tecnica",
        "messages": [
            {
                "text": "esegui un health check completo del sistema",
                "keywords": ["health", "check", "sistem", "ok", "status"],
                "expected_tools": ["health_check"]
            },
            {
                "text": "controlla lo stato dello scheduler, ci sono task programmati?",
                "keywords": ["scheduler", "task", "programmat"],
                "expected_tools": ["scheduler", "get_scheduler_status"]
            },
            {
                "text": "che versione sei? quanti tool hai attivi?",
                "keywords": ["version", "tool", "attiv"],
                "expected_tools": []
            }
        ]
    },
    4: {
        "title": "Navigazione e analisi web",
        "messages": [
            {
                "text": "naviga su https://www.materassi.com e dimmi che categorie di prodotti hanno",
                "keywords": ["categori", "prodott", "materass", "ret", "cuscin"],
                "expected_tools": ["browse_url", "web_agent"]
            },
            {
                "text": "fai uno screenshot di https://www.emmasleep.it e analizza il loro design — colori, layout, call to action",
                "keywords": ["screenshot", "design", "color", "layout", "call to action"],
                "expected_tools": ["analyze_screenshot", "take_screenshot"]
            }
        ]
    },
    5: {
        "title": "Operazioni quotidiane",
        "messages": [
            {
                "text": "cerca su internet le ultime tendenze per materassi 2025-2026",
                "keywords": ["tendenz", "2025", "2026", "ibrid", "sostenibilit"],
                "expected_tools": ["brave_search", "web_research"]
            },
            {
                "text": "salva in memoria: tendenze 2026 — materassi ibridi, sostenibilità, personalizzazione",
                "keywords": ["salvat", "memoria", "ricord", "tendenz"],
                "expected_tools": ["save_memory"]
            },
            {
                "text": "fammi un riassunto di tutto quello che abbiamo fatto oggi in questa sessione",
                "keywords": ["riassunt", "session", "fatto", "ogg"],
                "expected_tools": []
            }
        ]
    },
    6: {
        "title": "Test intelligenza e ragionamento",
        "messages": [
            {
                "text": "se un cliente mi chiede qual è la differenza tra memory foam e lattice, cosa gli dico?",
                "keywords": ["differenz", "memory", "lattice", "traspirant", "sostegn"],
                "expected_tools": []
            },
            {
                "text": "scrivi un breve testo promozionale per un materasso Made in Italy in memory foam, massimo 3 righe",
                "keywords": ["made in italy", "memory", "promozional", "scopr"],
                "expected_tools": []
            }
        ]
    }
}

def print_header():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  NIK29 — TEST CONVERSAZIONE UMANA                          ║")
    print("╠══════════════════════════════════════════════════════════════╣")

def print_footer(total_success: int, total_messages: int, elapsed_time: float, tools_used: set, relevance_score: int):
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  RISULTATO FINALE                                           ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    
    success_str = f"║  {total_success}/{total_messages} conversazioni riuscite"
    print(f"{success_str}{' '*(61 - len(success_str))}║")
    
    mins, secs = divmod(int(elapsed_time), 60)
    time_str = f"║  Tempo totale: {mins}m {secs}s"
    print(f"{time_str}{' '*(61 - len(time_str))}║")
    
    tools_list = ", ".join(tools_used) if tools_used else "Nessuno"
    if len(tools_list) > 42:
        tools_list = tools_list[:39] + "..."
    tools_str = f"║  Tool usati: {tools_list}"
    print(f"{tools_str}{' '*(61 - len(tools_str))}║")
    
    rel_str = f"║  Nik29 ha risposto in modo pertinente: {relevance_score}/{total_messages}"
    print(f"{rel_str}{' '*(61 - len(rel_str))}║")
    
    print("╚══════════════════════════════════════════════════════════════╝")

def check_relevance(response: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    response_lower = response.lower()
    return any(kw.lower() in response_lower for kw in keywords)

def run_test(scenario_id: int = None, verbose: bool = False):
    print_header()
    
    total_messages = 0
    total_success = 0
    relevance_score = 0
    all_tools_used = set()
    start_time = time.time()
    
    scenarios_to_run = [scenario_id] if scenario_id else SCENARIOS.keys()
    
    with httpx.Client(timeout=TIMEOUT) as client:
        for s_id in scenarios_to_run:
            if s_id not in SCENARIOS:
                print(f"Scenario {s_id} non trovato.")
                continue
                
            scenario = SCENARIOS[s_id]
            print(f"\n━━━ Scenario {s_id}: {scenario['title']} ━━━\n")
            
            for msg_data in scenario["messages"]:
                total_messages += 1
                text = msg_data["text"]
                expected_tools = msg_data.get("expected_tools", [])
                keywords = msg_data.get("keywords", [])
                
                print(f"👤 Nicola: \"{text}\"")
                
                payload = {
                    "message": text,
                    "session_id": SESSION_ID
                }
                
                msg_start_time = time.time()
                full_response = ""
                tools_called = []
                has_error = False
                
                try:
                    with client.stream("POST", API_URL, json=payload) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    continue
                                try:
                                    data_json = json.loads(data_str)
                                    msg_type = data_json.get("type")
                                    content = data_json.get("content", "")
                                    
                                    if msg_type == "response":
                                        full_response += content
                                    elif msg_type == "tool_call":
                                        try:
                                            if isinstance(content, str):
                                                tool_data = json.loads(content)
                                            else:
                                                tool_data = content
                                            tool_name = tool_data.get("name", "unknown_tool")
                                            tools_called.append(tool_name)
                                            all_tools_used.add(tool_name)
                                        except:
                                            tools_called.append(str(content))
                                except json.JSONDecodeError:
                                    pass
                except Exception as e:
                    full_response = f"Errore di connessione: {str(e)}"
                    has_error = True
                
                msg_elapsed = time.time() - msg_start_time
                
                is_empty = len(full_response.strip()) == 0
                if "errore" in full_response.lower():
                    has_error = True
                
                is_relevant = check_relevance(full_response, keywords) if not is_empty and not has_error else False
                if is_relevant:
                    relevance_score += 1
                
                passed = not is_empty and not has_error
                if passed:
                    total_success += 1
                
                status_icon = "✅ PASS" if passed else "❌ FAIL"
                
                resp_snippet = full_response.replace("\n", " ").strip()
                if len(resp_snippet) > 60:
                    resp_snippet = resp_snippet[:57] + "..."
                if not resp_snippet:
                    resp_snippet = "(nessuna risposta)"
                
                print(f"🤖 Nik29: \"{resp_snippet}\"")
                
                tools_str = ", ".join(tools_called) if tools_called else "nessun tool"
                print(f"   ⏱️ {msg_elapsed:.1f}s | 🔧 {tools_str} | {status_icon}")
                
                if verbose:
                    print(f"   [Dettagli] Risposta completa:\n   {full_response}")
                    print(f"   [Dettagli] Rilevanza: {'Sì' if is_relevant else 'No'}")
                    if expected_tools:
                        expected_str = ", ".join(expected_tools)
                        print(f"   [Dettagli] Tool attesi (almeno uno): {expected_str}")
                print()

    total_elapsed = time.time() - start_time
    print_footer(total_success, total_messages, total_elapsed, all_tools_used, relevance_score)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simula conversazione umana con Nik29")
    parser.add_argument("--scenario", type=int, help="Esegui solo uno scenario specifico (1-6)", choices=range(1, 7))
    parser.add_argument("--verbose", action="store_true", help="Mostra le risposte complete e i dettagli")
    args = parser.parse_args()
    
    run_test(scenario_id=args.scenario, verbose=args.verbose)
