# Istruzioni per l'integrazione del Bot Telegram in nik29-coordinator

Ciao Nicola! Ho completato l'integrazione del bot Telegram per `nik29-coordinator`. Il bot è stato progettato per funzionare all'interno dello stesso container Docker del server FastAPI, in modo da mantenere l'infrastruttura semplice e leggera.

Ecco cosa è stato fatto:
1. **`app/telegram_bot.py`**: È stato creato il modulo del bot che riceve i messaggi e li inoltra all'endpoint `/chat` locale. Gestisce correttamente i messaggi lunghi (dividendoli se superano i 4096 caratteri) e mostra l'indicatore "sta scrivendo...".
2. **`app/startup.py`**: È stato creato un nuovo script di avvio che lancia in parallelo (usando `asyncio`) sia il server FastAPI (`uvicorn`) sia il bot Telegram.
3. **`Dockerfile`**: È stato aggiornato per avviare il container tramite `app.startup` anziché direttamente con `uvicorn`.
4. **`requirements.txt`**: È stata aggiunta la libreria `python-telegram-bot`.
5. **`.env.example`**: Sono state aggiunte le variabili necessarie per la configurazione.

---

## Come installare e avviare l'aggiornamento

Poiché hai limitate competenze informatiche, ho preparato una guida passo-passo molto semplice.

### Passo 1: Scoprire il tuo ID Telegram (Whitelist)
Per fare in modo che **solo tu** possa usare il bot, dobbiamo inserire il tuo "ID Telegram" (un numero univoco) nella configurazione.
1. Apri l'app Telegram sul tuo telefono o computer.
2. Cerca l'utente **@userinfobot** (o clicca su questo link se sei da PC: [https://t.me/userinfobot](https://t.me/userinfobot)).
3. Avvia la chat cliccando su **Avvia** (o scrivi `/start`).
4. Il bot ti risponderà con un messaggio contenente il tuo `Id`. Copia quel numero (ad esempio: `123456789`).

### Passo 2: Aggiornare il file `.env`
Nel server dove hai installato `nik29-coordinator`, apri il file `.env` (quello dove hai già inserito `OPENAI_API_KEY`) e aggiungi queste due righe in fondo:

```env
TELEGRAM_BOT_TOKEN=8885025198:AAGEt1xNIecdcWCUSgi3ncFjRntK_S9tnwg
TELEGRAM_ALLOWED_USER_ID=inserisci_qui_il_tuo_id_numerico
```
*(Sostituisci `inserisci_qui_il_tuo_id_numerico` con il numero che hai copiato al Passo 1).*

### Passo 3: Sostituire i file del progetto
Estrai il file ZIP che ti ho inviato e sovrascrivi i file del tuo progetto attuale. In particolare, assicurati di copiare:
- La cartella `app/` (che ora contiene `telegram_bot.py` e `startup.py`).
- Il file `Dockerfile` aggiornato.
- Il file `requirements.txt` aggiornato.

### Passo 4: Ricostruire e riavviare Docker
Apri il terminale nella cartella del progetto (dove si trova il file `docker-compose.yml`) ed esegui questo comando per ricostruire l'immagine Docker con le nuove dipendenze e riavviare il sistema:

```bash
docker compose up -d --build
```

### Passo 5: Testare il bot
1. Vai su Telegram e cerca il tuo bot (dovresti già conoscere l'username associato al token).
2. Scrivi `/start`. Il bot dovrebbe risponderti con: *"Ciao Nicola! 👋 Sono nik29, il tuo assistente personale."*
3. Scrivi un messaggio qualsiasi e verifica che il bot ti risponda (vedrai l'indicatore "sta scrivendo..." mentre elabora la risposta).
4. Prova a scrivere `/status` per verificare lo stato di salute del sistema.

---

## Funzionalità e limitazioni attuali
- **Messaggi di testo**: Pienamente supportati. Se la risposta di nik29 è molto lunga, il bot la dividerà automaticamente in più messaggi.
- **Sicurezza**: Qualsiasi utente diverso da te che proverà a scrivere al bot riceverà un messaggio di errore: *"⛔ Non sei autorizzato a usare questo bot."*
- **File, Foto e Audio**: Al momento il bot ti avviserà che queste funzioni non sono ancora supportate (verranno implementate in un futuro aggiornamento).

Se hai problemi durante l'installazione, fammi sapere!
