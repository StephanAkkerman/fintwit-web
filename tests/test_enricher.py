from unittest.mock import MagicMock, patch

import pytest

from app.runtime.enricher import AssetEnricher

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
    return r


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
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_stock_info", return_value=None),
    ):
        result = await enricher.classify(["AAPL", ""])
    assert len(result) == 1


@pytest.mark.asyncio
async def test_classify_equity_fetches_stock_info():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result(
        "AAPL", "EQUITY", "Apple Inc.", 3_000_000_000_000
    )
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS
        ) as mock_stock,
    ):
        result = await enricher.classify(["AAPL"])
    mock_stock.assert_called_once_with("AAPL")
    assert result[0]["financials"] == STOCK_FINANCIALS


@pytest.mark.asyncio
async def test_classify_crypto_fetches_crypto_info():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin", 900_000_000_000)
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_crypto_info", return_value=CRYPTO_FINANCIALS
        ) as mock_crypto,
    ):
        result = await enricher.classify(["BTC"])
    mock_crypto.assert_called_once_with("BTC")
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_etf_uses_yahoo_lookup_for_stock_info():
    enricher = AssetEnricher()
    classifier_row = {
        "ticker": "SPY",
        "category": "ETF",
        "name": "SPDR S&P 500 ETF",
        "yahoo_lookup": "SPY",
    }
    with (
        patch.object(enricher._cls, "classify_async", return_value=[classifier_row]),
        patch(
            "app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS
        ) as mock_stock,
    ):
        result = await enricher.classify(["SPY"])

    mock_stock.assert_called_once_with("SPY")
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
    with (
        patch.object(enricher._cls, "classify_async", return_value=[classifier_row]),
        patch(
            "app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS
        ) as mock_stock,
    ):
        result = await enricher.classify(["EUR"])

    mock_stock.assert_called_once_with("EURUSD=X")
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
    with (
        patch.object(enricher._cls, "classify_async", return_value=[classifier_row]),
        patch(
            "app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS
        ) as mock_stock,
    ):
        result = await enricher.classify(["DXY"])

    mock_stock.assert_called_once_with("DX-Y.NYB")
    assert result[0]["financials"] == STOCK_FINANCIALS
    assert str(result[0]["kind"]).upper() == "INDEX"


@pytest.mark.asyncio
async def test_classify_lowercase_crypto_kind_also_fetches_crypto_info():
    """Enricher handles both "CRYPTO" and "crypto" as the same kind."""
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("ETH", "crypto", "Ethereum")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch(
            "app.runtime.enricher.get_crypto_info", return_value=CRYPTO_FINANCIALS
        ) as mock_crypto,
    ):
        result = await enricher.classify(["ETH"])
    mock_crypto.assert_called_once_with("ETH")
    assert result[0]["financials"] == CRYPTO_FINANCIALS


@pytest.mark.asyncio
async def test_classify_unknown_kind_returns_none_financials():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("XYZ", "UNKNOWN")
    with patch.object(enricher._cls, "classify_async", return_value=[mock_result]):
        result = await enricher.classify(["XYZ"])
    assert result[0]["financials"] is None


@pytest.mark.asyncio
async def test_classify_stock_service_returns_none():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_stock_info", return_value=None),
    ):
        result = await enricher.classify(["AAPL"])
    assert result[0]["financials"] is None


@pytest.mark.asyncio
async def test_classify_crypto_service_returns_none():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("BTC", "CRYPTO")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_crypto_info", return_value=None),
    ):
        result = await enricher.classify(["BTC"])
    assert result[0]["financials"] is None


@pytest.mark.asyncio
async def test_classify_normalizes_symbols_to_uppercase():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with (
        patch.object(
            enricher._cls, "classify_async", return_value=[mock_result]
        ) as mock_cls,
        patch("app.runtime.enricher.get_stock_info", return_value=None),
    ):
        result = await enricher.classify(["aapl"])
    # Classifier should have been called with uppercase symbol
    mock_cls.assert_called_once_with(["AAPL"])
    assert result[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_classify_uses_cache_on_second_call():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with (
        patch.object(
            enricher._cls, "classify_async", return_value=[mock_result]
        ) as mock_cls,
        patch("app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS),
    ):
        await enricher.classify(["AAPL"])
        await enricher.classify(["AAPL"])
    # classify_async must only be called once; second call uses cache
    mock_cls.assert_called_once()


@pytest.mark.asyncio
async def test_classify_deduplicates_symbols():
    enricher = AssetEnricher()
    mock_result = _mock_classifier_result("AAPL", "EQUITY")
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_stock_info", return_value=None),
    ):
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
    )
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS),
    ):
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
    assert result[0]["meta"] == {"exchange": "NASDAQ"}


@pytest.mark.asyncio
async def test_classify_multiple_mixed_symbols():
    enricher = AssetEnricher()
    mock_aapl = _mock_classifier_result("AAPL", "EQUITY", "Apple Inc.")
    mock_btc = _mock_classifier_result("BTC", "CRYPTO", "Bitcoin")
    with (
        patch.object(
            enricher._cls, "classify_async", return_value=[mock_aapl, mock_btc]
        ),
        patch("app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS),
        patch("app.runtime.enricher.get_crypto_info", return_value=CRYPTO_FINANCIALS),
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
    with (
        patch.object(enricher._cls, "classify_async", return_value=[mock_result]),
        patch("app.runtime.enricher.get_stock_info", return_value=STOCK_FINANCIALS),
    ):
        result1 = await enricher.classify(["AAPL"])
        result2 = await enricher.classify(["AAPL"])
    # Mutating the first result should not affect the second
    result1[0]["name"] = "MUTATED"
    assert result2[0]["name"] == "Apple Inc."
