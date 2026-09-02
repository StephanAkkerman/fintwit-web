"""Chart data extractor using StephanAkkerman/chart-extractor (YOLO + OCR).

Runs only after `app/ml/chart.py` has already classified an image as a
financial chart. It detects the on-chart title and price "pill", OCRs those
regions, and parses them into a structured symbol/exchange/timeframe/price/
session payload — used so a tweet whose text doesn't mention a ticker can
still be tied to the asset shown in its chart screenshot.

The model is loaded lazily on first use so importing this module never blocks
startup. All inference is offloaded to a thread pool via
``asyncio.to_thread`` so the FastAPI event loop stays non-blocking.
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_extractor = None  # lazily initialised


def _chart_extraction_enabled() -> bool:
    return os.getenv("CHART_EXTRACTION_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _load_extractor():
    from chart_extractor import ChartExtractor

    return ChartExtractor()


def _download_image(image_url: str):
    """Fetch *image_url* into a BGR array, as ``ChartExtractor.analyze`` expects."""
    import cv2
    import numpy as np
    import requests

    response = requests.get(image_url, timeout=10)
    response.raise_for_status()
    buffer = np.frombuffer(response.content, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Failed to decode image: {image_url}")
    return image


def _extract_sync(image_url: str) -> Optional[dict]:
    """Blocking extraction — run this inside a thread."""
    if not _chart_extraction_enabled():
        return None

    global _extractor
    if _extractor is None:
        logger.info("[chart-extractor] loading chart-extractor model…")
        _extractor = _load_extractor()
        logger.info("[chart-extractor] model ready")

    image = _download_image(image_url)
    result = _extractor.analyze(image)

    payload = {
        "symbol": result.symbol,
        "exchange": result.exchange,
        "timeframe": result.timeframe,
        "price": result.price,
        "session": result.session,
    }
    if not payload["symbol"] and payload["price"] is None:
        return None
    return payload


async def extract_chart_data(image_url: str) -> Optional[dict]:
    """Return structured chart info for *image_url*, or ``None`` if nothing useful was found."""
    if not _chart_extraction_enabled():
        return None

    try:
        return await asyncio.to_thread(_extract_sync, image_url)
    except Exception as exc:
        logger.warning("[chart-extractor] extraction failed for %s: %r", image_url, exc)
        return None
