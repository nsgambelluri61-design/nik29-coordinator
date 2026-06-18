#!/usr/bin/env python3
"""
nik29-coordinator: Patch per installare il Framework Multi-Agente.

Esegui con: python3 patch_agents.py

Questo script:
1. Crea la directory data/agents/ (se non esiste)
2. Copia i file del framework in app/agents/
3. Copia l'agente SEO di esempio in data/agents/
4. Patcha coordinator.py per registrare i nuovi tool
5. Verifica l'installazione

PREREQUISITO: Eseguire dalla root del progetto nik29-coordinator-v0.6.0/
"""

import os
import sys
import shutil
import json
from pathlib import Path

# Colori per output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def log_ok(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def log_err(msg):
    print(f"{RED}❌ {msg}{RESET}")

def log_info(msg):
    print(f"{BLUE}ℹ️  {msg}{RESET}")

def log_warn(msg):
    print(f"{YELLOW}⚠️  {msg}{RESET}")


def find_project_root():
    """Trova la root del progetto nik29-coordinator."""
    # Cerca coordinator.py nella directory corrente o in app/
    cwd = Path.cwd()
    
    # Controlla se siamo già nella root del progetto
    if (cwd / "app" / "coordinator.py").exists():
        return cwd
    if (cwd / "coordinator.py").exists():
        return cwd
    
    # Controlla se il patch è stato copiato dentro il progetto
    script_dir = Path(__file__).parent
    if (script_dir / "app" / "coordinator.py").exists():
        return script_dir
    
    return None


def step1_create_directories(root: Path):
    """Crea le directory necessarie."""
    log_info("Step 1: Creazione directory...")
    
    dirs = [
        root / "data" / "agents",
        root / "app" / "agents",
    ]
    
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        log_ok(f"Directory: {d.relative_to(root)}")


def step2_copy_framework_files(root: Path):
    """Copia i file del framework multi-agente."""
    log_info("Step 2: Copia file framework...")
    
    script_dir = Path(__file__).parent
    
    # File da copiare
    files_to_copy = {
        "app/agents/__init__.py": script_dir / "app" / "agents" / "__init__.py",
        "app/agents/agent_manager.py": script_dir / "app" / "agents" / "agent_manager.py",
        "app/agents/agent_tools.py": script_dir / "app" / "agents" / "agent_tools.py",
    }
    
    for dest_rel, src in files_to_copy.items():
        dest = root / dest_rel
        if src.exists():
            shutil.copy2(src, dest)
            log_ok(f"Copiato: {dest_rel}")
        else:
            # Se eseguito dalla stessa directory, i file sono già al posto giusto
            if dest.exists():
                log_ok(f"Già presente: {dest_rel}")
            else:
                log_err(f"File sorgente non trovato: {src}")
                return False
    
    return True


def step3_copy_example_agent(root: Path):
    """Copia l'agente SEO di esempio."""
    log_info("Step 3: Installazione agente SEO di esempio...")
    
    script_dir = Path(__file__).parent
    src = script_dir / "data" / "agents" / "agente_seo.json"
    dest = root / "data" / "agents" / "agente_seo.json"
    
    if src.exists():
        shutil.copy2(src, dest)
    elif not dest.exists():
        # Crea l'agente inline se il file sorgente non è disponibile
        agent_data = {
            "name": "agente_seo",
            "role": "Specialista SEO per ildormire.com",
            "description": "Agente dedicato all'ottimizzazione SEO del sito ildormire.com",
            "capabilities": "Analisi posizionamento, audit SEO, ottimizzazione contenuti, monitoraggio competitor",
            "system_prompt": "Sei agente_seo, specialista SEO per ildormire.com...",
            "tools": ["brave_search", "web_research", "deep_research", "browse_url"],
            "model": "gpt-4.1",
            "created_at": "2026-06-18T10:00:00Z",
            "last_used": None,
            "total_tasks": 0
        }
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(agent_data, f, indent=2, ensure_ascii=False)
    
    log_ok(f"Agente SEO installato: data/agents/agente_seo.json")


def step4_patch_coordinator(root: Path):
    """Patcha coordinator.py per registrare i tool multi-agente."""
    log_info("Step 4: Patch coordinator.py...")
    
    coordinator_path = root / "app" / "coordinator.py"
    if not coordinator_path.exists():
        coordinator_path = root / "coordinator.py"
    
    if not coordinator_path.exists():
        log_err("coordinator.py non trovato!")
        return False
    
    with open(coordinator_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Backup
    backup_path = coordinator_path.with_suffix(".py.bak_agents")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    log_ok(f"Backup creato: {backup_path.name}")
    
    changes_made = False
    
    # --- PATCH 1: Aggiungere import in cima ---
    import_block = """
# === MULTI-AGENT FRAMEWORK ===
from app.agents import AgentManager
from app.agents.agent_tools import (
    ALL_AGENT_TOOL_SCHEMAS,
    handle_create_agent,
    handle_delegate_to_agent,
    handle_list_agents,
)
# === END MULTI-AGENT FRAMEWORK ===
"""
    
    if "AgentManager" not in content:
        # Trova un buon punto per inserire l'import (dopo gli altri import)
        # Cerca l'ultimo "import" o "from" statement
        lines = content.split("\n")
        last_import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                last_import_idx = i
        
        lines.insert(last_import_idx + 1, import_block)
        content = "\n".join(lines)
        changes_made = True
        log_ok("Import AgentManager aggiunto")
    else:
        log_warn("Import AgentManager già presente, skip")
    
    # --- PATCH 2: Inizializzazione AgentManager ---
    init_block = """
# === MULTI-AGENT: Inizializzazione ===
agent_manager = None  # Inizializzato dopo la definizione di _execute_tool

def _init_agent_manager():
    global agent_manager
    agent_manager = AgentManager(tool_executor=_execute_tool)
    print(f"[nik29] AgentManager inizializzato con {len(agent_manager.list_agents())} agenti")
# === END MULTI-AGENT INIT ===
"""
    
    if "agent_manager" not in content and "_init_agent_manager" not in content:
        # Inserisci dopo la definizione di _execute_tool
        if "_execute_tool" in content:
            # Trova la fine della funzione _execute_tool
            idx = content.find("_execute_tool")
            # Trova la prossima funzione o classe dopo _execute_tool
            next_def = content.find("\ndef ", idx + 20)
            next_class = content.find("\nclass ", idx + 20)
            
            insert_pos = None
            if next_def > 0 and next_class > 0:
                insert_pos = min(next_def, next_class)
            elif next_def > 0:
                insert_pos = next_def
            elif next_class > 0:
                insert_pos = next_class
            
            if insert_pos:
                content = content[:insert_pos] + "\n" + init_block + "\n" + content[insert_pos:]
                changes_made = True
                log_ok("Inizializzazione AgentManager aggiunta")
            else:
                # Aggiungi alla fine
                content += "\n" + init_block
                changes_made = True
                log_ok("Inizializzazione AgentManager aggiunta (in fondo)")
        else:
            log_warn("_execute_tool non trovato, aggiungo init in fondo")
            content += "\n" + init_block
            changes_made = True
    else:
        log_warn("Inizializzazione AgentManager già presente, skip")
    
    # --- PATCH 3: Registrazione tool nel dispatcher _execute_tool ---
    dispatcher_block = """
    # === MULTI-AGENT TOOLS ===
    elif tool_name == "create_agent":
        if agent_manager is None:
            _init_agent_manager()
        return await handle_create_agent(args, agent_manager)
    elif tool_name == "delegate_to_agent":
        if agent_manager is None:
            _init_agent_manager()
        return await handle_delegate_to_agent(args, agent_manager, all_tools_schemas=tools)
    elif tool_name == "list_agents":
        if agent_manager is None:
            _init_agent_manager()
        return await handle_list_agents(args, agent_manager)
    # === END MULTI-AGENT TOOLS ==="""
    
    if "create_agent" not in content or "handle_create_agent" not in content:
        # Cerca il pattern del dispatcher (elif tool_name == ...)
        # Trova l'ultimo elif nel dispatcher
        if "_execute_tool" in content:
            # Cerca "else:" o "return" alla fine del dispatcher
            # Strategia: trova l'ultima occorrenza di 'elif tool_name ==' 
            last_elif_idx = content.rfind('elif tool_name ==')
            if last_elif_idx > 0:
                # Trova la fine di quel blocco elif (prossimo elif, else, o return non indentato)
                search_from = last_elif_idx + 20
                next_elif = content.find('\n    elif ', search_from)
                next_else = content.find('\n    else:', search_from)
                next_return = content.find('\n    return ', search_from)
                
                # Prendi il primo tra else e return (che segna la fine del dispatcher)
                candidates = [x for x in [next_else, next_return] if x > 0]
                if candidates:
                    insert_pos = min(candidates)
                    content = content[:insert_pos] + dispatcher_block + "\n" + content[insert_pos:]
                    changes_made = True
                    log_ok("Tool multi-agente registrati nel dispatcher")
                else:
                    log_warn("Non riesco a trovare la fine del dispatcher, patch manuale necessaria")
            else:
                log_warn("Pattern dispatcher non trovato, patch manuale necessaria")
        else:
            log_warn("_execute_tool non trovato, patch manuale necessaria")
    else:
        log_warn("Tool multi-agente già registrati nel dispatcher, skip")
    
    # --- PATCH 4: Aggiungere schemas alla lista tools ---
    schema_block = """
# === MULTI-AGENT: Aggiungi schemas alla lista tools ===
tools.extend(ALL_AGENT_TOOL_SCHEMAS)
# === END MULTI-AGENT SCHEMAS ===
"""
    
    if "ALL_AGENT_TOOL_SCHEMAS" not in content or "tools.extend(ALL_AGENT_TOOL_SCHEMAS)" not in content:
        # Cerca dove viene definita la lista 'tools' (di solito è una lista di dict)
        # Pattern comune: tools = [...] oppure TOOLS = [...]
        if "tools = [" in content.lower() or "tools=" in content.lower():
            # Trova la fine della definizione della lista tools
            # Cerca 'tools = [' (case insensitive per il nome variabile)
            import re
            match = re.search(r'^(tools\s*=\s*\[)', content, re.MULTILINE | re.IGNORECASE)
            if match:
                # Trova la chiusura della lista (] corrispondente)
                start = match.start()
                bracket_count = 0
                end_pos = start
                for i in range(start, len(content)):
                    if content[i] == '[':
                        bracket_count += 1
                    elif content[i] == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            end_pos = i + 1
                            break
                
                # Inserisci dopo la chiusura della lista
                content = content[:end_pos] + "\n" + schema_block + content[end_pos:]
                changes_made = True
                log_ok("Schema tool multi-agente aggiunti alla lista tools")
            else:
                log_warn("Lista 'tools' non trovata con regex, aggiungo in fondo")
                content += "\n" + schema_block
                changes_made = True
        else:
            log_warn("Variabile 'tools' non trovata, aggiungo extend in fondo")
            content += "\n" + schema_block
            changes_made = True
    else:
        log_warn("Schema tool già registrati, skip")
    
    # --- PATCH 5: Chiamata _init_agent_manager() all'avvio ---
    startup_block = """
# === MULTI-AGENT: Init all'avvio ===
_init_agent_manager()
"""
    
    if "_init_agent_manager()" not in content or content.count("_init_agent_manager()") < 2:
        # Cerca un punto di startup (es. if __name__ == "__main__" o app startup)
        if 'if __name__' in content:
            idx = content.find('if __name__')
            # Inserisci prima del main
            content = content[:idx] + startup_block + "\n" + content[idx:]
            changes_made = True
            log_ok("Chiamata _init_agent_manager() aggiunta all'avvio")
        elif '@app.on_event("startup")' in content:
            idx = content.find('@app.on_event("startup")')
            content = content[:idx] + startup_block + "\n" + content[idx:]
            changes_made = True
            log_ok("Chiamata _init_agent_manager() aggiunta prima dello startup")
        else:
            # Aggiungi alla fine
            content += "\n" + startup_block
            changes_made = True
            log_ok("Chiamata _init_agent_manager() aggiunta in fondo")
    
    # Salva
    if changes_made:
        with open(coordinator_path, "w", encoding="utf-8") as f:
            f.write(content)
        log_ok(f"coordinator.py patchato con successo!")
    else:
        log_warn("Nessuna modifica necessaria a coordinator.py")
    
    return True


def step5_verify(root: Path):
    """Verifica che tutto sia al posto giusto."""
    log_info("Step 5: Verifica installazione...")
    
    checks = [
        ("app/agents/__init__.py", "Package agents"),
        ("app/agents/agent_manager.py", "AgentManager"),
        ("app/agents/agent_tools.py", "Tool definitions"),
        ("data/agents/agente_seo.json", "Agente SEO esempio"),
    ]
    
    all_ok = True
    for path_rel, desc in checks:
        full_path = root / path_rel
        if full_path.exists():
            log_ok(f"{desc}: {path_rel}")
        else:
            log_err(f"{desc} MANCANTE: {path_rel}")
            all_ok = False
    
    # Verifica che coordinator.py contenga i patch
    coordinator_path = root / "app" / "coordinator.py"
    if not coordinator_path.exists():
        coordinator_path = root / "coordinator.py"
    
    if coordinator_path.exists():
        content = coordinator_path.read_text()
        if "AgentManager" in content:
            log_ok("coordinator.py: import AgentManager presente")
        else:
            log_warn("coordinator.py: import AgentManager NON trovato (patch manuale necessaria)")
            all_ok = False
    
    return all_ok


def print_manual_patch_instructions():
    """Stampa istruzioni per patch manuale se l'automatico fallisce."""
    print(f"""
{YELLOW}{'='*60}
ISTRUZIONI PER PATCH MANUALE (se il patch automatico fallisce)
{'='*60}{RESET}

Se il patch automatico non riesce a modificare coordinator.py,
aggiungi manualmente queste modifiche:

{BLUE}1. In cima al file (dopo gli altri import):{RESET}
   from app.agents import AgentManager
   from app.agents.agent_tools import (
       ALL_AGENT_TOOL_SCHEMAS,
       handle_create_agent,
       handle_delegate_to_agent,
       handle_list_agents,
   )

{BLUE}2. Dopo la definizione di _execute_tool:{RESET}
   agent_manager = AgentManager(tool_executor=_execute_tool)

{BLUE}3. Nel dispatcher _execute_tool, aggiungi:{RESET}
   elif tool_name == "create_agent":
       return await handle_create_agent(args, agent_manager)
   elif tool_name == "delegate_to_agent":
       return await handle_delegate_to_agent(args, agent_manager, all_tools_schemas=tools)
   elif tool_name == "list_agents":
       return await handle_list_agents(args, agent_manager)

{BLUE}4. Dopo la definizione della lista tools:{RESET}
   tools.extend(ALL_AGENT_TOOL_SCHEMAS)
""")


def main():
    print(f"""
{BLUE}{'='*60}
  nik29-coordinator: Installazione Framework Multi-Agente
{'='*60}{RESET}
""")
    
    # Trova la root del progetto
    root = find_project_root()
    
    if root is None:
        log_err("Non riesco a trovare la root del progetto nik29-coordinator!")
        log_info("Assicurati di eseguire questo script dalla directory del progetto")
        log_info("oppure copia tutti i file nella directory del progetto prima di eseguire.")
        print(f"\n{YELLOW}Uso: cd ~/Downloads/nik29-coordinator-v0.6.0 && python3 patch_agents.py{RESET}")
        sys.exit(1)
    
    log_ok(f"Root progetto trovata: {root}")
    print()
    
    # Esegui gli step
    step1_create_directories(root)
    print()
    
    if not step2_copy_framework_files(root):
        log_err("Errore nella copia dei file. Controlla i permessi.")
        sys.exit(1)
    print()
    
    step3_copy_example_agent(root)
    print()
    
    if not step4_patch_coordinator(root):
        log_warn("Patch automatico parzialmente fallito.")
        print_manual_patch_instructions()
    print()
    
    if step5_verify(root):
        print(f"""
{GREEN}{'='*60}
  ✅ INSTALLAZIONE COMPLETATA CON SUCCESSO!
{'='*60}{RESET}

{BLUE}Prossimi passi:{RESET}
1. Ricostruisci il container Docker:
   docker compose build && docker compose up -d

2. Testa i nuovi tool via Telegram:
   - "Quali agenti hai?" → chiamerà list_agents
   - "Analizza la SEO di ildormire.com" → delegherà ad agente_seo
   - "Crea un agente social media" → chiamerà create_agent

3. Verifica i log:
   docker compose logs -f nik29

{YELLOW}Nota: L'agente SEO di esempio è già pre-configurato e pronto all'uso.{RESET}
""")
    else:
        log_warn("Installazione completata con avvisi. Controlla i messaggi sopra.")
        print_manual_patch_instructions()


if __name__ == "__main__":
    main()
