from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services import news_digest
from app.services.news_digest import (
    build_digest,
    cluster_articles,
    get_market_news,
    merge_articles,
    overview_symbols,
    summarize_text,
)

NOW = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)


def _article(title, url, date="2026-10-15T16:00:00Z", source="Reuters", **extra):
    return {
        "symbols": extra.pop("symbols", ["SPY"]),
        "title": title,
        "excerpt": extra.pop("excerpt", None),
        "url": url,
        "date": date,
        "source": source,
        **extra,
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    news_digest._CACHE.clear()
    yield
    news_digest._CACHE.clear()


def test_overview_symbols_reads_env(monkeypatch):
    monkeypatch.setenv("NEWS_OVERVIEW_SYMBOLS", "spy, nvda,")
    assert overview_symbols() == ["SPY", "NVDA"]
    monkeypatch.delenv("NEWS_OVERVIEW_SYMBOLS")
    assert overview_symbols() == list(news_digest.DEFAULT_OVERVIEW_SYMBOLS)


def test_merge_articles_unions_symbols_of_one_url():
    spy = [_article("Fed holds rates", "https://x/1", symbols=["SPY"])]
    qqq = [
        _article("Fed holds rates", "https://x/1", symbols=["QQQ"]),
        _article("Nvidia jumps", "https://x/2", date="2026-10-15T17:00:00Z"),
    ]
    merged = merge_articles([spy, qqq])
    assert [a["url"] for a in merged] == ["https://x/2", "https://x/1"]
    assert merged[1]["symbols"] == ["SPY", "QQQ"]
    # The input article is not mutated.
    assert spy[0]["symbols"] == ["SPY"]


def test_cluster_articles_groups_headlines_about_one_event():
    articles = [
        _article("Fed holds interest rates steady, Powell signals patience", "a"),
        _article("Powell says Fed will be patient on interest rates", "b"),
        _article("Oil climbs as OPEC weighs output cut", "c"),
    ]
    clusters = cluster_articles(articles)
    assert [[a["url"] for a in c] for c in clusters] == [["a", "b"], ["c"]]


def test_summarize_text_keeps_leading_sentences_under_limit():
    text = "First sentence here. " * 3 + "x" * 400
    summary = summarize_text(text, max_chars=60)
    assert summary == "First sentence here. First sentence here."
    assert summarize_text("word " * 100, max_chars=40).endswith("…")
    assert len(summarize_text("word " * 100, max_chars=40)) <= 40
    assert summarize_text(None) == ""


def test_build_digest_ranks_widely_covered_story_first():
    articles = [
        _article("Small biotech wins approval", "s1", date="2026-10-15T17:50:00Z"),
        _article(
            "Fed cuts interest rates by quarter point",
            "f1",
            source="Reuters",
            symbols=["SPY", "QQQ"],
            excerpt="The Federal Reserve lowered rates. Markets rallied. More text.",
            sentiment_label="BULLISH",
            sentiment_score=0.8,
        ),
        _article(
            "Fed cuts interest rates, signals more to come",
            "f2",
            source="CNBC",
            symbols=["DIA"],
            sentiment_label="BULLISH",
            sentiment_score=0.6,
        ),
    ]
    digest = build_digest(articles, now=NOW)
    top = digest["top_stories"][0]
    assert top["url"] == "f1"
    assert top["article_count"] == 2
    assert top["sources"] == ["CNBC", "Reuters"]
    assert top["symbols"] == ["DIA", "QQQ", "SPY"]
    assert top["themes"] == ["Fed & rates"]
    assert top["sentiment_label"] == "BULLISH"
    assert top["sentiment_score"] == 0.7
    assert (
        top["summary"]
        == "The Federal Reserve lowered rates. Markets rallied. More text."
    )
    assert top["related"] == [
        {
            "title": "Fed cuts interest rates, signals more to come",
            "url": "f2",
            "source": "CNBC",
        }
    ]
    assert digest["themes"] == [{"name": "Fed & rates", "count": 2}]


def test_build_digest_prefers_recent_stories_and_caps_count():
    articles = [
        _article(title, url, date=date)
        for title, url, date in [
            ("Retailer posts holiday sales", "alpha", "2026-10-13T18:00:00Z"),
            ("Airline adds routes to Asia", "bravo", "2026-10-15T17:00:00Z"),
            ("Brewer names chief executive", "charlie", "not a date"),
        ]
    ]
    digest = build_digest(articles, now=NOW, max_stories=2)
    assert [s["url"] for s in digest["top_stories"]] == ["bravo", "alpha"]


def test_build_digest_handles_no_articles():
    assert build_digest([], now=NOW) == {"top_stories": [], "themes": []}


def _news_item(title, url):
    return {
        "content": {
            "title": title,
            "pubDate": "2026-10-15T12:00:00Z",
            "provider": {"displayName": "Reuters"},
            "clickThroughUrl": {"url": url},
        }
    }


@pytest.mark.asyncio
async def test_get_market_news_merges_and_caches():
    ticker = MagicMock()
    ticker.get_news.return_value = [_news_item("Stocks rally", "https://x/1")]

    with patch("yfinance.Ticker", return_value=ticker) as mock_cls:
        first = await get_market_news(["SPY", "QQQ"])
        second = await get_market_news(["SPY", "QQQ"])

    assert first == second
    assert len(first) == 1
    assert first[0]["symbols"] == ["SPY", "QQQ"]
    assert mock_cls.call_count == 2  # once per symbol, then served from cache


@pytest.mark.asyncio
async def test_get_market_news_returns_none_when_every_feed_fails():
    with patch("yfinance.Ticker", side_effect=RuntimeError("429")):
        assert await get_market_news(["SPY"]) is None
    assert news_digest._CACHE == {}
