"""
vision_chat_patch.py — Analisi visiva diretta via GPT-4o
=========================================================
Chiamato da coordinator.py quando l'utente carica un'immagine in chat.
NON usa nik29-images né la porta 4002.
Usa direttamente l'API OpenAI (OPENAI_API_KEY dall'ambiente).
"""

import os
import base64
import logging
from pathlib import Path
from openai import AsyncOpenAI

logger = logging.getLogger("vision_chat_patch")

WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/data/workspace")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _resolve_image_path(file_info: dict) -> Path | None:
    """
    Trova il path locale dell'immagine a partire dal dict {name, url}.
    Prova nell'ordine:
      1. WORKSPACE_DIR / name
      2. Estrae il filename dall'URL (/files/<name>) e cerca in WORKSPACE_DIR
    """
    name = file_info.get("name", "")
    url = file_info.get("url", "")

    # Tentativo 1: diretto per nome
    if name:
        p = Path(WORKSPACE_DIR) / name
        if p.exists():
            return p

    # Tentativo 2: estrai filename dall'URL
    if "/files/" in url:
        filename = url.split("/files/")[-1]
        p = Path(WORKSPACE_DIR) / filename
        if p.exists():
            return p

    logger.warning(f"Immagine non trovata nel workspace: name={name!r} url={url!r}")
    return None


def _mime_type(ext: str) -> str:
    return {
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png":  "image/png",
        ".webp": "image/webp",
        ".gif":  "image/gif",
    }.get(ext.lower(), "image/jpeg")


async def analyze_image_with_context(
    client: AsyncOpenAI,
    image_path: str,
    user_text: str
) -> str:
    """
    Analizza un'immagine con GPT-4o e restituisce la risposta testuale.
    Funzione pubblica usabile anche da altri moduli.
    """
    path = Path(image_path)
    if not path.exists():
        return f"[Errore vision] File non trovato: {image_path}"

    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        mime = _mime_type(path.suffix)
        prompt = user_text.strip() or "Descrivi questa immagine in dettaglio."

        logger.info(f"GPT-4o vision: {path.name} ({mime}), prompt: {prompt[:60]!r}")

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500
        )
        return response.choices[0].message.content or "(nessuna risposta)"

    except Exception as e:
        logger.error(f"Errore GPT-4o vision: {e}")
        return f"[Errore vision] {e}"


async def process_images_in_message(
    client: AsyncOpenAI,
    user_message: str,
    uploaded_files: list
) -> str:
    """
    Intercetta le immagini tra i file caricati, le analizza con GPT-4o
    e arricchisce user_message con i risultati.
    Restituisce user_message invariato se non ci sono immagini.
    """
    if not uploaded_files:
        return user_message

    results = []
    for f in uploaded_files:
        name = f.get("name", "")
        if not name:
            continue
        ext = Path(name).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            continue

        img_path = _resolve_image_path(f)
        if img_path is None:
            results.append(f"\n[Immagine {name}: file non trovato nel workspace]")
            continue

        analysis = await analyze_image_with_context(client, str(img_path), user_message)
        results.append(f"\n[Analisi visiva GPT-4o — {name}]:\n{analysis}\n")

    if results:
        return user_message + "\n" + "".join(results)

    return user_message
