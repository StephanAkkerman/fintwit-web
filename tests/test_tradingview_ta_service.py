from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import app.services.tradingview_ta_service as ta


def _rate_limit_exc() -> Exception:
    return Exception(
        "Can't access TradingView's API. HTTP status code: 429. "
        "Check for invalid symbol, exchange, or indicators."
    )


# ---------------------------------------------------------------------------
# _is_rate_limited
# ---------------------------------------------------------------------------


def test_is_rate_limited_detects_429():
    assert ta._is_rate_limited(_rate_limit_exc()) is True


def test_is_rate_limited_ignores_other_errors():
    assert ta._is_rate_limited(Exception("HTTP status code: 500")) is False
    assert ta._is_rate_limited(ValueError("invalid symbol")) is False


# ---------------------------------------------------------------------------
# _get_analysis_with_backoff
# ---------------------------------------------------------------------------


def test_backoff_returns_immediately_on_success():
    handler = MagicMock()
    handler.get_analysis.return_value = "OK"
    sleep = MagicMock()

    result = ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    assert result == "OK"
    handler.get_analysis.assert_called_once()
    sleep.assert_not_called()


def test_backoff_retries_then_succeeds():
    handler = MagicMock()
    handler.get_analysis.side_effect = [_rate_limit_exc(), "OK"]
    sleep = MagicMock()

    result = ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    assert result == "OK"
    assert handler.get_analysis.call_count == 2
    # One backoff between the two attempts, at the base delay.
    sleep.assert_called_once_with(ta._RATE_LIMIT_BASE_DELAY_SECONDS)


def test_backoff_exhausts_retries_and_raises_rate_limited():
    handler = MagicMock()
    handler.get_analysis.side_effect = _rate_limit_exc()
    sleep = MagicMock()

    with pytest.raises(ta._RateLimitedError):
        ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    assert handler.get_analysis.call_count == ta._RATE_LIMIT_MAX_ATTEMPTS
    # Sleeps happen between attempts, so one fewer than the attempt count.
    assert sleep.call_count == ta._RATE_LIMIT_MAX_ATTEMPTS - 1


def test_backoff_uses_exponential_delays():
    handler = MagicMock()
    handler.get_analysis.side_effect = _rate_limit_exc()
    sleep = MagicMock()

    with pytest.raises(ta._RateLimitedError):
        ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    base = ta._RATE_LIMIT_BASE_DELAY_SECONDS
    expected = [((base * 2**i),) for i in range(ta._RATE_LIMIT_MAX_ATTEMPTS - 1)]
    actual = [call.args for call in sleep.call_args_list]
    assert actual == expected


def test_backoff_propagates_non_rate_limit_errors_without_sleeping():
    handler = MagicMock()
    handler.get_analysis.side_effect = Exception("HTTP status code: 500")
    sleep = MagicMock()

    with pytest.raises(Exception, match="500"):
        ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    handler.get_analysis.assert_called_once()
    sleep.assert_not_called()


def test_backoff_logs_warning_on_rate_limit(caplog):
    handler = MagicMock()
    handler.get_analysis.side_effect = [_rate_limit_exc(), "OK"]
    sleep = MagicMock()

    with caplog.at_level("WARNING"):
        ta._get_analysis_with_backoff(handler, "AAPL", sleep=sleep)

    messages = [r.getMessage() for r in caplog.records]
    assert any("rate limit hit on AAPL" in m and "backing off" in m for m in messages)


def test_pick_best_row_prefers_the_exact_name():
    from app.services.tradingview_ta_service import _pick_best_row

    rows = [
        {"symbol": "NASDAQ:EWZS", "type": "fund", "volume": 2_600_000},
        {"symbol": "NASDAQ:NEWZ", "type": "fund", "volume": 7_000},
        {"symbol": "AMEX:EWZ", "type": "fund", "volume": 63_000_000},
    ]
    assert _pick_best_row(rows, "etf", "EWZ")["symbol"] == "AMEX:EWZ"
    assert _pick_best_row(rows[::-1], "stock", "EWZS")["symbol"] == "NASDAQ:EWZS"


def test_pick_best_row_prefers_a_listed_exchange_over_otc():
    from app.services.tradingview_ta_service import _pick_best_row

    rows = [
        {"symbol": "OTC:NOW", "type": "stock", "volume": 70_000},
        {"symbol": "NYSE:NOW", "type": "stock", "volume": 6_600_000},
    ]
    assert _pick_best_row(rows, "stock", "NOW")["symbol"] == "NYSE:NOW"


def test_resolve_prefers_the_exact_us_primary_listing(monkeypatch):
    from unittest.mock import MagicMock

    import app.services.tradingview_ta_service as svc

    resp = MagicMock()
    resp.json.return_value = {
        "data": [
            {"s": "OTC:NOW", "d": ["NOW", "OTC", "stock", False, 900_000]},
            {"s": "NYSE:NOW", "d": ["NOW", "NYSE", "stock", True, 6_600_000]},
        ]
    }
    post = MagicMock(return_value=resp)
    monkeypatch.setattr(svc.requests, "post", post)

    context = svc._resolve_symbol_context("NOW", "stock")

    assert context["exchange"] == "NYSE"
    assert context["symbol"] == "NOW"
    assert post.call_args.kwargs["json"]["filter"][0]["right"] == "NOW"


def test_resolve_falls_back_to_the_search_when_the_scanner_fails(monkeypatch):
    from unittest.mock import MagicMock

    import app.services.tradingview_ta_service as svc

    monkeypatch.setattr(svc.requests, "post", MagicMock(side_effect=OSError("down")))
    markets = MagicMock()
    markets.scrape.return_value = {
        "data": [
            {"symbol": "OTC:NOWVF", "type": "stock", "volume": 70_000},
            {"symbol": "NYSE:NOW", "type": "stock", "volume": 6_600_000},
        ]
    }
    monkeypatch.setattr(svc, "SymbolMarkets", MagicMock(return_value=markets))

    assert svc._resolve_symbol_context("NOW", "stock")["exchange"] == "NYSE"
    # Crypto never asks the US scanner.
    svc._resolve_symbol_context("BTC", "crypto")
    assert svc.requests.post.call_count == 1
