from unittest.mock import MagicMock, patch

import pytest

from app.services import news_service
from app.services.news_service import (
    annotate_news_sentiment,
    get_company_news,
    summarize_news_sentiment,
)


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


@pytest.mark.asyncio
async def test_get_company_news_sorts_newest_first_across_symbols():
    old = _news_item(title="old", url="https://example.com/old")
    old["content"]["pubDate"] = "2026-08-01T00:00:00Z"
    new = _news_item(title="new", url="https://example.com/new")
    new["content"]["pubDate"] = "2026-09-10T00:00:00Z"
    by_symbol = {"AAPL": [old], "TSLA": [new]}

    def make_ticker(symbol):
        ticker = MagicMock()
        ticker.get_news.return_value = by_symbol[symbol]
        return ticker

    with patch("yfinance.Ticker", side_effect=make_ticker):
        result = await get_company_news(["AAPL", "TSLA"], limit=1)

    assert [article["title"] for article in result] == ["new"]


class _FakeSentimentModel:
    def __init__(self, main_score, tickers=None, fail_on=None):
        self.main_score = main_score
        self.tickers = tickers or {}
        self.fail_on = fail_on
        self.calls = []

    async def classify_parts(self, text, tickers=None):
        self.calls.append((text, list(tickers or [])))
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("model blew up")
        return {
            "main": {"label": "IGNORED", "score": self.main_score},
            "quoted": None,
            "tickers": self.tickers,
        }


def _article(url="https://example.com/a", title="AAPL rallies", symbol="AAPL"):
    return {
        "symbols": [symbol],
        "title": title,
        "excerpt": "Strong demand.",
        "url": url,
        "date": "2026-09-01T12:00:00Z",
        "source": "Reuters",
    }


@pytest.fixture(autouse=True)
def _clear_sentiment_cache():
    news_service._SENTIMENT_CACHE.clear()
    yield
    news_service._SENTIMENT_CACHE.clear()


@pytest.mark.asyncio
async def test_annotate_news_sentiment_scores_title_and_excerpt():
    model = _FakeSentimentModel(0.8)

    [article] = await annotate_news_sentiment([_article()], model)

    assert article["sentiment_label"] == "BULLISH"
    assert article["sentiment_score"] == 0.8
    assert model.calls == [("AAPL rallies. Strong demand.", ["AAPL"])]


@pytest.mark.asyncio
async def test_annotate_news_sentiment_prefers_the_articles_own_ticker_score():
    model = _FakeSentimentModel(0.6, tickers={"AAPL": -0.7})

    [article] = await annotate_news_sentiment([_article()], model)

    assert article["sentiment_label"] == "BEARISH"
    assert article["sentiment_score"] == -0.7


@pytest.mark.asyncio
async def test_annotate_news_sentiment_caches_repeat_articles():
    model = _FakeSentimentModel(-0.5)

    await annotate_news_sentiment([_article()], model)
    [article] = await annotate_news_sentiment([_article()], model)

    assert len(model.calls) == 1
    assert article["sentiment_label"] == "BEARISH"


@pytest.mark.asyncio
async def test_annotate_news_sentiment_without_model_keeps_shape():
    [article] = await annotate_news_sentiment([_article()], None)

    assert article["sentiment_label"] is None
    assert article["sentiment_score"] is None
    assert article["title"] == "AAPL rallies"


@pytest.mark.asyncio
async def test_annotate_news_sentiment_isolates_a_failing_article():
    model = _FakeSentimentModel(0.9, fail_on="broken")
    articles = [
        _article(url="https://example.com/1", title="broken headline"),
        _article(url="https://example.com/2"),
    ]

    first, second = await annotate_news_sentiment(articles, model)

    assert first["sentiment_label"] is None
    assert second["sentiment_label"] == "BULLISH"


def test_summarize_news_sentiment_counts_and_averages():
    articles = [
        {"sentiment_label": "BULLISH", "sentiment_score": 0.9},
        {"sentiment_label": "BULLISH", "sentiment_score": 0.5},
        {"sentiment_label": "BEARISH", "sentiment_score": -0.8},
        {"sentiment_label": "NEUTRAL", "sentiment_score": 0.0},
        {"sentiment_label": None, "sentiment_score": None},
    ]

    assert summarize_news_sentiment(articles) == {
        "analyzed": 4,
        "bullish": 2,
        "neutral": 1,
        "bearish": 1,
        "mean_score": 0.15,
        "label": "BULLISH",
    }


def test_summarize_news_sentiment_with_nothing_scored():
    summary = summarize_news_sentiment([{"sentiment_score": None}])

    assert summary["analyzed"] == 0
    assert summary["mean_score"] is None
    assert summary["label"] is None
