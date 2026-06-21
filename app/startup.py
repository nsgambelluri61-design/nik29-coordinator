"""
nik29-coordinator - Startup Script
Avvia uvicorn (FastAPI) e il bot Telegram nello stesso event loop asyncio.
"""

import asyncio
import logging
import signal
import sys

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("startup")


async def main():
    """Avvia FastAPI (uvicorn) e Telegram bot in parallelo."""

    # Import qui per evitare circular imports
    from app.telegram_bot import start_telegram_bot

    # Configura uvicorn come server asincrono
    config = uvicorn.Config(
        "app.main:app",
        host="0.0.0.0",
        port=4001,
        ws_ping_interval=30,
        ws_ping_timeout=60,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Crea i task
    uvicorn_task = asyncio.create_task(server.serve())
    telegram_task = asyncio.create_task(start_telegram_bot())

    # Gestisci shutdown graceful
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Segnale di arresto ricevuto...")
        shutdown_event.set()
        uvicorn_task.cancel()
        telegram_task.cancel()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    # Attendi che uno dei due task termini (o che arrivi un segnale)
    done, pending = await asyncio.wait(
        [uvicorn_task, telegram_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Se uno è terminato inaspettatamente, logga e ferma l'altro
    for task in done:
        if task.exception():
            logger.error(f"Task terminato con errore: {task.exception()}")

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    logger.info("Shutdown completato.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrotto da tastiera.")
        sys.exit(0)
