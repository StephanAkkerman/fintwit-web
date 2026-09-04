from unittest.mock import MagicMock, patch

import pytest

from app.services.news_service import get_company_news


def _news_item(title="AAPL rallies", url="https://example.com/a", source="Reuters"):
    return {
        "content": {
            "title": title,
            "pubDate": "2026-09-01T12:00:00Z",
            "provider": {"displayName": source},
            "summary": "Some summary text.",
            "clickThroughUrl": {"url": url},
        }
    }


@pytest.mark.asyncio
async def test_get_company_news_normalizes_articles():
    ticker = MagicMock()
    ticker.get_news.return_value = [_news_item()]

    with patch("yfinance.Ticker", return_value=ticker) as mock_ticker_cls:
        result = await get_company_news(["aapl"], limit=5)

    mock_ticker_cls.assert_called_once_with("AAPL")
    ticker.get_news.assert_called_once_with(count=5)
    assert result == [
        {
            "symbols": ["AAPL"],
            "title": "AAPL rallies",
            "excerpt": "Some summary text.",
            "url": "https://example.com/a",
            "date": "2026-09-01T12:00:00Z",
            "source": "Reuters",
        }
    ]


@pytest.mark.asyncio
async def test_get_company_news_falls_back_to_canonical_url():
    item = _news_item()
    del item["content"]["clickThroughUrl"]
    item["content"]["canonicalUrl"] = {"url": "https://example.com/canonical"}
    ticker = MagicMock()
    ticker.get_news.return_value = [item]

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_company_news(["AAPL"])

    assert result[0]["url"] == "https://example.com/canonical"


@pytest.mark.asyncio
async def test_get_company_news_skips_items_missing_required_fields():
    ticker = MagicMock()
    ticker.get_news.return_value = [{"content": {"title": None}}, _news_item()]

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_company_news(["AAPL"])

    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_company_news_merges_multiple_symbols():
    ticker = MagicMock()
    ticker.get_news.return_value = [_news_item()]

    with patch("yfinance.Ticker", return_value=ticker):
        result = await get_company_news(["AAPL", "TSLA"], limit=10)

    assert len(result) == 2
    assert {article["symbols"][0] for article in result} == {"AAPL", "TSLA"}


@pytest.mark.asyncio
async def test_get_company_news_returns_none_when_all_fail():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network down")):
        result = await get_company_news(["AAPL"])

    assert result is None


@pytest.mark.asyncio
async def test_get_company_news_returns_none_for_blank_symbols():
    result = await get_company_news([""])

    assert result is None
