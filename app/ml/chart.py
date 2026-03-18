import asyncio
from io import BytesIO
import logging
from typing import Optional

import httpx
import timm
import torch
from PIL import Image, UnidentifiedImageError
from timm.data import create_transform, resolve_data_config

logger = logging.getLogger(__name__)

class ChartClassifier:
    def __init__(self):
        self.model: Optional[timm.models.VisionTransformer] = None
        self.transform = None
        self.labels = None

    def load_model(self):
        """Load the model synchronously. Call this during app startup/lifespan."""
        if self.model is not None:
            return

        logger.info("Loading ChartClassifier model...")
        self.model = timm.create_model("hf_hub:StephanAkkerman/chart-recognizer", pretrained=True)
        self.model.eval()

        self.transform = create_transform(**resolve_data_config(self.model.pretrained_cfg, model=self.model))
        self.labels = self.model.pretrained_cfg["label_names"]
        logger.info("ChartClassifier model loaded successfully.")

    def classify_image_sync(self, image_input) -> Optional[str]:
        if self.model is None or self.transform is None or self.labels is None:
            raise RuntimeError("ChartClassifier model is not loaded. Call load_model() first.")

        try:
            if isinstance(image_input, bytes):
                image = Image.open(BytesIO(image_input)).convert("RGB")
            elif isinstance(image_input, str):
                image = Image.open(image_input).convert("RGB")
            elif isinstance(image_input, Image.Image):
                image = image_input.convert("RGB")
            else:
                raise ValueError("Unsupported image format")

            inputs = self.transform(image).unsqueeze(0)

            with torch.no_grad():
                outputs = self.model(inputs)

            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
            prob_dict = {label: prob.item() for label, prob in zip(self.labels, probabilities)}

            return max(prob_dict, key=prob_dict.get)
        except (ValueError, TypeError, OSError, UnidentifiedImageError, RuntimeError) as e:
            logger.error(f"Error classifying image: {e}")
            return None

    async def classify_image_async(self, image_input) -> Optional[str]:
        """Run the synchronous image classification in an executor. If image_input is a URL, fetch it async first."""
        if isinstance(image_input, str) and (image_input.startswith("http://") or image_input.startswith("https://")):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(image_input, timeout=10.0)
                    response.raise_for_status()
                    image_input = response.content
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.error(f"Error fetching image: {e}")
                return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.classify_image_sync, image_input)

# Create a singleton instance to be used across the app
chart_classifier = ChartClassifier()
