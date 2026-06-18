# Tool `deep_research` per nik29-coordinator

Questo pacchetto aggiunge il tool **`deep_research`** al progetto `nik29-coordinator`. Il tool permette all'agente nik29 di eseguire ricerche web parallele approfondite: cerca su Brave Search, legge fino a 20 pagine contemporaneamente con `aiohttp` (con fallback automatico su Playwright per le pagine che richiedono JavaScript), estrae il testo pulito con `BeautifulSoup`, e produce una sintesi strutturata in italiano usando **GPT-4.1**.

---

## File inclusi

| File | Destinazione nel progetto | Descrizione |
|---|---|---|
| `deep_research.py` | `app/tools/deep_research.py` | Logica completa del tool |
| `patch_deep_research.py` | root del progetto | Script di installazione automatica |
| `README_DEEP_RESEARCH.md` | root del progetto | Queste istruzioni |

---

## Installazione in 4 passi

### Passo 1 — Copia il tool nella directory corretta

```bash
cp deep_research.py app/tools/
```

### Passo 2 — Esegui lo script di patch

Dalla **root** del progetto `nik29-coordinator`:

```bash
python3 patch_deep_research.py
```

Lo script esegue automaticamente le seguenti operazioni su `app/coordinator.py`:

1. Crea un backup in `app/coordinator.py.bak_pre_deep_research`
2. Aggiunge l'import: `from app.tools.deep_research import DEEP_RESEARCH_TOOL_DEF, DEEP_RESEARCH_TOOL_HANDLERS`
3. Registra il tool nella lista `TOOLS_DEFINITION` con `TOOLS_DEFINITION.append(DEEP_RESEARCH_TOOL_DEF)`
4. Aggiunge il dispatch nel metodo `_execute_tool`:
   ```python
   elif name in DEEP_RESEARCH_TOOL_HANDLERS:
       handler = DEEP_RESEARCH_TOOL_HANDLERS[name]
       return str(await handler(**args))
   ```
5. Aggiunge `lxml>=4.9.0` a `requirements.txt` se non presente

### Passo 3 — Ricostruisci il container Docker

```bash
docker-compose down
docker-compose build
docker-compose up -d
```

### Passo 4 — Verifica i log

```bash
docker-compose logs -f nik29
```

Cerca la riga: `INFO nik29.deep_research` per confermare che il tool è attivo.

---

## Utilizzo

Una volta installato, puoi chiedere a nik29 di eseguire ricerche approfondite:

> "Fai una ricerca approfondita sui migliori materassi memory foam del 2025"

> "Cerca informazioni dettagliate su come ottimizzare la SEO per un e-commerce, concentrandoti sulle strategie per il mercato italiano"

Il tool accetta tre parametri:

| Parametro | Tipo | Obbligatorio | Default | Descrizione |
|---|---|---|---|---|
| `query` | string | Sì | — | La query di ricerca |
| `num_results` | integer | No | 10 | Numero di pagine da leggere (max 20) |
| `focus` | string | No | — | Aspetto specifico su cui concentrare la sintesi |

---

## Architettura del tool

Il tool segue un pipeline in 4 fasi:

**Fase 1 — Brave Search.** Chiama l'API di Brave Search con la query fornita e recupera fino a 20 URL rilevanti. Usa la chiave API configurata nella variabile d'ambiente `BRAVE_API_KEY`.

**Fase 2 — Fetch parallelo.** Scarica tutte le pagine contemporaneamente usando `asyncio.gather()` con `aiohttp`. Per ogni pagina, imposta un timeout di 10 secondi. Se il fetch HTTP fallisce (timeout, errore HTTP, contenuto troppo corto), attiva automaticamente il fallback Playwright.

**Fase 3 — Fallback Playwright.** Per le pagine che richiedono JavaScript, prova prima il server Playwright su `localhost:5006` (il server avanzato del progetto), poi il `browser_manager` interno del coordinator (headless Chromium).

**Fase 4 — Estrazione testo.** `BeautifulSoup` rimuove script, stili, nav, footer, aside e altri elementi non pertinenti. Cerca il contenuto principale nell'ordine: `<article>`, `<main>`, `#content`, `.content`, `.post-content`, `.entry-content`, `<body>`. Tronca a **2000 parole** per pagina.

**Fase 5 — Sintesi GPT-4.1.** Invia tutto il testo estratto a GPT-4.1 (con fallback automatico a GPT-4o se il modello non è disponibile nell'endpoint configurato). Il prompt di sistema istruisce il modello a produrre una sintesi strutturata in Markdown con citazioni numeriche e sezione Fonti.

---

## Dipendenze

Il tool usa esclusivamente librerie già presenti nel container Docker del progetto:

| Libreria | Uso |
|---|---|
| `aiohttp` | Fetch HTTP parallelo |
| `beautifulsoup4` | Parsing HTML e estrazione testo |
| `playwright` | Fallback per pagine JavaScript-heavy |
| `lxml` | Parser HTML veloce per BeautifulSoup (aggiunto da patch) |

Le variabili d'ambiente utilizzate sono quelle già configurate nel progetto:

- `BRAVE_API_KEY`: chiave Brave Search (hardcoded come fallback se non impostata)
- `OPENAI_API_KEY`: chiave OpenAI
- `OPENAI_API_BASE`: endpoint OpenAI (default: `https://api.openai.com/v1`)

---

## Rollback

Se la patch causa problemi, ripristina il backup:

```bash
cp app/coordinator.py.bak_pre_deep_research app/coordinator.py
docker-compose build && docker-compose up -d
```
