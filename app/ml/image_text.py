"""Screenshot text extraction via Tesseract OCR (pytesseract) — issue #88.

Runs on photo tweets that `app/ml/chart.py` did *not* classify as a
financial chart. Some posters (screenshots of options flow, etc.) carry
little or no tweet text of their own — the only signal is printed inside
the image — so this recovers any `$TICKER`/`#HASHTAG` tokens the screenshot
itself contains.

Off by default (`IMAGE_OCR_ENABLED`): the false-positive rate on real
screenshots hasn't been evaluated yet, so this ships as an opt-in the
maintainer can turn on and watch before it runs for everyone.

The model is loaded lazily on first use so importing this module never
blocks startup. Inference is offloaded to a thread pool via
``asyncio.to_thread`` so the FastAPI event loop stays non-blocking.
"""

import asyncio
import logging
import os
from io import BytesIO

logger = logging.getLogger(__name__)

_pytesseract = None  # lazily initialised


def _image_ocr_enabled() -> bool:
    return os.getenv("IMAGE_OCR_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _load_pytesseract():
    import pytesseract

    return pytesseract


def _download_image(image_url: str):
    import requests
    from PIL import Image

    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    return Image.open(BytesIO(response.content)).convert("RGB")


def _extract_sync(image_url: str) -> str:
    """Blocking OCR — run this inside a thread."""
    global _pytesseract
    if _pytesseract is None:
        logger.info("[image-text] loading pytesseract…")
        _pytesseract = _load_pytesseract()
        logger.info("[image-text] ready")

    image = _download_image(image_url)
    return _pytesseract.image_to_string(image).strip()


async def extract_image_text(image_url: str) -> str | None:
    """Return the OCR'd text of the image at *image_url*, or ``None``.

    ``None`` covers the feature being disabled, the OCR pass finding
    nothing, and any failure to fetch/decode/recognize the image — callers
    treat all three the same way (fall back to having no image text).
    """
    if not _image_ocr_enabled():
        return None

    try:
        text = await asyncio.to_thread(_extract_sync, image_url)
    except Exception as exc:
        logger.warning("[image-text] OCR failed for %s: %r", image_url, exc)
        return None

    return text or None
