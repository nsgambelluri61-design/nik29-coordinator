# nik29-coordinator Web Chat Upgrade

Questo pacchetto contiene un aggiornamento completo dell'interfaccia web per il progetto `nik29-coordinator`. Sostituisce la vecchia interfaccia in stile terminale verde (Matrix) con una moderna in stile dark theme (simile a Manus/ChatGPT).

## Funzionalità Aggiunte

1. **Tema Dark Moderno**: Design pulito, palette colori professionale (`#1a1a2e`), angoli arrotondati e ombre leggere.
2. **Supporto Upload File**: 
   - Pulsante a graffetta per allegare file.
   - Supporto Drag & Drop per trascinare file direttamente nell'area della chat.
   - Anteprima file e immagini prima dell'invio.
   - Invio file tramite `multipart/form-data` verso `/api/chat`.
3. **Markdown Rendering**:
   - I messaggi del bot vengono formattati correttamente (grassetto, corsivo, liste, tabelle, intestazioni).
   - Evidenziazione della sintassi del codice tramite `highlight.js`.
   - Pulsante "Copia" integrato per i blocchi di codice.
4. **Visualizzazione Allegati**:
   - Le immagini allegate vengono mostrate inline nella chat.
   - I file di testo, PDF e altri documenti vengono mostrati come schede cliccabili per il download.
5. **Miglioramenti UX**:
   - Indicatori di stato (digitazione in corso, esecuzione tool).
   - Sidebar responsive (a comparsa su dispositivi mobili).
   - Supporto per `Shift+Enter` per nuova riga, `Enter` per inviare.

## Installazione

L'installazione è automatizzata tramite lo script Python incluso.

### Metodo 1: Script di Installazione (Consigliato)

1. Estrai il file zip nel server o nel container dove gira `nik29-coordinator`.
2. Esegui lo script di patch:
   ```bash
   python3 patch_interface.py
   ```
3. Lo script cercherà automaticamente la directory del progetto. Se non la trova, puoi specificarla manualmente:
   ```bash
   python3 patch_interface.py /percorso/a/nik29-coordinator
   ```
4. Lo script creerà automaticamente un backup del file `index.html` originale prima di sostituirlo.

### Metodo 2: Installazione Manuale

Se preferisci procedere manualmente:

1. Trova la directory del progetto `nik29-coordinator`.
2. Vai nella cartella `static/`.
3. Rinomina l'attuale `index.html` in `index.html.backup`.
4. Copia il file `static/index.html` presente in questo pacchetto nella cartella `static/` del progetto.

## Ripristino

In caso di problemi, puoi ripristinare la vecchia interfaccia:

```bash
cd /percorso/a/nik29-coordinator/static
cp index.html.backup_XXXXXXXX_XXXXXX index.html
```
*(sostituisci XXXXXXXX_XXXXXX con il timestamp reale del backup)*

## Requisiti

- L'interfaccia richiede una connessione a Internet per scaricare le librerie esterne via CDN (`marked.js`, `highlight.js`, `Google Fonts`).
- Il backend Python (`nik29-coordinator`) deve essere in esecuzione sulla porta 4001 (o quella configurata).
