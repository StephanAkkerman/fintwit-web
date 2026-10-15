"""Option-contract recognizer using StephanAkkerman/options-recognizer-gliner2-base.

A GLiNER2 LoRA adapter fine-tuned to pull option-contract details out of
tweets (issue #64): ``$AAPL 350 C 11/06/2026 $1.2M 4.37avg`` becomes a ticker,
strike, option type, expiry, premium and per-contract price. Training code and
benchmarks live in https://github.com/StephanAkkerman/options-recognizer-model.

The adapter repo ships a ``recognizer_config.json`` naming its base model,
entity descriptions, threshold and word splitter, so everything needed to load
it comes from the Hub. The model is loaded once and inference runs in a worker
thread so the event loop stays responsive.

A tweet counts as an options tweet when it names a call or put together with
at least one other detail of the contract. A quote tweet (or retweet) of an
options tweet counts too: the quoted text is recognized separately and either
part qualifying is enough.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Iterable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "StephanAkkerman/options-recognizer-gliner2-base"

#: Labels the adapter was trained on, in the order a contract is usually written.
LABELS = ("ticker", "strike", "option_type", "expiry", "premium", "price")


def options_ner_enabled() -> bool:
    return os.getenv("OPTIONS_NER_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class AlnumBoundarySplitter:
    """GLiNER2 word splitter that also breaks between letters and digits.

    Copied from ``src/core/spans.py`` of the model repo (``alnum-v2``). The
    adapter was trained with it, so ``1.58avg``, ``11/20exp`` and ``375C`` are
    split into word-aligned spans; with GLiNER2's stock splitter accuracy drops
    sharply. Dates and numbers with separators stay whole.
    """

    _PATTERN = re.compile(
        r"""(?:https?://[^\s]+|www\.[^\s]+)
        |[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}
        |@[a-z0-9_]+
        |[^\W\d_]+(?:[-_][^\W\d_]+)*
        |\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\d,.]\d)
        |\d+(?:[.,]\d+)*
        |\S""",
        re.VERBOSE | re.IGNORECASE,
    )

    def __call__(self, text, lower=True):
        for m in self._PATTERN.finditer(text):
            token = m.group()
            yield (token.lower() if lower else token), m.start(), m.end()


#: Splitter names the model repo writes into ``recognizer_config.json``.
SUPPORTED_SPLITTERS = {"alnum-v2": AlnumBoundarySplitter}

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")
_SCALE_RE = re.compile(r"(k|m|b|thousand|million|billion|mil|mm)\b", re.IGNORECASE)
_SCALES = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mm": 1e6,
    "mil": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
}


def parse_number(text: str | None) -> float | None:
    """First number in *text*: ``"$1,300"`` → 1300.0, ``".15"`` → 0.15."""
    match = _NUMBER_RE.search(text or "")
    if match is None:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def parse_premium(text: str | None) -> float | None:
    """Dollar size of a trade: ``"$1.2M"`` → 1_200_000.0, ``"993K"`` → 993_000.0."""
    value = parse_number(text)
    if value is None:
        return None
    number_end = _NUMBER_RE.search(text).end()
    scale = _SCALE_RE.match(text[number_end:].lstrip())
    if scale is not None:
        value *= _SCALES[scale.group(1).lower()]
    return value


_RIGHT_RE = re.compile(r"^(?:\d+(?:\.\d+)?)?\s*(C|P|CALLS?|PUTS?)$")


def normalize_right(text: str | None) -> str | None:
    """``"C"``, ``"calls"`` or ``"350P"`` → CALL/PUT; anything else → None.

    Only the call/put spellings themselves count: a looser prefix check let the
    model's stray spans through ("CASHES" read as a call, issue #216).
    """
    match = _RIGHT_RE.match((text or "").strip().upper())
    if match is None:
        return None
    return "CALL" if match.group(1).startswith("C") else "PUT"


def _normalize_ticker(text: str) -> str:
    return text.strip().lstrip("$#").upper()


def _spans(entities: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ``extract_entities`` output into spans sorted by position.

    Accepts both the ``include_spans`` form (dicts with text/start/confidence)
    and plain strings, which carry no position and sort by label order.
    """
    spans: list[dict[str, Any]] = []
    for label in LABELS:
        for order, item in enumerate(entities.get(label) or []):
            if isinstance(item, dict):
                text = str(item.get("text", ""))
                start = item.get("start")
                confidence = item.get("confidence")
            else:
                text, start, confidence = str(item), None, None
            if not text.strip():
                continue
            spans.append(
                {
                    "label": label,
                    "text": text,
                    "start": start if isinstance(start, int) else order,
                    "confidence": (
                        float(confidence) if confidence is not None else None
                    ),
                }
            )
    spans.sort(key=lambda s: s["start"])
    return spans


def group_contracts(spans: Iterable[dict[str, Any]], source: str) -> list[dict]:
    """Group positional spans into contracts.

    A contract starts at a ticker, or whenever a detail repeats (a second
    strike means a second contract), so ``$AAPL 350C 11/06 $TSLA 300P 12/18``
    yields two. Details written before the first ticker belong to the first
    contract. Contracts without a call/put are dropped.
    """
    contracts: list[dict[str, Any]] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if current:
            contracts.append(dict(current))
            current.clear()

    for span in spans:
        label = span["label"]
        if label in current:
            flush()
        current[label] = span["text"]
    flush()

    result = []
    for raw in contracts:
        right = normalize_right(raw.get("option_type"))
        if right is None:
            continue
        result.append(
            {
                "symbol": _normalize_ticker(raw["ticker"]) if "ticker" in raw else "",
                "right": right,
                "strike": parse_number(raw.get("strike")),
                "expiry": raw.get("expiry"),
                "notional_usd": parse_premium(raw.get("premium")),
                "price": parse_number(raw.get("price")),
                "source": source,
            }
        )
    return result


def _confidence(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def is_options_part(spans: list[dict[str, Any]]) -> bool:
    """A call/put plus at least one other contract detail."""
    labels = {
        s["label"]
        for s in spans
        if s["label"] != "option_type" or normalize_right(s["text"]) is not None
    }
    return "option_type" in labels and len(labels) >= 2


def build_options_result(
    main_entities: dict[str, Any] | None,
    quoted_entities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn recognized entities into ``is_options_tweet`` + ``options_context``.

    The shape matches :func:`app.runtime.options_intent.classify_options_intent`
    so storage, the API and the frontend need no special case.
    """
    main_spans = _spans(main_entities or {})
    quoted_spans = _spans(quoted_entities or {})
    main_is_options = is_options_part(main_spans)
    quoted_is_options = is_options_part(quoted_spans)
    is_options = main_is_options or quoted_is_options

    contracts = []
    if main_is_options:
        contracts += group_contracts(main_spans, "model")
    if quoted_is_options:
        contracts += group_contracts(quoted_spans, "model_quoted")

    deciding = [
        s
        for spans, ok in (
            (main_spans, main_is_options),
            (quoted_spans, quoted_is_options),
        )
        if ok
        for s in spans
    ]
    right_confidences = [
        s["confidence"]
        for s in deciding
        if s["label"] == "option_type" and s["confidence"] is not None
    ]
    score = round(max(right_confidences), 4) if right_confidences else 1.0
    if not is_options:
        score = 0.0

    rights = {c["right"] for c in contracts}
    if rights == {"CALL"}:
        side = "CALL"
    elif rights == {"PUT"}:
        side = "PUT"
    elif rights:
        side = "MIXED"
    else:
        side = "UNKNOWN"

    entities: dict[str, list[str]] = {}
    for span in deciding:
        entities.setdefault(span["label"], []).append(span["text"])

    context = {
        "classification": "OPTIONS" if is_options else "SPOT_OR_OTHER",
        "score": score,
        "confidence": _confidence(score) if is_options else "low",
        "side": side,
        "contract_count": len(contracts),
        "contracts": contracts,
        "keyword_hits": [],
        "cashtags": sorted(
            {_normalize_ticker(t) for t in entities.get("ticker", []) if t.strip()}
        ),
        "entities": entities,
        "from_quote": quoted_is_options and not main_is_options,
        "source": "model",
    }
    return {"is_options_tweet": is_options, "options_context": context}


class OptionsRecognizer:
    def __init__(self, model_name: str | None = None, cache_dir: str = "models/"):
        self._model_name = model_name or os.getenv("OPTIONS_NER_MODEL", DEFAULT_MODEL)
        self._cache_dir = cache_dir
        self._model = None
        self._labels: dict[str, str] = {}
        self._threshold = 0.5
        self._load_lock = asyncio.Lock()

    def _load_sync(self):
        from gliner2 import AutoExtractor
        from huggingface_hub import snapshot_download

        adapter_dir = snapshot_download(self._model_name, cache_dir=self._cache_dir)
        with open(
            os.path.join(adapter_dir, "recognizer_config.json"), encoding="utf-8"
        ) as f:
            cfg = json.load(f)

        splitter_name = cfg.get("word_splitter", "alnum-v2")
        splitter_cls = SUPPORTED_SPLITTERS.get(splitter_name)
        if splitter_cls is None:
            raise RuntimeError(
                f"{self._model_name} needs word splitter {splitter_name!r}, "
                f"which this app does not implement"
            )

        model = AutoExtractor.from_pretrained(cfg["base_model"], map_location="cpu")
        model.load_adapter(adapter_dir)
        model.set_word_splitter(splitter_cls())
        model.eval()

        self._labels = cfg.get("entity_descriptions") or {k: k for k in LABELS}
        self._threshold = float(cfg.get("threshold", 0.5))
        return model

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is not None:
                return
            logger.info("[options-ner] loading %s...", self._model_name)
            self._model = await asyncio.to_thread(self._load_sync)
            logger.info("[options-ner] model ready")

    async def warmup(self) -> None:
        """Preload the model at startup so inference later has no cold start."""
        await self._ensure_model()

    def _extract_sync(self, text: str) -> dict[str, Any]:
        result = self._model.extract_entities(
            text,
            self._labels,
            threshold=self._threshold,
            include_confidence=True,
            include_spans=True,
        )
        return (result or {}).get("entities") or {}

    async def extract(self, text: str | None) -> dict[str, Any]:
        """Raw entities for one block of text, keyed by label."""
        if not text or not text.strip():
            return {}
        await self._ensure_model()
        return await asyncio.to_thread(self._extract_sync, text)

    async def recognize(
        self, text: str | None, quoted_text: str | None = None
    ) -> dict[str, Any]:
        """Classify a tweet, and the tweet it quotes, as options or not."""
        main = await self.extract(text)
        quoted = await self.extract(quoted_text)
        return build_options_result(main, quoted)
