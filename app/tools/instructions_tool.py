"""
instructions_tool.py - Tool per gestire le istruzioni utente in nik29-coordinator v0.5.1

Permette di leggere e gestire un file istruzioni editabile dall'utente
che definisce preferenze, regole e procedure per il comportamento del coordinator.
"""

import os
import re
from typing import Optional

# Percorso del file istruzioni
INSTRUCTIONS_FILE = "/data/memory/istruzioni.md"

# Template default per il file istruzioni (creato al primo avvio)
DEFAULT_INSTRUCTIONS = """# Istruzioni per Nik29

## Chi sono
Nicola è il titolare de "Il Dormire" (Sgambelluri srls) a Siderno (RC).
Negozio specializzato in materassi, cuscini e reti da letto.
Sito web: ildormire.com
Non ha competenze informatiche avanzate — le istruzioni devono essere semplici e pratiche.

## Come rispondere
- Rispondi sempre in italiano
- Sii diretto e pratico, evita tecnicismi inutili
- Quando fai modifiche al sito, spiega cosa hai fatto in modo semplice
- Se qualcosa non è chiaro, chiedi prima di procedere
- Preferisci azioni concrete a spiegazioni lunghe

## Regole importanti
- MAI riscrivere un file da zero — solo modifiche chirurgiche
- Testare SEMPRE prima di dire "è pronto"
- Backup prima di ogni modifica importante
- Se un task fallisce, ritentare con approccio diverso prima di chiedere aiuto

## Procedure
### Deploy sul VPS
1. Push su GitHub
2. SSH sul VPS: cd /root/dormire-shop && git pull && npm run build && pm2 restart dormire-shop
3. Verificare che il sito risponda correttamente

### Aggiornamento prodotti
1. Accedere al pannello admin
2. Modificare/aggiungere il prodotto
3. Verificare che appaia correttamente sul sito

### Troubleshooting comune
- Sito non risponde → controllare PM2 status e logs
- Database non connette → verificare MySQL e credenziali
- Build fallisce → controllare errori TypeScript/ESLint
"""


# Definizione tool per OpenAI function calling
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "instructions",
        "description": "Gestisce il file istruzioni utente. Permette di leggere, aggiornare e organizzare le istruzioni che definiscono come comportarsi.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "update", "list_sections", "add_section"],
                    "description": "Azione: 'read' legge le istruzioni, 'update' aggiorna una sezione, 'list_sections' elenca le sezioni, 'add_section' aggiunge una nuova sezione"
                },
                "section": {
                    "type": "string",
                    "description": "Nome della sezione da aggiornare (richiesto per 'update')"
                },
                "content": {
                    "type": "string",
                    "description": "Nuovo contenuto della sezione (richiesto per 'update' e 'add_section')"
                },
                "title": {
                    "type": "string",
                    "description": "Titolo della nuova sezione (richiesto per 'add_section')"
                }
            },
            "required": ["action"]
        }
    }
}


class InstructionsTool:
    """Tool per gestire il file istruzioni utente."""

    def __init__(self):
        self.name = "instructions"
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Crea il file istruzioni con il template default se non esiste."""
        os.makedirs(os.path.dirname(INSTRUCTIONS_FILE), exist_ok=True)
        if not os.path.exists(INSTRUCTIONS_FILE):
            with open(INSTRUCTIONS_FILE, "w", encoding="utf-8") as f:
                f.write(DEFAULT_INSTRUCTIONS)

    def _read_file(self) -> str:
        """Legge il contenuto del file istruzioni."""
        self._ensure_file_exists()
        try:
            with open(INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            return f"Errore lettura file: {e}"

    def _write_file(self, content: str) -> None:
        """Scrive il contenuto nel file istruzioni (atomico)."""
        self._ensure_file_exists()
        tmp_path = INSTRUCTIONS_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, INSTRUCTIONS_FILE)
        except OSError:
            with open(INSTRUCTIONS_FILE, "w", encoding="utf-8") as f:
                f.write(content)

    def _parse_sections(self, content: str) -> list:
        """
        Estrae le sezioni (## header) dal contenuto markdown.
        Ritorna lista di tuple (titolo, contenuto, start_pos, end_pos).
        """
        sections = []
        # Pattern per trovare headers ## (livello 2)
        pattern = r'^## (.+)$'
        matches = list(re.finditer(pattern, content, re.MULTILINE))

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[match.end():end].strip()
            sections.append((title, section_content, start, end))

        return sections

    async def execute(self, action: str, **kwargs) -> str:
        """
        Esegue l'azione richiesta sul file istruzioni.
        
        Args:
            action: Una tra "read", "update", "list_sections", "add_section"
            **kwargs: Parametri aggiuntivi specifici per l'azione
        
        Returns:
            Stringa con il risultato dell'azione
        """
        try:
            if action == "read":
                return await self._action_read()
            elif action == "update":
                return await self._action_update(
                    kwargs.get("section", ""),
                    kwargs.get("content", "")
                )
            elif action == "list_sections":
                return await self._action_list_sections()
            elif action == "add_section":
                return await self._action_add_section(
                    kwargs.get("title", ""),
                    kwargs.get("content", "")
                )
            else:
                return f"❌ Azione non riconosciuta: '{action}'. Usa: read, update, list_sections, add_section"
        except Exception as e:
            return f"❌ Errore in instructions/{action}: {str(e)}"

    async def _action_read(self) -> str:
        """Legge e restituisce il contenuto completo delle istruzioni."""
        content = self._read_file()
        if content.startswith("Errore"):
            return f"❌ {content}"
        return f"📄 Contenuto istruzioni:\n\n{content}"

    async def _action_update(self, section: str, content: str) -> str:
        """Aggiorna il contenuto di una sezione specifica."""
        if not section.strip():
            return "❌ Specifica il nome della sezione da aggiornare."
        if not content.strip():
            return "❌ Specifica il nuovo contenuto per la sezione."

        file_content = self._read_file()
        sections = self._parse_sections(file_content)

        # Cerca la sezione (match parziale case-insensitive)
        section_lower = section.lower().strip()
        target = None
        for title, sec_content, start, end in sections:
            if section_lower in title.lower() or title.lower() in section_lower:
                target = (title, sec_content, start, end)
                break

        if not target:
            available = [s[0] for s in sections]
            return f"❌ Sezione '{section}' non trovata. Sezioni disponibili: {', '.join(available)}"

        title, old_content, start, end = target

        # Ricostruisci il file con la sezione aggiornata
        new_section = f"## {title}\n{content.strip()}\n\n"
        new_file_content = file_content[:start] + new_section + file_content[end:]

        self._write_file(new_file_content)
        return f"✅ Sezione '{title}' aggiornata con successo."

    async def _action_list_sections(self) -> str:
        """Elenca tutte le sezioni del file istruzioni."""
        content = self._read_file()
        sections = self._parse_sections(content)

        if not sections:
            return "📄 Nessuna sezione trovata nel file istruzioni."

        lines = [f"📑 Sezioni nel file istruzioni ({len(sections)}):"]
        for i, (title, sec_content, _, _) in enumerate(sections, 1):
            # Conta righe non vuote per dare un'idea della dimensione
            line_count = len([l for l in sec_content.split("\n") if l.strip()])
            lines.append(f"  {i}. {title} ({line_count} righe)")

        return "\n".join(lines)

    async def _action_add_section(self, title: str, content: str) -> str:
        """Aggiunge una nuova sezione al file istruzioni."""
        if not title.strip():
            return "❌ Specifica il titolo della nuova sezione."
        if not content.strip():
            return "❌ Specifica il contenuto della nuova sezione."

        file_content = self._read_file()
        sections = self._parse_sections(file_content)

        # Controlla che non esista già
        title_lower = title.lower().strip()
        for existing_title, _, _, _ in sections:
            if title_lower == existing_title.lower():
                return f"⚠️ La sezione '{existing_title}' esiste già. Usa 'update' per modificarla."

        # Aggiungi in fondo
        new_section = f"\n## {title.strip()}\n{content.strip()}\n"
        new_content = file_content.rstrip() + "\n" + new_section

        self._write_file(new_content)
        return f"✅ Nuova sezione '{title}' aggiunta con successo."


def get_instructions_context() -> str:
    """
    Restituisce un riassunto delle istruzioni per il system prompt.
    Usato dal coordinator per avere sempre il contesto delle preferenze utente.
    """
    tool = InstructionsTool()
    content = tool._read_file()
    if content.startswith("Errore") or not content.strip():
        return ""

    # Restituisci solo le sezioni "Come rispondere" e "Regole importanti"
    sections = tool._parse_sections(content)
    relevant = []
    for title, sec_content, _, _ in sections:
        title_lower = title.lower()
        if any(k in title_lower for k in ["come rispondere", "regole importanti"]):
            relevant.append(f"### {title}\n{sec_content}")

    if relevant:
        return "\n## Istruzioni Utente\n" + "\n\n".join(relevant)
    return ""
