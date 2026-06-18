#!/usr/bin/env python3
"""
Fix: aggiunge regole di efficienza per le ricerche web nel system prompt.
Evita che GPT-4.1 faccia 8-9 chiamate tool per una singola ricerca.
"""
import os

# Trova il system_prompt.txt
PATHS = [
    "config/system_prompt.txt",
    "./system_prompt.txt",
]

prompt_path = None
for p in PATHS:
    if os.path.exists(p):
        prompt_path = p
        break

if not prompt_path:
    print("ERRORE: system_prompt.txt non trovato!")
    print("Esegui questo script dalla directory nik29-coordinator-v0.6.0")
    exit(1)

with open(prompt_path, 'r') as f:
    content = f.read()

# Testo da trovare e sostituire
OLD_MAPPING = '''MAPPING OBBLIGATORIO:
- "cerca/trova/quanto costa" -> brave_search o web_search
- "controlla il sito/e' online" -> health_check o browse_url  
- "fai screenshot/come appare" -> analyze_screenshot (con url!)
- "naviga su/vai su/apri" -> browser_navigate o web_agent
- "salva/ricorda" -> save_memory
- "cosa ricordi/cosa sai" -> recall_memory
- "esegui/lancia/fai" (comando) -> shell o host_shell
- "controlla lo scheduler" -> shell (cat /data/scheduler/tasks.json)
- "che versione sei" -> shell (cat /app/manifest.json)
- "health check/stato sistema" -> health_check'''

NEW_MAPPING = '''MAPPING OBBLIGATORIO:
- "cerca/trova/quanto costa" -> web_research (UNA sola chiamata, fa tutto lui)
- "controlla il sito/e' online" -> health_check o browse_url  
- "fai screenshot/come appare" -> analyze_screenshot (con url!)
- "naviga su/vai su/apri" -> browser_navigate o web_agent
- "salva/ricorda" -> save_memory
- "cosa ricordi/cosa sai" -> recall_memory
- "esegui/lancia/fai" (comando) -> shell o host_shell
- "controlla lo scheduler" -> shell (cat /data/scheduler/tasks.json)
- "che versione sei" -> shell (cat /app/manifest.json)
- "health check/stato sistema" -> health_check

REGOLE EFFICIENZA RICERCHE WEB:
- Per ricerche semplici: usa web_research UNA VOLTA e rispondi. NON aggiungere brave_search + browse_url separati.
- web_research = fa gia' tutto (cerca + apre pagine + riassume). Basta UNA chiamata.
- brave_search = usa SOLO se vuoi risultati rapidi senza leggere le pagine (es. "che ora e' a Tokyo").
- browse_url = usa SOLO per aprire UN sito specifico che conosci gia' (es. "apri ildormire.com").
- MAI usare brave_search + browse_url + web_research insieme per la stessa domanda.
- Massimo 2-3 chiamate tool per rispondere a una domanda. Se dopo 3 tool non hai la risposta, rispondi con quello che hai.'''

if OLD_MAPPING in content:
    content = content.replace(OLD_MAPPING, NEW_MAPPING)
    with open(prompt_path, 'w') as f:
        f.write(content)
    print("✅ System prompt aggiornato con regole efficienza ricerche!")
    print("   + web_research come tool principale per ricerche")
    print("   + Regole anti-spam (max 2-3 chiamate per domanda)")
    print("   + Divieto di usare brave_search + browse_url + web_research insieme")
    print("\nOra fai: docker compose build && docker compose up -d")
else:
    print("⚠️  Testo da sostituire non trovato nel system prompt.")
    print("   Forse e' gia' stato modificato o il formato e' diverso.")
    print("   Provo inserimento diretto...")
    
    # Fallback: inserisci dopo "REGOLA ASSOLUTA"
    marker = "MAI chiedere \"cosa vuoi che faccia?\" - INTERPRETA e AGISCI."
    if marker in content:
        insert = """\n
REGOLE EFFICIENZA RICERCHE WEB:
- Per ricerche semplici: usa web_research UNA VOLTA e rispondi. NON aggiungere brave_search + browse_url separati.
- web_research = fa gia' tutto (cerca + apre pagine + riassume). Basta UNA chiamata.
- brave_search = usa SOLO se vuoi risultati rapidi senza leggere le pagine (es. "che ora e' a Tokyo").
- browse_url = usa SOLO per aprire UN sito specifico che conosci gia' (es. "apri ildormire.com").
- MAI usare brave_search + browse_url + web_research insieme per la stessa domanda.
- Massimo 2-3 chiamate tool per rispondere a una domanda. Se dopo 3 tool non hai la risposta, rispondi con quello che hai.
"""
        content = content.replace(marker, marker + insert)
        with open(prompt_path, 'w') as f:
            f.write(content)
        print("✅ Regole efficienza inserite dopo le regole tool!")
    else:
        print("❌ Non riesco a trovare il punto di inserimento. Modifica manuale necessaria.")
