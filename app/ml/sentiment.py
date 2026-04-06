"""Tweet sentiment classifier using StephanAkkerman/FinTwitBERT-sentiment.

The model is loaded once and reused. Inference is executed in a worker thread so
the async event loop remains responsive.
"""

from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger(__name__)
QUOTE_LINE_PATTERN = re.compile(r"^\s*>\s?(.*)$")

LABEL_TO_EMOJI = {
    "NEUTRAL": "🦆",
    "BULLISH": "🐂",
    "BEARISH": "🐻",
}

FALLBACK_ID_TO_LABEL = {
    0: "NEUTRAL",
    1: "BULLISH",
    2: "BEARISH",
}


def preprocess_text(tweet: str) -> str:
    """Match legacy bot preprocessing before sentiment classification."""
    text = re.sub(r"http\S+", "[URL]", tweet)
    text = re.sub(r"@\S+", "@USER", text)
    return text


def split_main_and_quoted_text(tweet: str) -> tuple[str | None, str | None]:
    """Split tweet text into author text and markdown-quoted text.

    Returns a `(main_text, quoted_text)` tuple where each value can be `None` if
    no content exists for that segment.
    """

    lines = tweet.splitlines()
    main_lines: list[str] = []
    quoted_lines: list[str] = []
    in_quote = False

    for line in lines:
        match = QUOTE_LINE_PATTERN.match(line)
        if match is not None:
            in_quote = True
            quoted_lines.append(match.group(1))
            continue

        if in_quote:
            # Keep trailing context that follows a quote line as part of the
            # quoted block to avoid mixing it back into the author's message.
            quoted_lines.append(line)
            continue

        main_lines.append(line)

    main_text = "\n".join(main_lines).strip() or None
    quoted_text = "\n".join(quoted_lines).strip() or None
    return main_text, quoted_text


class FinTwitSentiment:
    def __init__(
        self,
        model_name: str = "StephanAkkerman/FinTwitBERT-sentiment",
        cache_dir: str = "models/",
    ):
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._pipeline = None
        self._load_lock = asyncio.Lock()

    def _load_pipeline_sync(self):
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            pipeline,
        )

        model = AutoModelForSequenceClassification.from_pretrained(
            self._model_name,
            num_labels=3,
            id2label=FALLBACK_ID_TO_LABEL,
            label2id={v: k for k, v in FALLBACK_ID_TO_LABEL.items()},
            cache_dir=self._cache_dir,
        )
        model.config.problem_type = "single_label_classification"
        model.eval()

        tokenizer = AutoTokenizer.from_pretrained(
            self._model_name,
            cache_dir=self._cache_dir,
            use_fast=False,
        )

        return pipeline("text-classification", model=model, tokenizer=tokenizer)

    async def _ensure_pipeline(self) -> None:
        if self._pipeline is not None:
            return

        async with self._load_lock:
            if self._pipeline is not None:
                return

            logger.info("[sentiment] loading FinTwitBERT model...")
            self._pipeline = await asyncio.to_thread(self._load_pipeline_sync)
            logger.info("[sentiment] model ready")

    async def warmup(self) -> None:
        """Preload model at startup so inference later has no cold start."""
        await self._ensure_pipeline()

    def _normalize_label(self, raw_label: str) -> str:
        label = raw_label.upper()
        if label in LABEL_TO_EMOJI:
            return label

        if label.startswith("LABEL_"):
            try:
                idx = int(label.split("_", 1)[1])
            except ValueError:
                return "NEUTRAL"
            return FALLBACK_ID_TO_LABEL.get(idx, "NEUTRAL")

        return "NEUTRAL"

    def _classify_sync(self, text: str) -> dict[str, str | float]:
        # BERT supports up to 512 tokens; setting max_length avoids runtime warnings.
        result = self._pipeline(preprocess_text(text), truncation=True, max_length=512)[
            0
        ]
        label = self._normalize_label(str(result.get("label", "NEUTRAL")))
        score = float(result.get("score", 0.0))
        emoji = LABEL_TO_EMOJI.get(label, "🦆")
        return {
            "label": label,
            "emoji": emoji,
            "score": score,
        }

    async def classify_parts(
        self, text: str
    ) -> dict[str, dict[str, str | float] | None]:
        """Classify author text and quoted text separately."""
        if not text or not text.strip():
            return {"main": None, "quoted": None}

        await self._ensure_pipeline()
        main_text, quoted_text = split_main_and_quoted_text(text)

        main = (
            await asyncio.to_thread(self._classify_sync, main_text)
            if main_text
            else None
        )
        quoted = (
            await asyncio.to_thread(self._classify_sync, quoted_text)
            if quoted_text
            else None
        )
        return {"main": main, "quoted": quoted}

    async def classify(self, text: str) -> dict[str, str | float] | None:
        parts = await self.classify_parts(text)
        return parts["main"]
