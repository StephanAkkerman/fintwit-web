import asyncio
import logging

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 10


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

    return articles[:limit]
