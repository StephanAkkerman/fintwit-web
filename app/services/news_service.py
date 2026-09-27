import asyncio
import logging
from collections import OrderedDict
from typing import Any, Protocol, Sequence

from ..ml.sentiment import label_from_score

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 10

#: Headlines are re-requested every time the widget loads a symbol; the same
#: article reads the same way every time, so skip the model on a repeat.
_SENTIMENT_CACHE_MAX = 2000
_SENTIMENT_CACHE: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()


class SentimentModel(Protocol):
    async def classify_parts(
        self, text: str, tickers: Sequence[str] | None = None
    ) -> dict[str, Any]: ...


def _normalize_article(item: dict, symbol: str) -> dict | None:
    content = item.get("content")
    if not isinstance(content, dict):
        return None

    title = content.get("title")

    url = None
    click_through = content.get("clickThroughUrl")
    if isinstance(click_through, dict):
        url = click_through.get("url")
    if not url:
        canonical = content.get("canonicalUrl")
        if isinstance(canonical, dict):
            url = canonical.get("url")
    if not url:
        url = content.get("previewUrl")

    date = content.get("pubDate") or content.get("displayTime")
    provider = content.get("provider")
    source = provider.get("displayName") if isinstance(provider, dict) else None
    excerpt = content.get("summary") or content.get("description") or None

    if not (title and url and date):
        return None

    return {
        "symbols": [symbol],
        "title": title,
        "excerpt": excerpt,
        "url": url,
        "date": date,
        "source": source,
    }


def _fetch_news_sync(symbol: str, limit: int) -> list[dict]:
    """Blocking yfinance call — always run this via asyncio.to_thread."""
    import yfinance as yf

    raw = yf.Ticker(symbol).get_news(count=limit) or []
    articles = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        article = _normalize_article(item, symbol)
        if article is not None:
            articles.append(article)
    return articles


async def get_company_news(
    symbols: list[str], limit: int = _DEFAULT_LIMIT
) -> list[dict] | None:
    """Fetch recent company news for one or more tickers from Yahoo Finance.

    The blocking yfinance/requests call runs in a worker thread
    (asyncio.to_thread) so it never blocks the event loop.
    """
    normalized = [sym.strip().upper() for sym in symbols if sym.strip()]
    if not normalized:
        return None

    async def fetch_one(symbol: str) -> list[dict]:
        try:
            return await asyncio.to_thread(_fetch_news_sync, symbol, limit)
        except Exception as exc:
            logger.warning("[news] yfinance fetch failed for %s: %r", symbol, exc)
            return []

    results = await asyncio.gather(*(fetch_one(sym) for sym in normalized))
    articles = [article for group in results for article in group]
    if not articles:
        return None

    # Newest first across every requested symbol, so a multi-symbol request is
    # not truncated down to the first symbol's headlines.
    articles.sort(key=lambda article: str(article["date"]), reverse=True)
    return articles[:limit]


def _article_text(article: dict) -> str:
    title = str(article.get("title") or "").strip()
    excerpt = str(article.get("excerpt") or "").strip()
    if title and not title.endswith((".", "!", "?")):
        title += "."
    return f"{title} {excerpt}".strip()


async def _classify_article(article: dict, model: SentimentModel) -> dict | None:
    symbols = [str(sym).upper() for sym in article.get("symbols") or []]
    key = (str(article.get("url")), ",".join(symbols))
    cached = _SENTIMENT_CACHE.get(key)
    if cached is not None:
        _SENTIMENT_CACHE.move_to_end(key)
        return cached

    parts = await model.classify_parts(_article_text(article), symbols)
    main = parts.get("main")
    if not main:
        return None

    score = float(main.get("score", 0.0))
    # An article fetched for one symbol that also discusses others: read the
    # sentences about that symbol rather than the headline as a whole.
    per_ticker = parts.get("tickers") or {}
    for symbol in symbols:
        if symbol in per_ticker:
            score = float(per_ticker[symbol])
            break

    verdict = {"label": label_from_score(score), "score": round(score, 4)}
    _SENTIMENT_CACHE[key] = verdict
    while len(_SENTIMENT_CACHE) > _SENTIMENT_CACHE_MAX:
        _SENTIMENT_CACHE.popitem(last=False)
    return verdict


async def annotate_news_sentiment(
    articles: list[dict], model: SentimentModel | None
) -> list[dict]:
    """Attach FinTwitBERT ``sentiment_label``/``sentiment_score`` to articles.

    Headline and excerpt are classified together. Articles the model could not
    read (or every article, when no model is loaded) get ``None`` for both, so
    the response shape never depends on whether the ML stack is installed.
    """
    annotated = []
    for article in articles:
        verdict = None
        if model is not None:
            try:
                verdict = await _classify_article(article, model)
            except Exception as exc:
                logger.warning(
                    "[news] sentiment failed for %s: %r", article.get("url"), exc
                )
        annotated.append(
            {
                **article,
                "sentiment_label": verdict["label"] if verdict else None,
                "sentiment_score": verdict["score"] if verdict else None,
            }
        )
    return annotated


def summarize_news_sentiment(articles: list[dict]) -> dict:
    """Aggregate per-article sentiment into one read of the news flow.

    :return: ``{analyzed, bullish, neutral, bearish, mean_score, label}``.
        ``mean_score``/``label`` are ``None`` when no article was scored.
    """
    scores = [
        float(article["sentiment_score"])
        for article in articles
        if article.get("sentiment_score") is not None
    ]
    labels = [
        article.get("sentiment_label")
        for article in articles
        if article.get("sentiment_score") is not None
    ]
    mean = round(sum(scores) / len(scores), 4) if scores else None
    return {
        "analyzed": len(scores),
        "bullish": labels.count("BULLISH"),
        "neutral": labels.count("NEUTRAL"),
        "bearish": labels.count("BEARISH"),
        "mean_score": mean,
        "label": label_from_score(mean) if mean is not None else None,
    }
