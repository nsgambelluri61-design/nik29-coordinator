"""
nik29-coordinator - Telegram Bot Integration
Modulo bot Telegram che si interfaccia con il coordinator via API interna.

Usa python-telegram-bot (v20+) in modalità polling.
Gira nello stesso container Docker del FastAPI app.
"""

import os
import json
import logging
import asyncio
from typing import Optional

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction, ParseMode

logger = logging.getLogger("telegram_bot")

# ============================================================
# CONFIGURAZIONE
# ============================================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS: list[int] = []

# Parsing degli user ID consentiti (supporta lista separata da virgola)
_raw_ids = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "")
if _raw_ids:
    for uid in _raw_ids.split(","):
        uid = uid.strip()
        if uid.isdigit():
            ALLOWED_USER_IDS.append(int(uid))

# URL interno del coordinator (stesso container)
COORDINATOR_URL = os.environ.get("COORDINATOR_INTERNAL_URL", "http://localhost:4001")

# Limite caratteri Telegram per messaggio
TELEGRAM_MAX_LENGTH = 4096


# ============================================================
# HELPERS
# ============================================================

def is_authorized(user_id: int) -> bool:
    """Verifica se l'utente è nella whitelist."""
    if not ALLOWED_USER_IDS:
        # Se nessun ID configurato, blocca tutti (sicurezza)
        return False
    return user_id in ALLOWED_USER_IDS


def split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """
    Divide un messaggio lungo in parti che rispettano il limite Telegram.
    Cerca di spezzare su newline o spazi per non tagliare a metà parola.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break

        # Cerca un punto di taglio naturale
        chunk = text[:max_length]
        # Prova a tagliare sull'ultimo newline
        split_pos = chunk.rfind("\n")
        if split_pos < max_length // 2:
            # Se il newline è troppo indietro, prova con lo spazio
            split_pos = chunk.rfind(" ")
        if split_pos < max_length // 2:
            # Fallback: taglia al limite
            split_pos = max_length

        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip()

    return parts


async def call_coordinator(message: str, session_id: str) -> str:
    """
    Chiama l'endpoint /chat del coordinator e raccoglie la risposta completa.
    L'endpoint restituisce SSE (Server-Sent Events), quindi leggiamo lo stream.
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{COORDINATOR_URL}/chat",
                json={
                    "message": message,
                    "conversation_id": session_id,
                },
                headers={"Accept": "text/event-stream"},
            ) as response:
                if response.status_code != 200:
                    return f"Errore dal coordinator: HTTP {response.status_code}"

                final_response = ""
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]  # Rimuovi "data: "
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")
                    content = event.get("content", "")

                    if event_type == "response":
                        final_response = content
                    elif event_type == "done":
                        break
                    elif event_type == "error":
                        return f"⚠️ Errore: {content}"

                return final_response or "Ho elaborato la richiesta ma non ho generato una risposta testuale."

        except httpx.TimeoutException:
            return "⏱️ Timeout: l'elaborazione sta richiedendo troppo tempo. Riprova tra poco."
        except httpx.ConnectError:
            return "❌ Errore di connessione al coordinator. Il servizio potrebbe essere in fase di avvio."
        except Exception as e:
            logger.error(f"Errore chiamata coordinator: {e}", exc_info=True)
            return f"❌ Errore imprevisto: {str(e)}"


# ============================================================
# HANDLERS
# ============================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /start."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    await update.message.reply_text(
        "Ciao Nicola! 👋 Sono nik29, il tuo assistente personale.\n\n"
        "Scrivimi qualsiasi cosa e ti aiuterò. Ecco i comandi disponibili:\n"
        "/start - Messaggio di benvenuto\n"
        "/status - Stato del sistema\n\n"
        "Scrivi pure in linguaggio naturale, capisco tutto!"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /status — chiama /health e riporta lo stato."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    await update.message.chat.send_action(ChatAction.TYPING)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{COORDINATOR_URL}/health")
            if resp.status_code == 200:
                data = resp.json()
                status_text = (
                    f"✅ *Sistema operativo*\n\n"
                    f"• Servizio: `{data.get('service', 'n/a')}`\n"
                    f"• Versione: `{data.get('version', 'n/a')}`\n"
                    f"• Connessioni attive: `{data.get('active_connections', 0)}`\n"
                    f"• Task in coda: `{data.get('pending_tasks', 0)}`"
                )
            else:
                status_text = f"⚠️ Health check ha risposto con HTTP {resp.status_code}"
        except Exception as e:
            status_text = f"❌ Impossibile contattare il coordinator: {str(e)}"

    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per messaggi di testo normali — inoltra al coordinator."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    user_message = update.message.text
    if not user_message or not user_message.strip():
        return

    user_id = update.effective_user.id
    # Usa user_id come session_id per mantenere contesto conversazione
    session_id = f"telegram_{user_id}"

    # Mostra "sta scrivendo..."
    await update.message.chat.send_action(ChatAction.TYPING)

    # Avvia un task per mantenere l'indicatore typing attivo durante l'elaborazione
    typing_active = True

    async def keep_typing():
        """Mantiene l'indicatore typing attivo ogni 4 secondi."""
        while typing_active:
            try:
                await update.message.chat.send_action(ChatAction.TYPING)
            except Exception:
                pass
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(keep_typing())

    try:
        # Chiama il coordinator
        response_text = await call_coordinator(user_message, session_id)
    finally:
        typing_active = False
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

    # Invia risposta (gestendo messaggi lunghi)
    if not response_text:
        response_text = "Ho ricevuto il messaggio ma non ho generato una risposta."

    parts = split_message(response_text)
    for part in parts:
        try:
            await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Se il Markdown non è valido, invia come testo semplice
            await update.message.reply_text(part)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per messaggi vocali — non ancora supportati."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    await update.message.reply_text(
        "🎤 I messaggi vocali non sono ancora supportati.\n"
        "Per ora scrivi il tuo messaggio come testo. "
        "Il supporto vocale arriverà in un prossimo aggiornamento!"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per foto — non ancora supportate."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    await update.message.reply_text(
        "📷 Le foto non sono ancora supportate.\n"
        "Per ora scrivi il tuo messaggio come testo. "
        "Il supporto immagini arriverà in un prossimo aggiornamento!"
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per documenti — non ancora supportati."""
    if not update.effective_user or not is_authorized(update.effective_user.id):
        await update.message.reply_text("⛔ Non sei autorizzato a usare questo bot.")
        return

    await update.message.reply_text(
        "📄 I documenti non sono ancora supportati.\n"
        "Per ora scrivi il tuo messaggio come testo. "
        "Il supporto documenti arriverà in un prossimo aggiornamento!"
    )


# ============================================================
# BOT LIFECYCLE
# ============================================================

async def start_telegram_bot():
    """
    Avvia il bot Telegram in modalità polling.
    Questa funzione è progettata per girare come task asyncio
    accanto a uvicorn nello stesso event loop.
    """
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN non configurato. Bot Telegram disabilitato.")
        return

    if not ALLOWED_USER_IDS:
        logger.warning("TELEGRAM_ALLOWED_USER_ID non configurato. Bot Telegram disabilitato per sicurezza.")
        return

    logger.info(f"Avvio bot Telegram (utenti autorizzati: {ALLOWED_USER_IDS})")

    # Crea l'applicazione bot
    application = Application.builder().token(BOT_TOKEN).build()

    # Registra handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Inizializza e avvia polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        drop_pending_updates=True,  # Ignora messaggi ricevuti mentre era offline
        allowed_updates=["message"],
    )

    logger.info("✅ Bot Telegram avviato con successo (polling mode)")

    # Mantieni il bot attivo
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Arresto bot Telegram...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot Telegram arrestato.")
