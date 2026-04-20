"""Chart image classifier using StephanAkkerman/chart-recognizer (timm/PyTorch).

The model is loaded lazily on first use so that importing this module never
blocks startup.  All inference is offloaded to a thread pool via
``asyncio.to_thread`` so the FastAPI event loop stays non-blocking.
"""

import asyncio
import logging
import os
from io import BytesIO
from typing import Union

logger = logging.getLogger(__name__)

_pipeline = None  # lazily initialised


def _chart_enabled() -> bool:
    return os.getenv("CHART_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _load_pipeline():
    """Load model + transforms once; returns the CustomImagePipeline instance."""
    import timm
    import torch
    from PIL import Image
    from timm.data import create_transform, resolve_data_config

    class _Pipeline:
        def __init__(self, model, transform, labels):
            self.model = model
            self.transform = transform
            self.labels = labels

        def __call__(self, image: Union[str, "Image.Image"]) -> dict:
            import requests

            if isinstance(image, str):
                if image.startswith("http://") or image.startswith("https://"):
                    response = requests.get(image, timeout=10)
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content)).convert("RGB")
                else:
                    image = Image.open(image).convert("RGB")
            elif isinstance(image, Image.Image):
                image = image.convert("RGB")
            else:
                raise ValueError(f"Unsupported image type: {type(image)}")

            inputs = self.transform(image).unsqueeze(0)
            with torch.no_grad():
                outputs = self.model(inputs)
            probs = torch.nn.functional.softmax(outputs[0], dim=0)
            return {label: prob.item() for label, prob in zip(self.labels, probs)}

    model = timm.create_model(
        "hf_hub:StephanAkkerman/chart-recognizer", pretrained=True
    )
    model.eval()
    transform = create_transform(
        **resolve_data_config(model.pretrained_cfg, model=model)
    )
    labels = model.pretrained_cfg["label_names"]
    return _Pipeline(model=model, transform=transform, labels=labels)


def _classify_sync(image_url: str) -> str:
    """Blocking classification — run this inside a thread."""
    if not _chart_enabled():
        return "not_chart"

    global _pipeline
    if _pipeline is None:
        logger.info("[chart] loading chart-recognizer model…")
        _pipeline = _load_pipeline()
        logger.info("[chart] model ready")

    probs = _pipeline(image_url)
    label = max(probs, key=probs.get)
    logger.debug("[chart] %s → %s (%.2f)", image_url, label, probs[label])
    return label


async def is_chart(image_url: str) -> bool:
    """Return True if the image at *image_url* is classified as a financial chart."""
    if not _chart_enabled():
        return False

    label = await asyncio.to_thread(_classify_sync, image_url)
    return label == "chart"
