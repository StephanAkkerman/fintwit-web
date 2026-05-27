import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://app.getsigna.ai"
_DEFAULT_TIMEOUT_SECONDS = 15


def _normalize_ticker(ticker: str) -> str:
    return (ticker or "").strip().upper()


class SignaClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key or os.getenv("SIGNA_KEY")

        self.headers: dict[str, str] = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.warning("[signa] request failed endpoint=%s error=%r", endpoint, exc)
            return None
        except ValueError as exc:
            logger.warning(
                "[signa] non-json response endpoint=%s error=%r", endpoint, exc
            )
            return None

    def get_signal(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal?sym={ticker}"""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request("/api/v1/signal", params={"sym": symbol})

    def get_quote(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/quote/{ticker}"""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request(f"/api/v1/quote/{symbol}")

    def get_history(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/history/{ticker}"""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request(f"/api/v1/history/{symbol}")

    def get_enhanced_signal(self, ticker: str) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/enhanced-signal?sym={ticker}"""
        symbol = _normalize_ticker(ticker)
        if not symbol:
            return None
        return self._request("/api/v1/enhanced-signal", params={"sym": symbol})

    def get_signal_index(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/signal-index"""
        return self._request("/api/v1/signal-index")

    def scan(self, **filters: Any) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/scan with arbitrary screener filter query params."""
        clean_filters = {k: v for k, v in filters.items() if v is not None}
        return self._request("/api/v1/scan", params=clean_filters)

    def get_me(self) -> dict[str, Any] | list[Any] | None:
        """GET /api/v1/me"""
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
