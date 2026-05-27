from __future__ import annotations

from typing import Any

import pytest

from app.services.signa import SignaClient


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | list[Any]):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any] | list[Any]:
        return self._payload


def _assert_call(
    call: dict[str, Any],
    *,
    url: str,
    params: dict[str, Any] | None,
    auth_header: str,
) -> None:
    assert call["url"] == url
    assert call["params"] == params
    assert call["headers"]["Authorization"] == auth_header
    assert call["timeout"] == 15


def test_signa_client_covers_all_requested_endpoints(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"url": url, **kwargs})
        return _FakeResponse(200, {"ok": True, "url": url})

    monkeypatch.setattr("app.services.signa.requests.get", _fake_get)

    client = SignaClient(api_key="test-key")

    assert client.get_signal("aapl") is not None
    assert client.get_quote("aapl") is not None
    assert client.get_history("aapl") is not None
    assert client.get_enhanced_signal("aapl") is not None
    assert client.get_signal_index() is not None
    assert client.scan(signal="bullish", min_score=70) is not None
    assert client.get_me() is not None

    assert len(calls) == 7
    _assert_call(
        calls[0],
        url="https://app.getsigna.ai/api/v1/signal",
        params={"sym": "AAPL"},
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[1],
        url="https://app.getsigna.ai/api/v1/quote/AAPL",
        params=None,
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[2],
        url="https://app.getsigna.ai/api/v1/history/AAPL",
        params=None,
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[3],
        url="https://app.getsigna.ai/api/v1/enhanced-signal",
        params={"sym": "AAPL"},
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[4],
        url="https://app.getsigna.ai/api/v1/signal-index",
        params=None,
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[5],
        url="https://app.getsigna.ai/api/v1/scan",
        params={"signal": "bullish", "min_score": 70},
        auth_header="Bearer test-key",
    )
    _assert_call(
        calls[6],
        url="https://app.getsigna.ai/api/v1/me",
        params=None,
        auth_header="Bearer test-key",
    )


def test_signa_client_returns_none_for_empty_ticker():
    client = SignaClient(api_key="test-key")

    assert client.get_signal("") is None
    assert client.get_quote("   ") is None
    assert client.get_history("") is None
    assert client.get_enhanced_signal("") is None


def test_signa_client_returns_none_on_request_error(monkeypatch: pytest.MonkeyPatch):
    import requests

    def _raise_request_error(url: str, **kwargs: Any) -> _FakeResponse:
        raise requests.RequestException("network down")

    monkeypatch.setattr("app.services.signa.requests.get", _raise_request_error)

    client = SignaClient(api_key="test-key")
    assert client.get_me() is None
