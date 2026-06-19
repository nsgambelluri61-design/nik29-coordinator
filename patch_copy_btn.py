#!/usr/bin/env python3
"""
patch_copy_btn.py — Aggiunge pulsante "Copia" per copiare l'intero messaggio assistant.
Appare su hover sopra il messaggio. Funziona con l'interfaccia blu/viola attuale.
"""
import os
import sys

def find_project_root():
    candidates = [
        os.getcwd(),
        os.path.expanduser("~/Downloads/nik29-coordinator-v0.6.0"),
        "/app"
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "static", "index.html")):
            return c
    print("ERRORE: Non trovo la root del progetto.")
    sys.exit(1)

def patch(root):
    index_path = os.path.join(root, "static", "index.html")
    with open(index_path, "r") as f:
        content = f.read()
    
    if 'copy-msg-btn' in content:
        print("[SKIP] Pulsante copia messaggio gia' presente")
        return
    
    # 1. Aggiungi CSS per il pulsante copia messaggio
    css_block = """
        /* Copy message button */
        .message.assistant {
            position: relative;
        }
        .copy-msg-btn {
            position: absolute;
            top: 8px;
            right: 8px;
            padding: 4px 10px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text-muted);
            font-size: 11px;
            cursor: pointer;
            opacity: 0;
            transition: all 0.2s;
            z-index: 10;
        }
        .message.assistant:hover .copy-msg-btn {
            opacity: 1;
        }
        .copy-msg-btn:hover {
            color: var(--text-primary);
            border-color: var(--accent);
            background: var(--bg-secondary);
        }
"""
    # Inserisci prima di "/* Copy button for code blocks */"
    target_css = "/* Copy button for code blocks */"
    if target_css in content:
        content = content.replace(target_css, css_block + "        " + target_css)
        print("[OK] CSS pulsante copia messaggio aggiunto")
    else:
        # Fallback: inserisci prima di </style>
        content = content.replace("</style>", css_block + "    </style>", 1)
        print("[OK] CSS pulsante copia messaggio aggiunto (fallback)")
    
    # 2. Aggiungi il pulsante nel JS dopo addCopyButtons(contentDiv)
    old_js = "addCopyButtons(contentDiv);"
    new_js = """addCopyButtons(contentDiv);
                // Add copy-message button
                const copyMsgBtn = document.createElement('button');
                copyMsgBtn.className = 'copy-msg-btn';
                copyMsgBtn.textContent = 'Copia';
                copyMsgBtn.onclick = (e) => {
                    e.stopPropagation();
                    navigator.clipboard.writeText(content);
                    copyMsgBtn.textContent = 'Copiato!';
                    setTimeout(() => copyMsgBtn.textContent = 'Copia', 2000);
                };
                msgDiv.appendChild(copyMsgBtn);"""
    
    if old_js in content:
        content = content.replace(old_js, new_js, 1)
        print("[OK] Pulsante copia messaggio aggiunto in appendMessage")
    else:
        print("[ERRORE] 'addCopyButtons(contentDiv);' non trovato")
        return
    
    with open(index_path, "w") as f:
        f.write(content)
    
    print("\nFATTO! Riavvia con: docker compose up -d")
    print("Ora passa il mouse su un messaggio di nik29 -> appare 'Copia' in alto a destra")

if __name__ == "__main__":
    root = find_project_root()
    print(f"Directory: {root}")
    patch(root)
