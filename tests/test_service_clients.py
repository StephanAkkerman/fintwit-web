"""Parse-level tests for the thin external service clients.

These modules sat between 14% and 25% coverage — they are the layer where an
upstream schema change breaks the app silently, and the only place the shape of
each third-party payload is written down. Every response here is a trimmed
recording of the real upstream shape.

`httpx.MockTransport` is used rather than patching the client method, so the
genuine request/response path runs, including `raise_for_status`.
"""

import httpx
import pytest

from app.services import (
    binance_service,
    cmc,
    coin360_service,
    fear_greed_service,
    stock_fear_greed_service,
    unusual_whales,
)

pytestmark = pytest.mark.asyncio

# Bound before any test patches httpx.AsyncClient, so the factory below builds a
# real client instead of calling itself.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client(handler) -> httpx.AsyncClient:
    return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))


def _responds(payload, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def _patch_internal_client(monkeypatch, module, handler) -> None:
    """Redirect a module that builds its own AsyncClient at call time."""

    def factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler))

    # These modules construct their client inside the call, with no seam to
    # inject through, so the module attribute is the only place to intercept.
    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


# ---------------------------------------------------------------------------
# alternative.me Fear & Greed
# ---------------------------------------------------------------------------

_FNG = {
    "data": [
        {"value": "72", "value_classification": "Greed"},
        {"value": "60", "value_classification": "Greed"},
    ]
}


async def test_fear_greed_parses_value_and_rising_change(monkeypatch):
    _patch_internal_client(monkeypatch, fear_greed_service, _responds(_FNG))

    result = await fear_greed_service.get_feargreed()

    assert result == {"value": 72, "change": "+20.0% 📈", "status": "Greed"}


@pytest.mark.parametrize(
    ("today", "yesterday", "expected"),
    [("40", "80", "-50.0% 📉"), ("50", "50", "0.0% ➖")],
)
async def test_fear_greed_renders_falling_and_flat_change(
    monkeypatch, today, yesterday, expected
):
    payload = {
        "data": [
            {"value": today, "value_classification": "Fear"},
            {"value": yesterday, "value_classification": "Fear"},
        ]
    }
    _patch_internal_client(monkeypatch, fear_greed_service, _responds(payload))

    result = await fear_greed_service.get_feargreed()

    assert result["change"] == expected


async def test_fear_greed_returns_none_without_two_readings(monkeypatch):
    payload = {"data": [{"value": "72", "value_classification": "Greed"}]}
    _patch_internal_client(monkeypatch, fear_greed_service, _responds(payload))

    assert await fear_greed_service.get_feargreed() is None


async def test_fear_greed_returns_none_on_http_error(monkeypatch):
    _patch_internal_client(monkeypatch, fear_greed_service, _responds({}, status=503))

    assert await fear_greed_service.get_feargreed() is None


async def test_fear_greed_survives_a_zero_baseline(monkeypatch):
    """A zero yesterday would divide by zero; the client must absorb it."""
    payload = {
        "data": [
            {"value": "10", "value_classification": "Fear"},
            {"value": "0", "value_classification": "Extreme Fear"},
        ]
    }
    _patch_internal_client(monkeypatch, fear_greed_service, _responds(payload))

    assert await fear_greed_service.get_feargreed() is None


# ---------------------------------------------------------------------------
# CoinMarketCap trending
# ---------------------------------------------------------------------------

_CMC = {
    "data": {
        "cryptoTopSearchRanks": [
            {
                "name": "Bitcoin",
                "symbol": "BTC",
                "slug": "bitcoin",
                "priceChange": {
                    "price": 65000.5,
                    "priceChange24h": 2.5,
                    "volume24h": 1234.0,
                },
            },
            {"name": "NoSlug", "symbol": "NOS", "priceChange": {}},
        ]
    }
}


async def test_cmc_maps_fields_and_builds_website(monkeypatch):
    _patch_internal_client(monkeypatch, cmc, _responds(_CMC))

    results = await cmc.get_trending_crypto()

    assert results[0] == {
        "name": "Bitcoin",
        "symbol": "BTC",
        "slug": "bitcoin",
        "price": 65000.5,
        "change_24h": 2.5,
        "volume_24h": 1234.0,
        "website": "https://coinmarketcap.com/currencies/bitcoin",
    }


async def test_cmc_leaves_website_unset_without_a_slug(monkeypatch):
    _patch_internal_client(monkeypatch, cmc, _responds(_CMC))

    results = await cmc.get_trending_crypto()

    assert results[1]["website"] is None
    assert results[1]["price"] is None


async def test_cmc_returns_none_for_an_unexpected_shape(monkeypatch):
    _patch_internal_client(monkeypatch, cmc, _responds({"data": {}}))

    assert await cmc.get_trending_crypto() is None


async def test_cmc_returns_none_on_http_error(monkeypatch):
    _patch_internal_client(monkeypatch, cmc, _responds({}, status=500))

    assert await cmc.get_trending_crypto() is None


# ---------------------------------------------------------------------------
# Binance 24h movers
# ---------------------------------------------------------------------------


def _ticker(symbol: str, change: str, price: str = "10.0", volume: str = "5.0") -> dict:
    return {
        "symbol": symbol,
        "priceChangePercent": change,
        "weightedAvgPrice": price,
        "volume": volume,
    }


async def test_binance_ranks_gainers_and_losers():
    payload = [
        _ticker("BTCUSDT", "5.5"),
        _ticker("ETHUSDT", "-2.5"),
        _ticker("DOGEUSDT", "10.0"),
    ]

    async with _client(_responds(payload)) as client:
        result = await binance_service.get_gainers_losers(client)

    assert [item["symbol"] for item in result["gainers"]] == ["DOGE", "BTC", "ETH"]
    # Losers are returned most-negative first.
    assert [item["symbol"] for item in result["losers"]] == ["ETH", "BTC", "DOGE"]
    assert result["gainers"][0]["website"] == "https://www.binance.com/en/price/DOGE"


async def test_binance_ignores_non_usdt_pairs():
    payload = [_ticker("BTCUSDT", "1.0"), _ticker("ETHBTC", "9.9")]

    async with _client(_responds(payload)) as client:
        result = await binance_service.get_gainers_losers(client)

    assert [item["symbol"] for item in result["gainers"]] == ["BTC"]


async def test_binance_skips_rows_it_cannot_parse():
    payload = [
        _ticker("BTCUSDT", "1.0"),
        {"symbol": "BADUSDT", "priceChangePercent": "not-a-number"},
    ]

    async with _client(_responds(payload)) as client:
        result = await binance_service.get_gainers_losers(client)

    assert [item["symbol"] for item in result["gainers"]] == ["BTC"]


async def test_binance_returns_none_when_nothing_is_usable():
    async with _client(_responds([_ticker("ETHBTC", "1.0")])) as client:
        assert await binance_service.get_gainers_losers(client) is None


async def test_binance_returns_none_for_a_non_list_response():
    async with _client(_responds({"msg": "rate limited"})) as client:
        assert await binance_service.get_gainers_losers(client) is None


async def test_binance_returns_none_on_http_error():
    async with _client(_responds([], status=418)) as client:
        assert await binance_service.get_gainers_losers(client) is None


# ---------------------------------------------------------------------------
# Stock Fear & Greed (feargreedmeter.com)
#
# _FEARGREEDMETER is a trimmed recording of the real api2.mmeter.app/data/summary
# response (score under payload["fgi"]["latest"]["now"]). The other payloads in
# this block are best-effort guesses at alternative shapes predating that
# recording (see stock_fear_greed_service's module docstring) and only pin the
# parser's tolerant behavior, not a verified upstream contract.
# ---------------------------------------------------------------------------

_FEARGREEDMETER = {
    "fgi": {
        "latest": {
            "now": 37,
            "one_month_ago": 60,
            "one_week_ago": 30,
            "one_year_ago": 51,
            "previous_close": 36,
            "date": "2026-09-25",
        },
        "last_update": "2026-09-25T23:59:59",
    },
}


@pytest.fixture(autouse=True)
def _reset_stock_fear_greed_cache():
    stock_fear_greed_service._reset_cache_for_tests()
    yield
    stock_fear_greed_service._reset_cache_for_tests()


async def test_stock_fear_greed_parses_the_real_feargreedmeter_payload():
    async with _client(_responds(_FEARGREEDMETER)) as client:
        result = await stock_fear_greed_service.get_stock_feargreed(client)

    assert result == {"value": 37, "status": "Fear", "change": "+2.78% 📈"}


async def test_stock_fear_greed_parses_a_flat_payload():
    payload = {"score": 54, "rating": "Neutral", "previous_close": 50}

    async with _client(_responds(payload)) as client:
        result = await stock_fear_greed_service.get_stock_feargreed(client)

    assert result == {"value": 54, "status": "Neutral", "change": "+8.0% 📈"}


async def test_stock_fear_greed_parses_a_nested_cnn_style_payload():
    payload = {"fear_and_greed": {"value": 30, "rating": "Fear"}}

    async with _client(_responds(payload)) as client:
        result = await stock_fear_greed_service.get_stock_feargreed(client)

    assert result == {"value": 30, "status": "Fear", "change": None}


async def test_stock_fear_greed_derives_a_label_when_none_is_provided():
    payload = {"score": 82}

    async with _client(_responds(payload)) as client:
        result = await stock_fear_greed_service.get_stock_feargreed(client)

    assert result == {"value": 82, "status": "Extreme Greed", "change": None}


async def test_stock_fear_greed_returns_none_for_an_unexpected_shape():
    payload = {"unrelated": "data"}

    async with _client(_responds(payload)) as client:
        assert await stock_fear_greed_service.get_stock_feargreed(client) is None


async def test_stock_fear_greed_returns_none_on_http_error():
    async with _client(_responds({}, status=503)) as client:
        assert await stock_fear_greed_service.get_stock_feargreed(client) is None


async def test_stock_fear_greed_falls_back_to_a_stale_cache_on_a_later_failure():
    stale = {"value": 40, "status": "Fear", "change": None}
    stock_fear_greed_service._cache = (0.0, stale)  # far past the TTL

    async with _client(_responds({}, status=500)) as client:
        result = await stock_fear_greed_service.get_stock_feargreed(client)

    assert result == stale


async def test_stock_fear_greed_uses_a_fresh_cache_without_a_new_request():
    payload = {"score": 40, "rating": "Fear"}

    async with _client(_responds(payload)) as client:
        first = await stock_fear_greed_service.get_stock_feargreed(client)

    def _blow_up(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not re-fetch while the cache is fresh")

    async with _client(_blow_up) as client:
        second = await stock_fear_greed_service.get_stock_feargreed(client)

    assert first == second == {"value": 40, "status": "Fear", "change": None}


# ---------------------------------------------------------------------------
# Pass-through clients
# ---------------------------------------------------------------------------


async def test_spy_heatmap_returns_the_payload():
    payload = {"data": [{"ticker": "AAPL", "weight": 7.1}]}

    async with _client(_responds(payload)) as client:
        assert await unusual_whales.get_spy_heatmap(client) == payload


async def test_spy_heatmap_returns_none_on_http_error():
    async with _client(_responds({}, status=502)) as client:
        assert await unusual_whales.get_spy_heatmap(client) is None


# ---------------------------------------------------------------------------
# SPY heatmap sector/subsector aggregation
# ---------------------------------------------------------------------------


def test_summarize_spy_sectors_groups_by_sector_and_industry():
    payload = {
        "data": [
            {
                "ticker": "NVDA",
                "sector": "Technology",
                "industry": "Semiconductors",
                "close": "110",
                "prev_close": "100",
                "marketcap": 3_000_000_000_000,
            },
            {
                "ticker": "MSFT",
                "sector": "Technology",
                "industry": "Software",
                "close": "410",
                "prev_close": "410",
                "marketcap": 1_000_000_000_000,
            },
            {
                "ticker": "JPM",
                "sector": "Financials",
                "industry": "Banks",
                "close": "196",
                "prev_close": "200",
                "marketcap": 500_000_000_000,
            },
        ]
    }

    sectors = unusual_whales.summarize_spy_sectors(payload)

    assert [s["sector"] for s in sectors] == ["Technology", "Financials"]

    tech = sectors[0]
    assert tech["stock_count"] == 2
    assert tech["market_cap"] == 4_000_000_000_000
    # Weighted by market cap: (10% * 3T + 0% * 1T) / 4T = 7.5%
    assert tech["change_percent"] == pytest.approx(7.5)

    subsectors = {s["industry"]: s for s in tech["subsectors"]}
    assert subsectors["Semiconductors"]["change_percent"] == pytest.approx(10.0)
    assert subsectors["Software"]["change_percent"] == pytest.approx(0.0)

    financials = sectors[1]
    assert financials["change_percent"] == pytest.approx(-2.0)
    assert financials["subsectors"] == [
        {
            "industry": "Banks",
            "market_cap": 500_000_000_000,
            "change_percent": pytest.approx(-2.0),
            "stock_count": 1,
        }
    ]


def test_summarize_spy_sectors_falls_back_for_missing_sector_industry_or_price():
    payload = {
        "data": [
            {"ticker": "XYZ", "close": "10", "prev_close": "10", "marketcap": 1_000},
        ]
    }

    sectors = unusual_whales.summarize_spy_sectors(payload)

    assert sectors == [
        {
            "sector": "Unknown",
            "market_cap": 1_000,
            "change_percent": 0.0,
            "stock_count": 1,
            "subsectors": [
                {
                    "industry": "Other",
                    "market_cap": 1_000,
                    "change_percent": 0.0,
                    "stock_count": 1,
                }
            ],
        }
    ]


def test_summarize_spy_sectors_change_percent_is_none_without_market_cap():
    payload = {
        "data": [
            {"ticker": "XYZ", "sector": "Energy", "close": "10", "prev_close": "9"}
        ]
    }

    sectors = unusual_whales.summarize_spy_sectors(payload)

    assert sectors[0]["market_cap"] == 0.0
    assert sectors[0]["change_percent"] is None


def test_summarize_spy_sectors_handles_missing_or_malformed_payload():
    assert unusual_whales.summarize_spy_sectors(None) == []
    assert unusual_whales.summarize_spy_sectors({}) == []
    assert unusual_whales.summarize_spy_sectors({"data": "not-a-list"}) == []


async def test_treemap_returns_the_payload():
    payload = {"data": [{"s": "BTC", "p": 1.0}]}

    async with _client(_responds(payload)) as client:
        assert await coin360_service.get_treemap_data(client) == payload


async def test_treemap_returns_none_on_http_error():
    async with _client(_responds({}, status=500)) as client:
        assert await coin360_service.get_treemap_data(client) is None
