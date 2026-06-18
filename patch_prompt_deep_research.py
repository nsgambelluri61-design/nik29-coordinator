#!/usr/bin/env python3
"""
Patch: aggiunge la regola deep_research al system prompt di nik29-coordinator.
Eseguire dalla root del progetto: python3 patch_prompt_deep_research.py
"""
import os

PROMPT_FILE = "config/system_prompt.txt"

# La regola da aggiungere dopo il mapping obbligatorio
SEARCH_TEXT = '- MAI usare brave_search + browse_url + web_research insieme per la stessa domanda.'
INSERT_AFTER = '''- MAI usare brave_search + browse_url + web_research insieme per la stessa domanda.
- "ricerca approfondita/analizza a fondo/confronta/ricerca completa" -> deep_research (cerca 10-20 pagine in parallelo e sintetizza tutto)
- deep_research = usa quando serve una ricerca COMPLETA su un argomento (competitor, mercato, prodotti, confronti). Legge 10-20 siti in parallelo.
- web_research = usa per domande SEMPLICI (una risposta rapida da 1-2 pagine).
- REGOLA: se Nicola dice "approfondita", "completa", "confronta", "analizza il mercato" -> deep_research SEMPRE.'''

def patch():
    if not os.path.exists(PROMPT_FILE):
        print(f"ERRORE: {PROMPT_FILE} non trovato. Esegui dalla root del progetto.")
        return False
    
    with open(PROMPT_FILE, 'r') as f:
        content = f.read()
    
    if 'deep_research' in content:
        print("deep_research gia' presente nel system prompt. Nessuna modifica.")
        return True
    
    if SEARCH_TEXT not in content:
        print(f"ERRORE: non trovo la riga di riferimento nel prompt.")
        print(f"Cercavo: {SEARCH_TEXT}")
        return False
    
    content = content.replace(SEARCH_TEXT, INSERT_AFTER)
    
    with open(PROMPT_FILE, 'w') as f:
        f.write(content)
    
    print("OK! Regola deep_research aggiunta al system prompt.")
    print("Ora fai: docker compose down && docker compose build && docker compose up -d")
    return True

if __name__ == "__main__":
    patch()
