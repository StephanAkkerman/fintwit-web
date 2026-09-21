"""Tweet sentiment classifier using StephanAkkerman/FinTwitBERT-sentiment.

The model is loaded once and reused. Inference is executed in a worker thread so
the async event loop remains responsive.

Scores are **signed by direction** — `+0.9` is confidently bullish, `-0.9`
confidently bearish, `0.0` neutral — because that is what every consumer
assumes: `mention_aggregator._score_to_label`, the `sentiment_score > 0.1` /
`< -0.1` splits in its SQL, and `trader_scoring._direction` all read the sign.
The magnitude is the model's confidence, so `abs(score)` is how strongly it
read the text either way.

Long text is split into segments and classified per segment rather than in one
truncated read, so a thesis that runs past 512 tokens is not judged on its
opening paragraph, and a tweet that is long one ticker and short another can
say so per ticker instead of giving both the same label.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Iterable, Sequence

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

#: Sentence and paragraph boundaries. Tweets are not clean enough prose for a
#: real sentence tokenizer to be worth the dependency; segments only need to be
#: small enough that one rarely holds two opposing calls.
SEGMENT_PATTERN = re.compile(r"(?<=[.!?])\s+|[\n;]+")

#: Shorter than this is not a claim about anything ("Edit:", "TL;DR").
MIN_SEGMENT_CHARS = 12

#: Mirrors the BULL/BEAR split used in `mention_aggregator` and
#: `trader_scoring`. Any single segment clears it: a 3-class argmax is never
#: less confident than 1/3, so a short tweet keeps the label it always had.
#: `frontend/src/utils/sentiment.ts`'s `labelFromScore` mirrors this constant —
#: update both sides if it ever changes.
SENTIMENT_THRESHOLD = 0.1


def signed_score(label: str, confidence: float) -> float:
    """Sign a model confidence by direction so scores can be averaged."""
    if label == "BULLISH":
        return float(confidence)
    if label == "BEARISH":
        return -float(confidence)
    return 0.0


def label_from_score(score: float) -> str:
    """Turn a signed score, or the mean of several, back into a label."""
    if score > SENTIMENT_THRESHOLD:
        return "BULLISH"
    if score < -SENTIMENT_THRESHOLD:
        return "BEARISH"
    return "NEUTRAL"


def split_segments(text: str) -> list[str]:
    """Split text into sentence-sized segments.

    A short tweet yields a single segment, which makes the segmented path
    identical to classifying the text as a whole.
    """
    segments = [
        segment.strip()
        for segment in SEGMENT_PATTERN.split(text or "")
        if len(segment.strip()) >= MIN_SEGMENT_CHARS
    ]
    if segments:
        return segments
    stripped = (text or "").strip()
    return [stripped] if stripped else []


def ticker_pattern(symbol: str) -> re.Pattern[str]:
    """Match a ticker's surface form, with or without a cashtag or hash.

    Short symbols are matched case-sensitively: a two-letter ticker is
    otherwise indistinguishable from an ordinary word ("IT", "ON", "SO").
    """
    flags = re.IGNORECASE if len(symbol) >= 4 else 0
    return re.compile(rf"[$#]?\b{re.escape(symbol)}\b", flags)


def attribute_segments(
    segments: Sequence[str], tickers: Iterable[str]
) -> dict[str, list[int]]:
    """Work out which segments speak about which ticker.

    A segment naming a single ticker is evidence about that ticker; one naming
    several ("$NVDA over $INTC any day") says nothing about either in
    particular, so it is only used for a ticker with no segment of its own.

    :return: Ticker to the indices of the segments it is scored from. A ticker
        that appears in no segment is absent.
    """
    symbols = [str(t).strip().upper() for t in tickers if str(t).strip()]

    named: dict[int, set[str]] = {}
    for symbol in symbols:
        pattern = ticker_pattern(symbol)
        for index, segment in enumerate(segments):
            if pattern.search(segment):
                named.setdefault(index, set()).add(symbol)

    attributed: dict[str, list[int]] = {}
    for symbol in symbols:
        owned = sorted(index for index, names in named.items() if symbol in names)
        exclusive = [index for index in owned if len(named[index]) == 1]
        chosen = exclusive or owned
        if chosen:
            attributed[symbol] = chosen
    return attributed


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

    def _score_segments_sync(self, segments: Sequence[str]) -> list[float]:
        """Classify every segment in one batched pass, returning signed scores."""
        if not segments:
            return []

        # BERT supports up to 512 tokens; setting max_length avoids runtime
        # warnings. Segmenting means the overflow is read rather than dropped.
        results = self._pipeline(
            [preprocess_text(segment) for segment in segments],
            truncation=True,
            max_length=512,
        )
        return [
            signed_score(
                self._normalize_label(str(result.get("label", "NEUTRAL"))),
                float(result.get("score", 0.0)),
            )
            for result in results
        ]

    @staticmethod
    def _as_verdict(score: float) -> dict[str, str | float]:
        label = label_from_score(score)
        return {
            "label": label,
            "emoji": LABEL_TO_EMOJI.get(label, "🦆"),
            "score": round(score, 4),
        }

    def _classify_sync(
        self, text: str, tickers: Sequence[str] | None = None
    ) -> tuple[dict[str, str | float], dict[str, float]]:
        """Classify one block of text, and each ticker named inside it.

        :return: ``(verdict, per_ticker)`` where *verdict* describes the block
            as a whole and *per_ticker* maps a ticker to its own signed score.
            Only tickers whose score differs from the block's appear.
        """
        segments = split_segments(text)
        if not segments:
            return self._as_verdict(0.0), {}

        scores = self._score_segments_sync(segments)
        overall = sum(scores) / len(scores)

        per_ticker: dict[str, float] = {}
        for symbol, indices in attribute_segments(segments, tickers or ()).items():
            mean = round(sum(scores[i] for i in indices) / len(indices), 4)
            # Storing a value identical to the block's own would only pad the
            # payload; `sentiment_for` falls back to it anyway.
            if mean != round(overall, 4):
                per_ticker[symbol] = mean

        return self._as_verdict(overall), per_ticker

    async def classify_parts(
        self, text: str, tickers: Sequence[str] | None = None
    ) -> dict[str, dict | None]:
        """Classify author text and quoted text separately.

        :param tickers: Tickers the tweet mentions. When given, the ``tickers``
            key of the result maps each to its own signed score, taken from the
            author's own segments — a quoted tweet is someone else's opinion,
            so it never attributes.
        """
        if not text or not text.strip():
            return {"main": None, "quoted": None, "tickers": {}}

        await self._ensure_pipeline()
        main_text, quoted_text = split_main_and_quoted_text(text)

        main: dict[str, str | float] | None = None
        per_ticker: dict[str, float] = {}
        if main_text:
            main, per_ticker = await asyncio.to_thread(
                self._classify_sync, main_text, tickers
            )

        quoted: dict[str, str | float] | None = None
        if quoted_text:
            quoted, _ = await asyncio.to_thread(self._classify_sync, quoted_text)

        return {"main": main, "quoted": quoted, "tickers": per_ticker}

    async def classify(
        self, text: str, tickers: Sequence[str] | None = None
    ) -> dict[str, str | float] | None:
        parts = await self.classify_parts(text, tickers)
        return parts["main"]
