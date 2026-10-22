import pytest

import app.services.technical_indicators_service as svc
from app.services.technical_indicators_service import (
    compute_from_history,
    get_indicators,
    normalize_symbol,
    parse_row,
    rating_label,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


@pytest.fixture(autouse=True)
def history(monkeypatch):
    """Daily bars per Yahoo symbol for the fallback; none unless a test adds."""
    series: dict[str, list[dict]] = {}
    calls: list[str] = []

    async def get_price_series(symbol, range_key):
        calls.append(symbol)
        return series.get(symbol, [])

    monkeypatch.setattr(svc, "get_price_series", get_price_series)
    return series, calls


def _bars(closes: list[float], volume: float = 1000.0) -> list[dict]:
    return [
        {"t": f"d{i}", "close": c, "high": c + 1, "low": c - 1, "volume": volume}
        for i, c in enumerate(closes)
    ]


def _row(ticker: str, **overrides) -> dict:
    """A scanner row in ``_COLUMNS`` order; EWZ's readings by default."""
    name = ticker.split(":", 1)[1]
    fields = {
        "name": name,
        "exchange": ticker.split(":", 1)[0],
        "type": "fund",
        "subtype": "etf",
        "is_primary": True,
        "close": 42.94,
        "RSI": 66.62,
        "RSI|240": 63.72,
        "MACD.macd": 1.4086,
        "MACD.signal": 1.3928,
        "MACD.macd[1]": 1.3800,
        "MACD.signal[1]": 1.3900,
        "SMA20": 40.40,
        "SMA50": 37.95,
        "SMA200": 37.04,
        "SMA50[1]": 37.00,
        "SMA200[1]": 37.01,
        "ATR": 1.0213,
        "ADX": 30.89,
        "ADX+DI": 32.0,
        "ADX-DI": 12.0,
        "volume": 60_000_000,
        "average_volume_30d_calc": 40_000_000,
        "Recommend.All": 0.60,
        "Recommend.MA": 0.93,
        "Recommend.Other": 0.27,
        "Recommend.All|240": 0.42,
    }
    fields.update(overrides)
    return {"s": ticker, "d": [fields[c] for c in svc._COLUMNS]}


def test_parse_row_derives_states_and_crosses():
    ind = parse_row(_row("AMEX:EWZ"), "EWZ")

    assert ind["tv_symbol"] == "AMEX:EWZ"
    assert ind["type"] == "etf"
    assert ind["rsi"] == {"value": 66.6, "state": "neutral", "four_h": 63.7}
    assert ind["macd"]["above_signal"] is True
    assert ind["macd"]["cross"] == "bullish"  # was below its signal a bar ago
    ma = ind["moving_averages"]
    assert ma["price_vs_sma200_percent"] == pytest.approx(15.93, abs=0.01)
    assert ma["sma50_vs_sma200"] == "golden_cross"
    assert ma["cross_today"] == "golden_cross"
    assert ind["atr"] == {"value": 1.0213, "percent_of_price": 2.38}
    assert ind["adx"] == {"value": 30.9, "trend_strength": "strong", "direction": "up"}
    assert ind["volume"]["vs_avg_30d"] == 1.5
    assert ind["rating"] == {
        "one_d": "Strong Buy",
        "four_h": "Buy",
        "moving_averages": "Strong Buy",
        "oscillators": "Buy",
    }
    assert ind["signals"] == [
        "macd_bullish_cross",
        "golden_cross",
        "above_sma200",
        "strong_uptrend",
        "heavy_volume",
    ]


def test_parse_row_tolerates_missing_values():
    ind = parse_row(
        _row("NASDAQ:NEW", RSI=25.0, SMA200=None, ATR=None, ADX=None), "NEW"
    )

    assert ind["rsi"]["state"] == "oversold"
    assert ind["moving_averages"]["price_vs_sma200_percent"] is None
    assert ind["moving_averages"]["sma50_vs_sma200"] is None
    assert ind["atr"]["percent_of_price"] is None
    assert ind["adx"]["trend_strength"] is None
    assert ind["signals"][0] == "rsi_oversold"
    assert parse_row(_row("NASDAQ:X", close=None), "X") is None
    assert parse_row({"s": "NASDAQ:X", "d": [1, 2]}, "X") is None


def test_rating_label_and_normalize_symbol():
    assert [rating_label(v) for v in (0.6, 0.1, 0.0, -0.3, -0.9, None)] == [
        "Strong Buy",
        "Buy",
        "Neutral",
        "Sell",
        "Strong Sell",
        None,
    ]
    assert normalize_symbol("$brk-b", "stock") == "BRK.B"
    assert normalize_symbol("AMEX:EWZ", "etf") == "EWZ"
    assert normalize_symbol("BTC-USD", "crypto") == "BTC"
    assert normalize_symbol("ethusdt", "crypto") == "ETH"
    assert normalize_symbol("USDT", "crypto") == "USDT"


async def test_us_lookup_prefers_the_primary_listing(monkeypatch):
    calls = []

    async def scan(session, market, payload):
        calls.append((market, payload))
        return [
            _row("OTC:BRK.B", is_primary=False, volume=10),
            _row("NYSE:BRK.B", is_primary=True, volume=5),
            # No primary flag on either: the listed one beats busier OTC.
            _row("OTC:NOW", is_primary=False, volume=900),
            _row("NYSE:NOW", is_primary=False, volume=500),
            _row("AMEX:EWZ"),
        ]

    monkeypatch.setattr(svc, "_scan", scan)
    result = await get_indicators(["BRK-B", "ewz", "NOPE", "NOW"], "stock")
    again = await get_indicators(["EWZ"], "etf")

    assert result["BRK-B"]["tv_symbol"] == "NYSE:BRK.B"
    assert result["EWZ"]["symbol"] == "EWZ"
    assert result["NOPE"] is None
    assert result["NOW"]["tv_symbol"] == "NYSE:NOW"
    assert again["EWZ"] == result["EWZ"]
    assert len(calls) == 1  # the second call came from the cache
    market, payload = calls[0]
    assert market == "america"
    assert payload["filter"][0]["right"] == ["BRK.B", "EWZ", "NOPE", "NOW"]


async def test_crypto_lookup_takes_the_first_known_pair(monkeypatch):
    async def scan(session, market, payload):
        assert market == "crypto"
        assert payload["symbols"]["tickers"][:2] == [
            "BINANCE:BTCUSDT",
            "COINBASE:BTCUSD",
        ]
        return [_row("COINBASE:SOLUSD"), _row("BINANCE:BTCUSDT")]

    monkeypatch.setattr(svc, "_scan", scan)
    result = await get_indicators(["BTC-USD", "SOL", "NOPE"], "crypto")

    assert result["BTC-USD"]["tv_symbol"] == "BINANCE:BTCUSDT"
    assert result["SOL"]["tv_symbol"] == "COINBASE:SOLUSD"
    assert result["NOPE"] is None


def test_compute_from_history():
    # Falls for 150 days, then rises for 100: above every average, RSI
    # pinned high, and the 50-day crossed the 200-day on the last bar or
    # earlier.
    closes = [300.0 - i for i in range(150)] + [151.0 + 2 * i for i in range(100)]
    ind = compute_from_history(_bars(closes), "XYZ")

    assert ind["source"] == "price_history"
    assert ind["tv_symbol"] is None
    assert ind["price"] == 349.0
    assert ind["rsi"]["value"] == 100.0
    assert ind["rsi"]["state"] == "overbought"
    assert ind["rsi"]["four_h"] is None
    assert ind["macd"]["above_signal"] is True
    ma = ind["moving_averages"]
    assert ma["sma20"] == pytest.approx(sum(closes[-20:]) / 20, abs=1e-4)
    assert ma["sma200"] == pytest.approx(sum(closes[-200:]) / 200, abs=1e-4)
    assert ma["price_vs_sma50_percent"] > 0
    # A 2-point daily rise plus the 1-point wick: true range is 3.
    assert ind["atr"]["value"] == pytest.approx(3.0, abs=0.01)
    assert ind["adx"]["direction"] == "up"
    assert ind["volume"]["vs_avg_30d"] == 1.0
    assert ind["rating"] == {
        "one_d": None,
        "four_h": None,
        "moving_averages": None,
        "oscillators": None,
    }
    assert compute_from_history(_bars(closes[:30]), "XYZ") is None


async def test_falls_back_to_price_history(monkeypatch, history):
    series, calls = history
    series["BRK-B"] = _bars([100.0 + i for i in range(60)])
    series["ETH-USD"] = _bars([100.0 + i for i in range(60)])

    async def throttled(session, market, payload):
        return None

    monkeypatch.setattr(svc, "_scan", throttled)
    stocks = await get_indicators(["BRK.B", "NOPE"])
    coins = await get_indicators(["ETH"], "crypto")
    again = await get_indicators(["BRK.B"])

    assert stocks["BRK.B"]["source"] == "price_history"
    assert stocks["BRK.B"]["symbol"] == "BRK.B"
    assert stocks["BRK.B"]["moving_averages"]["sma200"] is None  # too short
    assert stocks["NOPE"] is None
    assert coins["ETH"]["price"] == 159.0
    assert again == {"BRK.B": stocks["BRK.B"]}
    # The hit was cached; the miss is retried.
    assert calls == ["BRK-B", "NOPE", "ETH-USD"]


async def test_failed_scans_are_not_cached(monkeypatch):
    responses = [None, [_row("AMEX:EWZ")]]

    async def scan(session, market, payload):
        return responses.pop(0)

    monkeypatch.setattr(svc, "_scan", scan)

    assert await get_indicators(["EWZ"]) == {"EWZ": None}
    assert (await get_indicators(["EWZ"]))["EWZ"]["tv_symbol"] == "AMEX:EWZ"
    assert await get_indicators(["EUR"], "forex") == {"EUR": None}
