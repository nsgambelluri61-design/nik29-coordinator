#!/usr/bin/env python3
"""
patch_v2_features.py — Patch per nik29-coordinator v0.6.0
Aggiunge:
1. coordinator.py: Supporto Vision (immagini → GPT-4.1 multimodal)
2. static/index.html: marked.js per markdown rendering + file attachment cards + pulsante copia
Testato su clone locale. Eseguire nella root del progetto.
"""
import os
import re
import sys

def find_project_root():
    """Trova la root del progetto."""
    candidates = [
        os.getcwd(),
        os.path.expanduser("~/Downloads/nik29-coordinator-v0.6.0"),
        "/app"
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "app", "coordinator.py")):
            return c
    print("ERRORE: Non trovo la root del progetto. Esegui dalla directory del progetto.")
    sys.exit(1)


def find_function(content, signature):
    """Trova una funzione JS tramite brace-counting. Ritorna (start, end) o None."""
    start = content.find(signature)
    if start < 0:
        return None
    search = content[start:]
    brace_count = 0
    end_idx = 0
    for i, ch in enumerate(search):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    if end_idx == 0:
        return None
    return (start, start + end_idx)


def patch_coordinator_vision(root):
    """Aggiunge supporto Vision: immagini caricate -> content multimodal per GPT-4.1."""
    coord_path = os.path.join(root, "app", "coordinator.py")
    with open(coord_path, "r") as f:
        content = f.read()
    
    if "IMAGE_EXTENSIONS" in content:
        print("  [SKIP] Vision gia' presente in coordinator.py")
        return True
    
    new_block = '''        # Gestisci file caricati (con supporto Vision per immagini)
        import base64 as _b64
        IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
        file_info = ""
        image_parts = []
        if uploaded_files:
            for uf in uploaded_files:
                fname = uf.get('filename', uf.get('name', 'unknown'))
                furl = uf.get('url', '')
                ext = os.path.splitext(fname)[1].lower()
                if ext in IMAGE_EXTENSIONS and furl:
                    # Prova a leggere il file locale per base64
                    local_path = furl.split('/files/')[-1] if '/files/' in furl else ''
                    workspace_path = os.path.join('/data/workspace', local_path)
                    if os.path.exists(workspace_path):
                        with open(workspace_path, 'rb') as img_f:
                            img_b64 = _b64.b64encode(img_f.read()).decode('utf-8')
                        mime_ext = ext.replace('.', '')
                        if mime_ext == 'jpg': mime_ext = 'jpeg'
                        image_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/{mime_ext};base64,{img_b64}"}
                        })
                    else:
                        # URL esterno
                        image_parts.append({
                            "type": "image_url",
                            "image_url": {"url": furl}
                        })
                else:
                    file_info += f"\\n[File caricato: {fname}]"
        # Costruisci messaggio utente (multimodal se ci sono immagini)
        if image_parts:
            user_content = [{"type": "text", "text": user_message + file_info}] + image_parts
            messages.append({"role": "user", "content": user_content})
        else:
            content = user_message + file_info
            messages.append({"role": "user", "content": content})'''
    
    # Regex flessibile per trovare il blocco (con \n? per blank line opzionale)
    pattern = r'        # Gestisci file caricati\n        file_info = ""\n        if uploaded_files:\n            for f in uploaded_files:\n[^\n]+\n\n?        # Aggiungi messaggio utente\n        content = user_message \+ file_info\n        messages\.append\(\{"role": "user", "content": content\}\)'
    match = re.search(pattern, content)
    if match:
        content = content[:match.start()] + new_block + content[match.end():]
        with open(coord_path, "w") as f:
            f.write(content)
        print("  [OK] Vision support aggiunto a coordinator.py")
        return True
    else:
        print("  [ERRORE] Blocco uploaded_files non trovato. Verifica coordinator.py manualmente.")
        return False


def patch_index_html(root):
    """Aggiunge marked.js, stili markdown, pulsante copia, file attachment cards."""
    index_path = os.path.join(root, "static", "index.html")
    with open(index_path, "r") as f:
        content = f.read()
    
    changes = 0
    
    # 1. Aggiungi marked.js CDN e stili extra prima di </head>
    if 'marked' not in content:
        extra_head = '''  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    /* Markdown enhanced styles for msg-bubble */
    .msg-bubble h1, .msg-bubble h2, .msg-bubble h3 {
      margin: 0.5em 0 0.3em; color: var(--green-bright); font-family: var(--font-mono);
    }
    .msg-bubble h1 { font-size: 1.2em; }
    .msg-bubble h2 { font-size: 1.1em; }
    .msg-bubble h3 { font-size: 1.0em; }
    .msg-bubble ul, .msg-bubble ol { margin: 0.4em 0; padding-left: 1.5em; }
    .msg-bubble li { margin: 0.2em 0; }
    .msg-bubble table { border-collapse: collapse; margin: 0.5em 0; width: 100%; }
    .msg-bubble th, .msg-bubble td {
      border: 1px solid var(--border); padding: 4px 8px; text-align: left; font-size: 12px;
    }
    .msg-bubble th { background: rgba(0,255,65,0.05); color: var(--green-mid); }
    .msg-bubble blockquote {
      border-left: 3px solid var(--green-mid); margin: 0.5em 0;
      padding: 0.3em 0.8em; background: rgba(0,255,65,0.03);
    }
    .msg-bubble a { color: var(--green-bright); text-decoration: underline; }
    .msg-bubble strong { color: var(--green-bright); }
    .msg-bubble img { max-width: 100%; border-radius: var(--radius); margin: 4px 0; }
    .msg-bubble p { margin: 0.3em 0; }
    /* File attachment cards */
    .file-card {
      display: inline-flex; align-items: center; gap: 8px;
      background: rgba(0,255,65,0.05); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 6px 12px; margin: 4px 4px 4px 0;
      cursor: pointer; transition: all 0.2s; text-decoration: none;
    }
    .file-card:hover { background: rgba(0,255,65,0.1); border-color: var(--green-mid); }
    .file-card-icon { font-size: 1.2em; }
    .file-card-name { font-size: 12px; color: var(--text-assist); max-width: 180px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-card-size { font-size: 10px; color: var(--text-muted); }
    /* Copy button */
    .copy-btn {
      position: absolute; top: 4px; right: 4px;
      background: var(--bg-card); border: 1px solid var(--border);
      border-radius: 3px; color: var(--text-muted); cursor: pointer;
      padding: 2px 6px; font-size: 10px; font-family: var(--font-mono);
      opacity: 0; transition: opacity 0.2s;
    }
    .msg-row:hover .copy-btn { opacity: 1; }
    .copy-btn:hover { color: var(--green-bright); border-color: var(--green-mid); }
  </style>
'''
        content = content.replace('</head>', extra_head + '</head>')
        changes += 1
        print("  [OK] marked.js CDN + stili markdown/attachment aggiunti")
    else:
        print("  [SKIP] marked.js gia' presente")
    
    # 2. Sostituisci formatContent con marked.parse usando brace-counting
    new_format = '''  function formatContent(text) {
    // Usa marked.js se disponibile, altrimenti fallback basico
    if (typeof marked !== 'undefined') {
      try {
        marked.setOptions({ breaks: true, gfm: true });
        return marked.parse(text);
      } catch(e) { /* fallback sotto */ }
    }
    // Fallback basico
    let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    html = html.replace(/```(\\w*)\\n?([\\s\\S]*?)```/g, (_, lang, code) => `<pre><code>${code.trim()}</code></pre>`);
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
    html = html.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
    html = html.replace(/\\n/g, '<br>');
    return html;
  }'''
    
    if 'marked.parse' not in content:
        bounds = find_function(content, '  function formatContent(text) {')
        if bounds:
            content = content[:bounds[0]] + new_format + content[bounds[1]:]
            changes += 1
            print("  [OK] formatContent sostituita con marked.parse + fallback")
        else:
            print("  [WARN] formatContent non trovata")
    else:
        print("  [SKIP] formatContent gia' usa marked.parse")
    
    # 3. Sostituisci appendMessage con versione che supporta files + copy button
    new_append = '''  function appendMessage(role, content, files) {
    msgCount++;
    msgCountDisp.textContent = msgCount;

    const now    = new Date();
    const timeStr = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const label  = role === 'user' ? 'YOU' : 'NIK29';

    const row    = document.createElement('div');
    row.className = `msg-row ${role}`;
    row.style.position = 'relative';

    const meta   = document.createElement('div');
    meta.className = 'msg-meta';
    meta.textContent = `${label} \u00b7 ${timeStr}`;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = formatContent(content);

    // Pulsante copia per assistant
    if (role === 'assistant') {
      const copyBtn = document.createElement('button');
      copyBtn.className = 'copy-btn';
      copyBtn.textContent = '[COPY]';
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(content);
        copyBtn.textContent = '[OK!]';
        setTimeout(() => copyBtn.textContent = '[COPY]', 1500);
      };
      row.appendChild(copyBtn);
    }

    // File attachment cards
    if (files && files.length > 0) {
      const attachDiv = document.createElement('div');
      attachDiv.style.marginTop = '6px';
      files.forEach(file => {
        const card = document.createElement('a');
        card.className = 'file-card';
        card.href = file.url || '#';
        card.target = '_blank';
        card.download = file.filename || file.name || 'file';
        const ext = (file.filename || file.name || '').split('.').pop().toLowerCase();
        const icons = {pdf:'📄',zip:'📦',png:'🖼️',jpg:'🖼️',jpeg:'🖼️',webp:'🖼️',py:'🐍',js:'📜',json:'📋',csv:'📊',md:'📝'};
        const iconSpan = document.createElement('span');
        iconSpan.className = 'file-card-icon';
        iconSpan.textContent = icons[ext] || '📎';
        const nameSpan = document.createElement('span');
        nameSpan.className = 'file-card-name';
        nameSpan.textContent = file.filename || file.name || 'file';
        card.appendChild(iconSpan);
        card.appendChild(nameSpan);
        if (file.size) {
          const sizeSpan = document.createElement('span');
          sizeSpan.className = 'file-card-size';
          const kb = file.size < 1024*1024 ? (file.size/1024).toFixed(1)+'KB' : (file.size/1024/1024).toFixed(1)+'MB';
          sizeSpan.textContent = kb;
          card.appendChild(sizeSpan);
        }
        attachDiv.appendChild(card);
      });
      bubble.appendChild(attachDiv);
    }

    row.appendChild(meta);
    row.appendChild(bubble);

    // Insert before thinking row
    chatWindow.insertBefore(row, thinkingRow);
    scrollToBottom();
  }'''
    
    if 'function appendMessage(role, content, files)' not in content:
        bounds = find_function(content, '  function appendMessage(role, content) {')
        if bounds:
            content = content[:bounds[0]] + new_append + content[bounds[1]:]
            changes += 1
            print("  [OK] appendMessage aggiornata con copy button + file cards")
        else:
            print("  [WARN] appendMessage non trovata")
    else:
        print("  [SKIP] appendMessage gia' aggiornata")
    
    # 4. Aggiorna la chiamata appendMessage nel WS handler per passare data.files
    old_ws = "    appendMessage('assistant', content);"
    new_ws = "    appendMessage('assistant', content, data.files || []);"
    if old_ws in content and 'data.files' not in content:
        content = content.replace(old_ws, new_ws)
        changes += 1
        print("  [OK] WS handler aggiornato per passare files")
    elif 'data.files' in content:
        print("  [SKIP] WS handler gia' passa files")
    
    # 5. Rimuovi white-space: pre-wrap (conflitto con marked.js che genera <p> tags)
    if 'white-space: pre-wrap;' in content:
        content = content.replace('      white-space: pre-wrap;\n', '')
        changes += 1
        print("  [OK] Rimosso white-space: pre-wrap (conflitto con marked.js)")
    
    with open(index_path, "w") as f:
        f.write(content)
    
    print(f"  Totale modifiche: {changes}")
    return changes > 0


def main():
    root = find_project_root()
    print("=" * 60)
    print("  PATCH v2: Vision + Markdown + Allegati + Copy")
    print("=" * 60)
    print(f"  Directory: {root}")
    print()
    
    print("[1/2] Patch coordinator.py (Vision support)...")
    patch_coordinator_vision(root)
    print()
    
    print("[2/2] Patch index.html (Markdown + Allegati + Copy)...")
    patch_index_html(root)
    print()
    
    print("=" * 60)
    print("  FATTO! Ora esegui:")
    print("  docker compose build && docker compose up -d")
    print()
    print("  Test Vision: carica un'immagine e chiedi 'cosa vedi?'")
    print("  Test Markdown: chiedi qualcosa di complesso")
    print("=" * 60)


if __name__ == "__main__":
    main()
