from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.runtime.enricher import AssetEnricher

STOCK_FINANCIALS = {
    "price": 185.0,
    "change_percent": 1.5,
    "volume": 80_000_000,
    "website": "https://finance.yahoo.com/quote/AAPL",
}

CRYPTO_FINANCIALS = {
    "price": 45_000.0,
    "change_percent": 3.2,
    "volume": 25_000_000_000.0,
    "website": "https://www.coingecko.com/en/coins/bitcoin",
}


def _route_price(entry):
    """Mimic ticker-price-data: crypto entries get crypto financials, else stock.

    Price routing now lives in ``ticker_price_data.price_from_classification``;
    these tests stub that seam and assert the enricher feeds it correctly
    classified entries (right ``kind``/``yahoo_lookup``).
    """
    kind = str(entry.get("kind") or entry.get("category") or "").upper()
    return CRYPTO_FINANCIALS if kind == "CRYPTO" else STOCK_FINANCIALS


@pytest.fixture(autouse=True)
def _enricher_defaults():
    with (
        patch(
            "app.runtime.enricher.get_tradingview_ta_summary",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.runtime.enricher.get_signa_signal",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.runtime.enricher.get_stocktwits_sentiment",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.runtime.enricher.price_from_classification",
            new=AsyncMock(side_effect=_route_price),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_classifier_result(
    symbol,
    kind,
    name="Test Asset",
    market_cap=1_000_000,
    meta=None,
    sector=None,
    industry=None,
    company_profile=None,
    fundamentals=None,
):
    """Return a mock object that looks like a TickerClassifier result row."""
    r = MagicMock()
    r.symbol = symbol
    r.kind = kind
    r.name = name
    r.market_cap = market_cap
    r.meta = meta or {}
    r.sector = sector
    r.industry = industry
    r.company_profile = company_profile
    r.fundamentals = fundamentals
    return r


TRADINGVIEW_TA = {
    "source": "tradingview_ta",
    "website": "https://www.tradingview.com/symbols/NASDAQ-AAPL/",
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "screener": "america",
    "four_h": {
        "interval": "four_h",
        "recommendation": "Buy",
        "buy": 10,
        "neutral": 8,
        "sell": 4,
        "summary": "Buy\n10📈 8⌛️ 4📉",
    },
    "one_d": {
        "interval": "one_d",
        "recommendation": "Strong Buy",
        "buy": 13,
        "neutral": 7,
        "sell": 2,
        "summary": "Strong Buy\n13📈 7⌛️ 2📉",
    },
}

SIGNA_SIGNAL = {
    "source": "signa",
    "symbol": "AAPL",
    "signal": "Bullish",
    "score": 74.0,
    "trend": "up",
    "confidence": 0.81,
    "timeframe": "1D",
    "website": "https://app.getsigna.ai/?sym=AAPL",
}

STOCKTWITS_SENTIMENT = {
    "source": "stocktwits",
    "symbol": "AAPL",
    "bullish_percent": 62.5,
    "bearish_percent": 37.5,
    "message_volume": 120,
    "as_of": "2026-09-02T08:00:00.000Z",
    "website": "https://stocktwits.com/symbol/AAPL",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_empty_input_returns_empty_list():
    enricher = AssetEnricher()
    result = await enricher.classify([])
    assert result == []


@pytest.mark.asyncio
async def test_classify_whitespace_symbols_are_filtered():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL", ""])
    assert len(result) == 1


@pytest.mark.asyncio
async def test_classify_equity_fetches_stock_info():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", 3_000_000_000_000
    )
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL"])
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_crypto_fetches_crypto_info():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin", 900_000_000_000)
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["BTC"])
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_equity_attaches_tradingview_ta_summary():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", 3_000_000_000_000
    )
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_tradingview_ta_summary",
            new=AsyncMock(return_value=TRADINGVIEW_TA),
        ),
    ):
        result = await enricher.classify(["AAPL"])

    assert result[0]["financials"]["technical_analysis"] == TRADINGVIEW_TA


@pytest.mark.asyncio
async def test_classify_equity_attaches_signa_signal():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", 3_000_000_000_000
    )
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_signa_signal",
            new=AsyncMock(return_value=SIGNA_SIGNAL),
        ) as mock_signa,
    ):
        result = await enricher.classify(["AAPL"])

    mock_signa.assert_awaited_once_with("AAPL")
    assert result[0]["financials"]["signa"] == SIGNA_SIGNAL


@pytest.mark.asyncio
async def test_classify_crypto_does_not_fetch_signa_signal():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_signa_signal",
            new=AsyncMock(return_value=SIGNA_SIGNAL),
        ) as mock_signa,
    ):
        result = await enricher.classify(["BTC"])

    mock_signa.assert_not_awaited()
    assert "signa" not in result[0]["financials"]


@pytest.mark.asyncio
async def test_classify_equity_attaches_stocktwits_sentiment():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", 3_000_000_000_000
    )
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_stocktwits_sentiment",
            new=AsyncMock(return_value=STOCKTWITS_SENTIMENT),
        ) as mock_stocktwits,
    ):
        result = await enricher.classify(["AAPL"])

    mock_stocktwits.assert_awaited_once_with("AAPL")
    assert result[0]["financials"]["stocktwits_sentiment"] == STOCKTWITS_SENTIMENT


@pytest.mark.asyncio
async def test_classify_crypto_also_fetches_stocktwits_sentiment():
    """StockTwits covers crypto too, unlike the equity-only Signa signal."""
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin")
    crypto_sentiment = {**STOCKTWITS_SENTIMENT, "symbol": "BTC"}
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_stocktwits_sentiment",
            new=AsyncMock(return_value=crypto_sentiment),
        ) as mock_stocktwits,
    ):
        result = await enricher.classify(["BTC"])

    mock_stocktwits.assert_awaited_once_with("BTC")
    assert result[0]["financials"]["stocktwits_sentiment"] == crypto_sentiment


@pytest.mark.asyncio
async def test_classify_etf_uses_yahoo_lookup_for_stock_info():
    enricher = AssetEnricher()
    classifier_row = {
        "ticker": "SPY",
        "category": "ETF",
        "name": "SPDR S&P 500 ETF",
        "yahoo_lookup": "SPY",
    }
    with patch.object(enricher._cls, "classify_async", return_value=[classifier_row]):
        result = await enricher.classify(["SPY"])

    assert result[0]["yahoo_lookup"] == "SPY"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_forex_uses_yahoo_lookup_for_stock_info():
    enricher = AssetEnricher()
    classifier_row = {
        "ticker": "EUR",
        "category": "forex",
        "name": "EUR Currency",
        "yahoo_lookup": "EURUSD=X",
    }
    with patch.object(enricher._cls, "classify_async", return_value=[classifier_row]):
        result = await enricher.classify(["EUR"])

    assert result[0]["yahoo_lookup"] == "EURUSD=X"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_dxy_uses_classifier_yahoo_lookup():
    enricher = AssetEnricher()
    classifier_row = {
        "ticker": "DXY",
        "category": "Index",
        "name": "US Dollar Index",
        "yahoo_lookup": "DX-Y.NYB",
    }
    with patch.object(enricher._cls, "classify_async", return_value=[classifier_row]):
        result = await enricher.classify(["DXY"])

    assert result[0]["yahoo_lookup"] == "DX-Y.NYB"
    assert result[0]["financials"] == STOCK_FINANCIALS
    assert str(result[0]["kind"]).upper() == "INDEX"


@pytest.mark.asyncio
async def test_classify_eurusd_pair_uses_local_forex_override():
    enricher = AssetEnricher()
    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["EURUSD"])

    mock_cls.assert_not_called()
    assert result[0]["symbol"] == "EURUSD"
    assert result[0]["kind"] == "FOREX"
    assert result[0]["name"] == "EUR/USD"
    assert result[0]["yahoo_lookup"] == "EURUSD=X"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_usoil_uses_local_commodity_override():
    enricher = AssetEnricher()
    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["USOIL"])

    mock_cls.assert_not_called()
    assert result[0]["symbol"] == "USOIL"
    assert result[0]["kind"] == "COMMODITY"
    assert result[0]["name"] == "Crude Oil"
    assert result[0]["yahoo_lookup"] == "CL=F"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_nq_uses_local_future_override():
    enricher = AssetEnricher()
    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["NQ"])

    mock_cls.assert_not_called()
    assert result[0]["symbol"] == "NQ"
    assert result[0]["kind"] == "FUTURE"
    assert result[0]["name"] == "E-mini Nasdaq-100 Futures"
    assert result[0]["yahoo_lookup"] == "NQ=F"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_ym_local_override_replaces_stale_cached_crypto():
    enricher = AssetEnricher()
    enricher._cache["YM"] = {
        "symbol": "YM",
        "kind": "CRYPTO",
        "name": "Wrong Cache Entry",
        "market_cap": None,
        "sector": None,
        "industry": None,
        "company_profile": None,
        "meta": None,
        "yahoo_lookup": "YM-USD",
    }

    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["YM"])

    mock_cls.assert_not_called()
    assert result[0]["kind"] == "FUTURE"
    assert result[0]["name"] == "E-mini Dow Futures"
    assert result[0]["yahoo_lookup"] == "YM=F"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_eth_uses_local_crypto_override():
    enricher = AssetEnricher()
    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["ETH"])

    mock_cls.assert_not_called()
    assert result[0]["symbol"] == "ETH"
    assert result[0]["kind"] == "CRYPTO"
    assert result[0]["name"] == "Ethereum"
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_eth_local_override_replaces_stale_cached_etf():
    enricher = AssetEnricher()
    enricher._cache["ETH"] = {
        "symbol": "ETH",
        "kind": "ETF",
        "name": "VanEck Ethereum ETF",
        "market_cap": None,
        "sector": None,
        "industry": None,
        "company_profile": None,
        "meta": None,
        "yahoo_lookup": "ETH",
    }

    with patch.object(enricher._cls, "classify_async", return_value=[]) as mock_cls:
        result = await enricher.classify(["ETH"])

    mock_cls.assert_not_called()
    assert result[0]["kind"] == "CRYPTO"
    assert result[0]["name"] == "Ethereum"
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_lowercase_crypto_kind_also_fetches_crypto_info():
    """Enricher handles both "CRYPTO" and "crypto" as the same kind."""
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("ETH", "crypto", "Ethereum")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["ETH"])
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_unknown_kind_is_excluded_from_assets():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("XYZ", "UNKNOWN")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["XYZ"])
    assert result == []


@pytest.mark.asyncio
async def test_classify_excludes_unknown_but_keeps_supported_kinds():
    enricher = AssetEnricher()
    unknown = _mock_classifier_result("OOTT", "UNKNOWN")
    equity = _mock_classifier_result("AAPL", "EQUITY")

    with patch.object(enricher._cls, "classify_async", return_value=[unknown, equity]):
        result = await enricher.classify(["OOTT", "AAPL"])

    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_stock_service_returns_none():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.price_from_classification",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await enricher.classify(["AAPL"])
    assert result[0]["financials"] is None


@pytest.mark.asyncio
async def test_classify_crypto_service_returns_none():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.price_from_classification",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await enricher.classify(["BTC"])
    assert result[0]["financials"] is None


@pytest.mark.asyncio
async def test_classify_normalizes_symbols_to_uppercase():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with patch.object(
        enricher._cls, "classify_async", return_value=[mock_result]
    ) as mock_cls:
        result = await enricher.classify(["aapl"])
    # Classifier should have been called with uppercase symbol
    mock_cls.assert_called_once_with(["AAPL"])
    assert result[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_classify_uses_cache_on_second_call():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with patch.object(
        enricher._cls, "classify_async", return_value=[mock_result]
    ) as mock_cls:
        await enricher.classify(["AAPL"])
        await enricher.classify(["AAPL"])
    # classify_async must only be called once; second call uses cache
    mock_cls.assert_called_once()


@pytest.mark.asyncio
async def test_classify_deduplicates_symbols():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL", "AAPL", "aapl"])
    assert len(result) == 1


@pytest.mark.asyncio
async def test_classify_preserves_static_fields():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL",
        "EQUITY",
        "Apple Inc.",
        3_000_000_000_000,
        {"exchange": "NASDAQ"},
        sector="Information Technology",
        industry="Electronic Equipment, Instruments & Components",
        company_profile={
            "industry_group": "Technology Hardware & Equipment",
            "country": "United States",
            "exchange": "NASDAQ Global Select",
            "currency": "USD",
            "website": "http://www.apple.com",
            "market_cap_category": "Mega Cap",
        },
        fundamentals={
            "market_cap": 3_000_000_000_000,
            "forward_pe": 30.7,
            "trailing_pe": 41.1,
            "avg_volume": 54_321_000,
            "currency": "USD",
        },
    )
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL"])
    assert result[0]["name"] == "Apple Inc."
    assert result[0]["market_cap"] == 3_000_000_000_000
    assert result[0]["sector"] == "Information Technology"
    assert result[0]["industry"] == "Electronic Equipment, Instruments & Components"
    assert result[0]["company_profile"] == {
        "industry_group": "Technology Hardware & Equipment",
        "country": "United States",
        "exchange": "NASDAQ Global Select",
        "currency": "USD",
        "website": "http://www.apple.com",
        "market_cap_category": "Mega Cap",
    }
    assert result[0]["fundamentals"] == {
        "market_cap": 3_000_000_000_000,
        "forward_pe": 30.7,
        "trailing_pe": 41.1,
        "avg_volume": 54_321_000,
        "currency": "USD",
    }
    assert result[0]["meta"] == {"exchange": "NASDAQ"}


@pytest.mark.asyncio
async def test_classify_fundamentals_absent_when_classifier_omits_them():
    """Older cached classifier rows have no fundamentals; the key must still exist."""
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY", "Apple Inc.")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL"])
    assert result[0]["fundamentals"] is None


@pytest.mark.asyncio
async def test_classify_fundamentals_ignores_non_dict_payload():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", fundamentals="not-a-dict"
    )
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["AAPL"])
    assert result[0]["fundamentals"] is None


@pytest.mark.asyncio
async def test_classify_local_override_has_no_fundamentals():
    """Local shortcuts bypass the classifier, so there is no quote to read."""
    enricher = AssetEnricher()
    with patch.object(enricher._cls, "classify_async", return_value=[]):
        result = await enricher.classify(["NQ"])
    assert result[0]["fundamentals"] is None


@pytest.mark.asyncio
async def test_classify_multiple_mixed_symbols():
    enricher = AssetEnricher()
    mock_aapl = _mock_classifier_result("AAPL", "EQUITY", "Apple Inc.")
    mock_btc = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin")
    with patch.object(
        enricher._cls, "classify_async", return_value=[mock_aapl, mock_btc]
    ):
        result = await enricher.classify(["AAPL", "BTC"])
    assert len(result) == 2
    symbols = {r["symbol"] for r in result}
    assert symbols == {"AAPL", "BTC"}
    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["AAPL"]["financials"] == STOCK_FINANCIALS
    assert by_symbol["BTC"]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_does_not_mutate_cache_between_calls():
    """Each call should return a fresh copy, not a shared mutable dict."""
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY", "Apple Inc.")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result1 = await enricher.classify(["AAPL"])
        result2 = await enricher.classify(["AAPL"])
    # Mutating the first result should not affect the second
    result1[0]["name"] = "MUTATED"
    assert result2[0]["name"] == "Apple Inc."
