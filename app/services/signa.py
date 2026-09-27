import asyncio
import logging
import os
import re
import time
from collections import deque
from typing import Any, Callable

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://app.getsigna.ai"
_DEFAULT_TIMEOUT_SECONDS = 15
_DEFAULT_CACHE_TTL_SECONDS = 60
_DEFAULT_PER_MINUTE_LIMIT = 60
_DEFAULT_PER_DAY_LIMIT = 1000


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


def has_signa_key() -> bool:
    """Whether a ``SIGNA_KEY`` is configured for the authenticated endpoints."""
    return bool(os.getenv("SIGNA_KEY"))


class SignaClient:
    """Minimal Signa REST client with local caching and quota guards.

    Notes
    -----
    - Responses are cached per endpoint + query params for `cache_ttl_seconds`.
    - Cache invalidates lazily on read once TTL has elapsed.
    - Outbound calls are blocked locally when minute/day quotas are exhausted.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
        per_minute_limit: int = _DEFAULT_PER_MINUTE_LIMIT,
        per_day_limit: int = _DEFAULT_PER_DAY_LIMIT,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.per_minute_limit = per_minute_limit
        self.per_day_limit = per_day_limit
        # Resolve the key lazily per request (see ``_resolve_api_key``) rather
        # than freezing it here: the module-level ``_default_client`` is built
        # at import time, which can run *before* ``load_dotenv`` populates the
        # environment, leaving a constructor-time ``os.getenv`` call empty.
        self._api_key_override = api_key
        self._time_fn = time_fn or time.time

        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, dict[str, Any] | list[Any]],
        ] = {}
        self._minute_requests: deque[float] = deque()
        self._day_requests: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _resolve_api_key(self) -> str | None:
        """Return the explicit override or the current ``SIGNA_KEY`` env value.

        Read lazily so a key loaded into the environment after this client was
        constructed (e.g. via ``load_dotenv``) is still picked up.
        """
        return self._api_key_override or os.getenv("SIGNA_KEY")

    @property
    def api_key(self) -> str | None:
        return self._resolve_api_key()

    @property
    def headers(self) -> dict[str, str]:
        key = self._resolve_api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    @staticmethod
    def _make_params_key(params: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
        if not params:
            return tuple()
        return tuple(sorted((str(key), str(value)) for key, value in params.items()))

    async def _get_cached(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | list[Any] | None:
        if self.cache_ttl_seconds <= 0:
            return None

        cache_key = (endpoint, self._make_params_key(params))
        now = self._time_fn()

        async with self._lock:
            item = self._cache.get(cache_key)
            if item is None:
                return None

            ts, payload = item
            if now - ts > self.cache_ttl_seconds:
                self._cache.pop(cache_key, None)
                return None

            return payload

    async def _set_cache(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
        payload: dict[str, Any] | list[Any],
    ) -> None:
        if self.cache_ttl_seconds <= 0:
            return

        cache_key = (endpoint, self._make_params_key(params))
        async with self._lock:
            self._cache[cache_key] = (self._time_fn(), payload)

    async def _consume_rate_budget(self) -> bool:
        now = self._time_fn()
        minute_cutoff = now - 60
        day_cutoff = now - 86400

        async with self._lock:
            while self._minute_requests and self._minute_requests[0] <= minute_cutoff:
                self._minute_requests.popleft()
            while self._day_requests and self._day_requests[0] <= day_cutoff:
                self._day_requests.popleft()

            if len(self._minute_requests) >= self.per_minute_limit:
                return False
            if len(self._day_requests) >= self.per_day_limit:
                return False

            self._minute_requests.append(now)
            self._day_requests.append(now)

        return True

    async def _request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        cached = await self._get_cached(endpoint, params)
        if cached is not None:
            return cached

        if not await self._consume_rate_budget():
            logger.warning(
                "[signa] local rate limit reached endpoint=%s minute_limit=%s day_limit=%s",
                endpoint,
                self.per_minute_limit,
                self.per_day_limit,
            )
            return None

        url = f"{self.base_url}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    url, headers=self.headers, params=params
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()

            if isinstance(payload, (dict, list)):
                await self._set_cache(endpoint, params, payload)
                return payload

            logger.warning("[signa] unexpected payload type endpoint=%s", endpoint)
            return None
        except aiohttp.ClientError as exc:
            logger.warning("[signa] request failed endpoint=%s error=%r", endpoint, exc)
            return None
        except (ValueError, asyncio.TimeoutError) as exc:
            logger.warning(
                "[signa] non-json or timed-out response endpoint=%s error=%r",
                endpoint,
                exc,
            )
            return None

    async def get_signal(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal?sym={ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe,
        timeframe_input, cached, engine, engine_coverage, signa, data, meta.

        Observed example (abridged):
        {
            "ok": True,
            "symbol": "AAPL",
            "timeframe": "1D",
            "cached": False,
            "engine": "v2",
            "signa": "Bullish",
            "data": {
                "score": 74,
                "trend": "up",
                "confidence": 0.81,
            },
            "meta": {
                "timestamp": "2026-05-...Z",
                "latency_ms": 120,
            },
        }
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return await self._request("/api/v1/signal", params={"sym": symbol})

    async def get_quote(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/quote/{ticker}.

        Observed response shape includes keys like: ok, symbol, cached, price,
        open, high, low, close, volume, change, changePercent, timestamp, meta.

        Observed example (abridged):
        {
            "ok": True,
            "symbol": "AAPL",
            "price": 214.08,
            "open": 212.10,
            "high": 215.50,
            "low": 211.90,
            "close": 214.08,
            "volume": 52344211,
            "change": 1.98,
            "changePercent": 0.93,
            "timestamp": "2026-05-...Z",
        }
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return await self._request(f"/api/v1/quote/{symbol}")

    async def get_history(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/history/{ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe, count,
        cached, candles, meta. candles items use ohlcv fields t/o/h/l/c/v.

        Observed example (abridged):
        {
            "ok": True,
            "symbol": "AAPL",
            "timeframe": "1D",
            "count": 5,
            "cached": True,
            "candles": [
                {"t": 1716163200, "o": 189.1, "h": 191.7, "l": 188.9, "c": 191.2, "v": 51234123},
                {"t": 1716249600, "o": 191.2, "h": 192.3, "l": 189.8, "c": 190.4, "v": 48911220},
            ],
        }
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return await self._request(f"/api/v1/history/{symbol}")

    async def get_enhanced_signal(
        self, ticker: str
    ) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/enhanced-signal?sym={ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe,
        cached, enhanced, signa, enhanced_score, trade, prediction_markets,
        news, quote, timestamp.

        Observed example (abridged):
        {
            "ok": True,
            "symbol": "AAPL",
            "timeframe": "1D",
            "enhanced": "Bullish",
            "signa": "Bullish",
            "enhanced_score": 82,
            "trade": {
                "entry": 213.4,
                "stop": 208.0,
                "target": 221.0,
            },
            "prediction_markets": [],
            "news": [],
            "quote": {"price": 214.08},
        }
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return await self._request("/api/v1/enhanced-signal", params={"sym": symbol})

    async def get_signal_index(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal-index.

        Observed response shape includes keys like: ok, cached, universe,
        symbolCount, coveredCount, uncoveredCount, timestamp, value,
        sentiment, components, topSignals, data_source, meta.

        Observed example (abridged):
        {
            "ok": True,
            "cached": True,
            "universe": "stocks",
            "symbolCount": 500,
            "coveredCount": 462,
            "value": 61,
            "sentiment": "risk-on",
            "components": {
                "momentum": 64,
                "breadth": 58,
                "volatility": 55,
            },
            "topSignals": ["NVDA", "AAPL", "MSFT"],
        }
        """
        return await self._request("/api/v1/signal-index")

    async def scan(self, **filters: Any) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/scan with screener query params.

        Working examples observed:
        - scan(sym="AAPL")
        - scan(direction="bullish", min_score=80, limit=10, sym="AAPL")

        Observed response shape includes keys: ok, results, meta.
        results entries include fields like symbol, score, tier, bias,
        confidence, stage, triggers, price, change24h, rsi.

        Observed example (abridged):
        {
            "ok": True,
            "results": [
                {
                    "symbol": "AAPL",
                    "score": 83,
                    "tier": "A",
                    "bias": "bullish",
                    "confidence": 0.84,
                    "stage": "continuation",
                    "triggers": ["breakout", "relative_strength"],
                    "price": 214.08,
                    "change24h": 0.93,
                    "rsi": 62.1,
                }
            ],
            "meta": {
                "count": 1,
                "filters": {"direction": "bullish", "min_score": 80, "sym": "AAPL"},
            },
        }
        """
        clean_filters = {k: v for k, v in filters.items() if v is not None}
        return await self._request("/api/v1/scan", params=clean_filters)

    async def get_me(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/me.

        Observed response shape includes keys: ok, user_id, plan, api, scopes,
        entitlements, meta. api includes daily/minute limits and usage counters.

        Observed example (abridged):
        {
            "ok": True,
            "user_id": "...",
            "plan": "pro",
            "api": {
                "calls_remaining": 1000,
                "daily_limit": 1000,
                "hourly_limit": 60,
                "rate_limit": "60/min, 1000/day",
            },
            "scopes": ["signal", "quote", "scan"],
            "entitlements": ["enhanced_signal"],
        }
        """
        return await self._request("/api/v1/me")

    async def get_analysis(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """Legacy helper retained for backwards compatibility."""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return await self._request("/api/v1/analysis", params={"ticker": symbol})

    async def get_best_trades(
        self, *, limit: int = 250, scored: bool = True
    ) -> dict[str, Any] | list[Any] | None:
        """GET /api/signals/run — the "best trades" ranked signals feed.

        Undocumented endpoint backing the getsigna.ai dashboard route
        ``/dashboard/best-trades``. Unlike the ``/api/v1/*`` endpoints it
        requires **no API key / no auth** — it is publicly accessible. Premium
        tier-3 signals are gated server-side (the response carries
        ``tier3_gated: true``) but tier 1/2 signals are returned in full.

        Parameters
        ----------
        limit : int
            Maximum number of signals to return (server honours this exactly).
        scored : bool
            When ``True`` the API returns the ranked ``signals`` array. When
            ``False`` it returns only a ``count`` with no signal payload, so the
            default of ``True`` is almost always what you want.

        Observed response shape:
        {
            "signals": [
                {
                    "id": "00e018a4-3eaa-4dca-8843-f229537b80cc",
                    "ticker": "SBUX",
                    "direction": "BULLISH",          # or "BEARISH"
                    "alert_tier": 2,                  # 1 or 2 (tier 3 gated)
                    "composite_score": 98,
                    "confidence": 0.58,
                    "model_count": 2,
                    "model_ids": ["bollinger-band", "low-vol-factor"],
                    "model_names": [],
                    "categories": [],
                    "category_diversity": 0,
                    "regime": "TRANSITIONAL",
                    "regime_multiplier": 1,
                    "suggested_size_pct": 0,
                    "conflict_detected": false,
                    "risks": [],
                    "reason": "Strong consensus: 100% bullish; ...",
                    "key_drivers": ["Strong consensus: 100% bullish", ...],
                    "grade": "A",                     # A, B, ...
                    "generated_at": "2026-06-03T19:06:04.375+00:00",
                }
            ],
            "count": 98,
            "tier3_gated": true,
        }
        """
        params = {"scored": "true" if scored else "false", "limit": int(limit)}
        return await self._request("/api/signals/run", params=params)

    async def get_feed(self, *, limit: int = 1500) -> dict[str, Any] | list[Any] | None:
        """GET /api/signals/feed — the raw, per-model *live* signals feed.

        Sibling of ``get_best_trades`` (``/api/signals/run``) and, like it,
        requires **no API key / no auth**. Where ``/run`` returns the nightly
        multi-model *consensus*, ``/feed`` returns every individual model's
        latest call, refreshed throughout the day (hence ``is_live`` / a poll
        timer on the frontend).

        Parameters
        ----------
        limit : int
            Maximum number of raw signals to return (server honours this).

        Observed response shape:
        {
            "signals": [
                {
                    "id": "66f21725-1010-45cf-9ec9-0b4729348425",
                    "ticker": "MNA",
                    "signal": "BUY",          # BUY/SELL/SHORT/AVOID/HOLD/WATCH
                    "model_id": "merger-arbitrage",
                    "model_name": "MergerArbitrageAgent",
                    "model_source": "Mitchell & Pulvino (2001) + ...",
                    "category": "fundamental",
                    "confidence": 0.78,        # 0-1
                    "reason": "Merger arbitrage: ...",
                    "entry_price": 36.3,
                    "stop_level": null,
                    "target_price": null,
                    "position_size_pct": 0.08,
                    "metadata": {...},
                    "is_live": true,
                    "created_at": "2026-06-05T04:03:07.287922+00:00",
                    "conflict_detected": false,
                    "grade": "A",              # may be null
                    "tier": 1,                 # may be null
                    "score": 98,               # may be null
                }
            ],
            "type": "raw",
            "count": 200,
            "date": "2026-06-05",
            "latest_signal_at": "2026-06-05T04:03:07.381466+00:00",
            "generated_at": "2026-06-05T07:13:59.341Z",
        }
        """
        params = {"limit": int(limit)}
        return await self._request("/api/signals/feed", params=params)


_default_client = SignaClient()


def _coerce_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# Mirrors the frontend ``classifyDirection`` (utils/directionColor.ts) so the
# live-feed colours match: BUY/LONG -> bullish, SELL/SHORT -> bearish, and
# AVOID/HOLD/WATCH (and anything else) fall through to non-directional.
_BULLISH_LABEL = re.compile(r"(bull|buy|\bup\b|\blong\b|positive)")
_BEARISH_LABEL = re.compile(r"(bear|sell|\bdown\b|\bshort\b|negative)")


def _classify_direction(label: Any) -> str | None:
    """Map a Signa signal label to ``"BULLISH"``/``"BEARISH"``.

    Returns ``None`` for non-directional labels (AVOID/HOLD/WATCH), which the
    live feed drops as noise.
    """
    text = label.strip().lower() if isinstance(label, str) else ""
    if not text:
        return None
    if _BULLISH_LABEL.search(text):
        return "BULLISH"
    if _BEARISH_LABEL.search(text):
        return "BEARISH"
    return None


def _normalize_confidence(value: Any) -> float | None:
    """Coerce Signa confidence to a 0–1 float.

    Signa reports confidence as a 0–100 integer (e.g. ``92``); the frontend
    renders it as ``confidence * 100``, so scale it down here.
    """
    confidence = _coerce_optional_float(value)
    if confidence is None:
        return None
    if confidence > 1:
        confidence = confidence / 100.0
    return confidence


async def get_signa_signal(ticker: str) -> dict[str, Any] | None:
    """Fetch and normalize the Signa signal for a single ticker.

    Mirrors ``get_tradingview_ta_summary``: returns a compact dict suitable for
    the frontend, or ``None`` when no usable signal is available.

    The ``/api/v1/signal`` payload carries the verdict in an ``engine`` block
    (the nightly multi-model consensus that matches the in-app Action Card),
    with an intraday ``data`` block as a fallback. The top-level ``signa`` key
    is a *nested object* (grade/conviction/action), not the verdict label.

    Observed shape (abridged)::

        {
            "symbol": "AAPL",
            "timeframe": "1d",
            "engine": {"direction": "BULLISH", "score": 98,
                       "confidence": 92, "grade": "A"},
            "data": {"direction": "WAIT", "bias": "bullish",
                     "confidence": 55, "stage": 2},
        }

    Returns
    -------
    dict or None
        ``{"source", "symbol", "signal", "score", "trend", "confidence",
        "grade", "timeframe", "website"}`` where ``signal`` is the verdict
        (e.g. ``"Bullish"``). ``None`` when the ticker is empty, the request
        fails, or the payload carries no verdict label.
    """
    symbol = _normalize_ticker(ticker)
    if not symbol:
        return None

    payload = await _default_client.get_signal(symbol)
    if not isinstance(payload, dict):
        return None

    engine = payload.get("engine")
    engine = engine if isinstance(engine, dict) else {}
    data = payload.get("data")
    data = data if isinstance(data, dict) else {}

    # Verdict: prefer the nightly engine consensus, fall back to intraday bias.
    label = engine.get("direction") or data.get("bias") or data.get("direction")
    if not isinstance(label, str) or not label.strip():
        return None

    score = _coerce_optional_float(engine.get("score"))
    if score is None:
        score = _coerce_optional_float(data.get("score"))

    confidence = _normalize_confidence(engine.get("confidence"))
    if confidence is None:
        confidence = _normalize_confidence(data.get("confidence"))

    return {
        "source": "signa",
        "symbol": str(payload.get("symbol") or symbol).upper(),
        # "BULLISH" -> "Bullish" so it reads like the TradingView TA verdicts.
        "signal": label.strip().title(),
        "score": score,
        "trend": data.get("bias") or engine.get("direction"),
        "confidence": confidence,
        "grade": engine.get("grade"),
        "timeframe": payload.get("timeframe"),
        "website": f"{_default_client.base_url}/?sym={symbol}",
    }


async def get_signa_best_trades(
    limit: int = 250, scored: bool = True
) -> list[dict[str, Any]]:
    """Fetch and normalize the Signa "best trades" ranked signals feed.

    Wraps :meth:`SignaClient.get_best_trades` and flattens each raw signal into
    a compact, frontend-friendly dict. Returns an empty list when the request
    fails or carries no usable signals (never ``None``).

    Returns
    -------
    list of dict
        Each entry: ``{"source", "symbol", "direction", "grade", "alert_tier",
        "composite_score", "confidence", "regime", "reason", "key_drivers",
        "model_ids", "generated_at", "website"}``.
    """
    payload = await _default_client.get_best_trades(limit=limit, scored=scored)
    if not isinstance(payload, dict):
        return []

    signals = payload.get("signals")
    if not isinstance(signals, list):
        return []

    results: list[dict[str, Any]] = []
    for item in signals:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_ticker(item.get("ticker"))
        if not symbol:
            continue

        direction = item.get("direction")
        key_drivers = item.get("key_drivers")
        model_ids = item.get("model_ids")
        categories = item.get("categories")

        results.append(
            {
                "source": "signa",
                "symbol": symbol,
                "direction": (
                    direction.upper() if isinstance(direction, str) else None
                ),
                "grade": item.get("grade"),
                "alert_tier": item.get("alert_tier"),
                "composite_score": _coerce_optional_float(item.get("composite_score")),
                "confidence": _coerce_optional_float(item.get("confidence")),
                "model_count": item.get("model_count"),
                "regime": item.get("regime"),
                "categories": categories if isinstance(categories, list) else [],
                "reason": item.get("reason"),
                "key_drivers": key_drivers if isinstance(key_drivers, list) else [],
                "model_ids": model_ids if isinstance(model_ids, list) else [],
                "generated_at": item.get("generated_at"),
                "website": f"{_default_client.base_url}/?sym={symbol}",
            }
        )
    return results


async def get_signa_live_feed(limit: int = 1500) -> list[dict[str, Any]]:
    """Fetch and normalize the Signa raw, per-model *live* signals feed.

    Wraps :meth:`SignaClient.get_feed` and flattens each raw signal into a
    compact, frontend-friendly dict. Only *directional* signals are kept —
    BUY/SELL/SHORT (anything :func:`_classify_direction` reads as
    bullish/bearish); non-directional AVOID/HOLD/WATCH entries are dropped as
    noise. Returns an empty list when the request fails or carries no usable
    signals (never ``None``).

    The list is returned unsorted; the frontend ranks it with the same
    comparator as the best-trades widget (score -> confidence -> tier).

    Returns
    -------
    list of dict
        Each entry: ``{"source", "id", "symbol", "signal", "direction",
        "model_id", "model_name", "model_source", "category", "confidence",
        "reason", "entry_price", "stop_level", "target_price",
        "position_size_pct", "grade", "tier", "score", "conflict_detected",
        "created_at", "website"}``.
    """
    payload = await _default_client.get_feed(limit=limit)
    if not isinstance(payload, dict):
        return []

    signals = payload.get("signals")
    if not isinstance(signals, list):
        return []

    results: list[dict[str, Any]] = []
    for item in signals:
        if not isinstance(item, dict):
            continue
        symbol = _normalize_ticker(item.get("ticker"))
        if not symbol:
            continue

        label = item.get("signal")
        direction = _classify_direction(label)
        if direction is None:
            # Drop non-directional noise (AVOID/HOLD/WATCH).
            continue

        results.append(
            {
                "source": "signa",
                "id": item.get("id"),
                "symbol": symbol,
                "signal": label.strip().upper() if isinstance(label, str) else None,
                "direction": direction,
                "model_id": item.get("model_id"),
                "model_name": item.get("model_name"),
                "model_source": item.get("model_source"),
                "category": item.get("category"),
                "confidence": _coerce_optional_float(item.get("confidence")),
                "reason": item.get("reason"),
                "entry_price": _coerce_optional_float(item.get("entry_price")),
                "stop_level": _coerce_optional_float(item.get("stop_level")),
                "target_price": _coerce_optional_float(item.get("target_price")),
                "position_size_pct": _coerce_optional_float(
                    item.get("position_size_pct")
                ),
                "grade": item.get("grade"),
                "tier": item.get("tier"),
                "score": _coerce_optional_float(item.get("score")),
                "conflict_detected": bool(item.get("conflict_detected")),
                "created_at": item.get("created_at"),
                "website": f"{_default_client.base_url}/?sym={symbol}",
            }
        )
    return results


async def signal_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_signal(ticker)


async def quote_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_quote(ticker)


async def history_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_history(ticker)


async def enhanced_signal_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_enhanced_signal(ticker)


async def signal_index_request() -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_signal_index()


async def scan_request(**filters: Any) -> dict[str, Any] | list[Any] | None:
    return await _default_client.scan(**filters)


async def me_request() -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_me()


async def analysis_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_analysis(ticker)


async def signals_run_request(
    limit: int = 250, scored: bool = True
) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_best_trades(limit=limit, scored=scored)


async def signals_feed_request(
    limit: int = 1500,
) -> dict[str, Any] | list[Any] | None:
    return await _default_client.get_feed(limit=limit)


if __name__ == "__main__":
    import asyncio

    async def main():
        trades = await get_signa_best_trades(limit=5)
        print(f"Best trades ({len(trades)}):")
        for trade in trades:
            print(
                f"  {trade['symbol']:<6} {trade['direction']:<8} "
                f"grade={trade['grade']} score={trade['composite_score']} "
                f"conf={trade['confidence']}"
            )

        feed = await get_signa_live_feed(limit=200)
        print(f"\nLive feed — directional only ({len(feed)}):")
        for sig in feed[:10]:
            print(
                f"  {sig['symbol']:<6} {str(sig['signal']):<6} {sig['direction']:<8} "
                f"score={sig['score']} conf={sig['confidence']} "
                f"model={sig['model_name']}"
            )

    asyncio.run(main())
