import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://app.getsigna.ai"
_DEFAULT_TIMEOUT_SECONDS = 15
_DEFAULT_CACHE_TTL_SECONDS = 60
_DEFAULT_PER_MINUTE_LIMIT = 60
_DEFAULT_PER_DAY_LIMIT = 1000


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


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
        self.api_key = api_key or os.getenv("SIGNA_KEY")
        self._time_fn = time_fn or time.time

        self.headers: dict[str, str] = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, dict[str, Any] | list[Any]],
        ] = {}
        self._minute_requests: deque[float] = deque()
        self._day_requests: deque[float] = deque()
        self._lock = threading.Lock()

    @staticmethod
    def _make_params_key(params: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
        if not params:
            return tuple()
        return tuple(sorted((str(key), str(value)) for key, value in params.items()))

    def _get_cached(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any] | list[Any] | None:
        if self.cache_ttl_seconds <= 0:
            return None

        cache_key = (endpoint, self._make_params_key(params))
        now = self._time_fn()

        with self._lock:
            item = self._cache.get(cache_key)
            if item is None:
                return None

            ts, payload = item
            if now - ts > self.cache_ttl_seconds:
                self._cache.pop(cache_key, None)
                return None

            return payload

    def _set_cache(
        self,
        endpoint: str,
        params: dict[str, Any] | None,
        payload: dict[str, Any] | list[Any],
    ) -> None:
        if self.cache_ttl_seconds <= 0:
            return

        cache_key = (endpoint, self._make_params_key(params))
        with self._lock:
            self._cache[cache_key] = (self._time_fn(), payload)

    def _consume_rate_budget(self) -> bool:
        now = self._time_fn()
        minute_cutoff = now - 60
        day_cutoff = now - 86400

        with self._lock:
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

    def _request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        cached = self._get_cached(endpoint, params)
        if cached is not None:
            return cached

        if not self._consume_rate_budget():
            logger.warning(
                "[signa] local rate limit reached endpoint=%s minute_limit=%s day_limit=%s",
                endpoint,
                self.per_minute_limit,
                self.per_day_limit,
            )
            return None

        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, (dict, list)):
                self._set_cache(endpoint, params, payload)
                return payload

            logger.warning("[signa] unexpected payload type endpoint=%s", endpoint)
            return None
        except requests.RequestException as exc:
            logger.warning("[signa] request failed endpoint=%s error=%r", endpoint, exc)
            return None
        except ValueError as exc:
            logger.warning(
                "[signa] non-json response endpoint=%s error=%r", endpoint, exc
            )
            return None

    def get_signal(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal?sym={ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe,
        timeframe_input, cached, engine, engine_coverage, signa, data, meta.
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request("/api/v1/signal", params={"sym": symbol})

    def get_quote(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/quote/{ticker}.

        Observed response shape includes keys like: ok, symbol, cached, price,
        open, high, low, close, volume, change, changePercent, timestamp, meta.
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request(f"/api/v1/quote/{symbol}")

    def get_history(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/history/{ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe, count,
        cached, candles, meta. candles items use ohlcv fields t/o/h/l/c/v.
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request(f"/api/v1/history/{symbol}")

    def get_enhanced_signal(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/enhanced-signal?sym={ticker}.

        Observed response shape includes keys like: ok, symbol, timeframe,
        cached, enhanced, signa, enhanced_score, trade, prediction_markets,
        news, quote, timestamp.
        """
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request("/api/v1/enhanced-signal", params={"sym": symbol})

    def get_signal_index(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal-index.

        Observed response shape includes keys like: ok, cached, universe,
        symbolCount, coveredCount, uncoveredCount, timestamp, value,
        sentiment, components, topSignals, data_source, meta.
        """
        return self._request("/api/v1/signal-index")

    def scan(self, **filters: Any) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/scan with screener query params.

        Working examples observed:
        - scan(sym="AAPL")
        - scan(direction="bullish", min_score=80, limit=10, sym="AAPL")

        Observed response shape includes keys: ok, results, meta.
        results entries include fields like symbol, score, tier, bias,
        confidence, stage, triggers, price, change24h, rsi.
        """
        clean_filters = {k: v for k, v in filters.items() if v is not None}
        return self._request("/api/v1/scan", params=clean_filters)

    def get_me(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/me.

        Observed response shape includes keys: ok, user_id, plan, api, scopes,
        entitlements, meta. api includes daily/minute limits and usage counters.
        """
        return self._request("/api/v1/me")

    def get_analysis(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """Legacy helper retained for backwards compatibility."""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request("/api/v1/analysis", params={"ticker": symbol})


_default_client = SignaClient()


def signal_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return _default_client.get_signal(ticker)


def quote_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return _default_client.get_quote(ticker)


def history_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return _default_client.get_history(ticker)


def enhanced_signal_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return _default_client.get_enhanced_signal(ticker)


def signal_index_request() -> dict[str, Any] | list[Any] | None:
    return _default_client.get_signal_index()


def scan_request(**filters: Any) -> dict[str, Any] | list[Any] | None:
    return _default_client.scan(**filters)


def me_request() -> dict[str, Any] | list[Any] | None:
    return _default_client.get_me()


def analysis_request(ticker: str) -> dict[str, Any] | list[Any] | None:
    return _default_client.get_analysis(ticker)
