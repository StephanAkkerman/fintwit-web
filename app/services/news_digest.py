"""Market news overview: the day's most important headlines (issue #217).

Everything here is plain Python so the digest runs on a Raspberry Pi 4 with no
LLM, paid or local. The "summary" of a story is the summary Yahoo already
scraped from the article; what this module adds is deciding which stories
matter:

1. Fetch headlines for a handful of broad-market symbols and merge the copies
   of one article that Yahoo lists under several of them.
2. Group headlines about the same event by the words their titles share.
3. Rank each group by how widely it is covered (articles, outlets, symbols),
   how recent it is, and whether it touches a market-moving topic.
"""

import asyncio
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from .news_service import _fetch_news_sync

logger = logging.getLogger(__name__)

#: Broad-market symbols whose Yahoo news feeds make up the overview: the index
#: trackers, small caps, bitcoin, gold and oil.
DEFAULT_OVERVIEW_SYMBOLS = ("SPY", "QQQ", "DIA", "IWM", "BTC-USD", "GC=F", "CL=F")

_PER_SYMBOL_LIMIT = 20
_CACHE_TTL_SECONDS = 600.0
_CACHE: dict[tuple[str, ...], tuple[float, list[dict]]] = {}

#: Recency weight halves every this many hours.
_RECENCY_HALF_LIFE_HOURS = 12.0
_SUMMARY_MAX_CHARS = 280

#: Topic → title words that put a headline in it. A headline in any topic gets
#: a ranking boost: these are the subjects that move the market as a whole.
THEMES: dict[str, frozenset[str]] = {
    "Fed & rates": frozenset(
        {"fed", "fomc", "powell", "rate", "rates", "yield", "yields", "treasury"}
    ),
    "Inflation": frozenset({"inflation", "cpi", "ppi", "pce", "prices"}),
    "Jobs": frozenset({"jobs", "payrolls", "unemployment", "jobless", "labor"}),
    "Earnings": frozenset(
        {"earnings", "revenue", "guidance", "profit", "quarterly", "eps"}
    ),
    "Trade & tariffs": frozenset({"tariff", "tariffs", "trade", "sanctions"}),
    "Deals": frozenset(
        {"merger", "acquisition", "acquire", "acquires", "buyout", "takeover", "ipo"}
    ),
    "AI & chips": frozenset(
        {"ai", "nvidia", "chip", "chips", "semiconductor", "semiconductors"}
    ),
    "Crypto": frozenset({"bitcoin", "crypto", "btc", "ether", "ethereum"}),
    "Energy": frozenset({"oil", "opec", "crude", "gas", "energy"}),
    "Gold": frozenset({"gold", "silver", "metals"}),
}

_STOPWORDS = frozenset(
    """
    a about after again against ahead all also amid an and any are as at be
    been before being but by can could did do does down for from had has have
    he her his how if in into is it its just more most new no not now of off
    on or other our out over says say said she so some still than that the
    their them then there these they this those through to today too under up
    us vs was we week were what when where which while who why will with would
    you your stock stocks shares market markets wall street investors here
    """.split()
)

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def overview_symbols() -> list[str]:
    """Symbols the overview reads, from ``NEWS_OVERVIEW_SYMBOLS`` if set."""
    raw = os.getenv("NEWS_OVERVIEW_SYMBOLS", "")
    parsed = [part.strip().upper() for part in raw.split(",") if part.strip()]
    return parsed or list(DEFAULT_OVERVIEW_SYMBOLS)


def _tokens(text: str) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    return {
        word.removesuffix("'s")
        for word in words
        if len(word) > 1 and word not in _STOPWORDS and not word.isdigit()
    }


def _parse_date(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def merge_articles(groups: list[list[dict]]) -> list[dict]:
    """Collapse one article listed under several symbols into a single entry.

    The union of its ``symbols`` is kept: an article Yahoo files under SPY,
    QQQ and DIA at once is about the whole market, which the ranking uses.
    """
    by_url: dict[str, dict] = {}
    for group in groups:
        for article in group:
            url = str(article.get("url"))
            existing = by_url.get(url)
            if existing is None:
                by_url[url] = {**article, "symbols": list(article.get("symbols", []))}
                continue
            for symbol in article.get("symbols", []):
                if symbol not in existing["symbols"]:
                    existing["symbols"].append(symbol)
    return sorted(by_url.values(), key=lambda a: str(a.get("date")), reverse=True)


async def get_market_news(
    symbols: list[str], per_symbol: int = _PER_SYMBOL_LIMIT
) -> list[dict] | None:
    """Merged, newest-first headlines for ``symbols``; cached for ten minutes.

    The cache keeps a Pi from re-scraping Yahoo for every page load. ``None``
    means no symbol returned anything (Yahoo down or rate-limiting).
    """
    key = tuple(symbols)
    cached = _CACHE.get(key)
    if cached is not None and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    async def fetch_one(symbol: str) -> list[dict]:
        try:
            return await asyncio.to_thread(_fetch_news_sync, symbol, per_symbol)
        except Exception as exc:
            logger.warning("[news] overview fetch failed for %s: %r", symbol, exc)
            return []

    groups = await asyncio.gather(*(fetch_one(symbol) for symbol in symbols))
    articles = merge_articles(list(groups))
    if not articles:
        return None
    _CACHE[key] = (time.monotonic(), articles)
    return articles


def _same_story(a: set[str], b: set[str]) -> bool:
    """Two titles describe one event when they share most of their key words."""
    shared = len(a & b)
    return shared >= 2 and shared / min(len(a), len(b)) >= 0.5


def cluster_articles(articles: list[dict]) -> list[list[dict]]:
    """Group headlines about the same event (greedy, newest article first)."""
    clusters: list[tuple[set[str], list[dict]]] = []
    for article in articles:
        tokens = _tokens(str(article.get("title") or ""))
        for cluster_tokens, members in clusters:
            if tokens and _same_story(tokens, cluster_tokens):
                members.append(article)
                cluster_tokens |= tokens
                break
        else:
            clusters.append((set(tokens), [article]))
    return [members for _, members in clusters]


def themes_for(text: str) -> list[str]:
    tokens = _tokens(text)
    return [name for name, words in THEMES.items() if tokens & words]


def summarize_text(text: str | None, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    """The first sentence or two of ``text``, cut at a word under ``max_chars``."""
    if not text:
        return ""
    text = " ".join(str(text).split())
    summary = ""
    for sentence in _SENTENCE_END_RE.split(text):
        candidate = f"{summary} {sentence}".strip()
        if summary and len(candidate) > max_chars:
            break
        summary = candidate
        if len(summary) >= max_chars // 2:
            break
    if len(summary) > max_chars:
        summary = summary[: max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return summary


def _score_cluster(members: list[dict], now: datetime) -> float:
    outlets = {m.get("source") for m in members if m.get("source")}
    symbols = {s for m in members for s in m.get("symbols", [])}
    dates = [d for d in (_parse_date(m.get("date")) for m in members) if d]
    newest = max(dates) if dates else None
    age_hours = max((now - newest).total_seconds() / 3600, 0.0) if newest else 48.0
    recency = math.pow(0.5, age_hours / _RECENCY_HALF_LIFE_HOURS)
    titles = " ".join(str(m.get("title") or "") for m in members)
    scores = [
        abs(float(m["sentiment_score"]))
        for m in members
        if m.get("sentiment_score") is not None
    ]
    return (
        len(members)
        + 0.5 * max(len(outlets) - 1, 0)
        + 0.5 * max(len(symbols) - 1, 0)
        + (1.0 if themes_for(titles) else 0.0)
        + 3.0 * recency
        + (0.5 * sum(scores) / len(scores) if scores else 0.0)
    )


def _story(members: list[dict], score: float) -> dict:
    # Lead with the newest article that came with a summary to show.
    lead = next((m for m in members if m.get("excerpt")), members[0])
    scored = [
        float(m["sentiment_score"])
        for m in members
        if m.get("sentiment_score") is not None
    ]
    mean = round(sum(scored) / len(scored), 4) if scored else None
    labels = [m.get("sentiment_label") for m in members if m.get("sentiment_label")]
    label = max(set(labels), key=labels.count) if labels else None
    titles = " ".join(str(m.get("title") or "") for m in members)
    return {
        "title": lead.get("title"),
        "url": lead.get("url"),
        "source": lead.get("source"),
        "date": lead.get("date"),
        "summary": summarize_text(lead.get("excerpt")),
        "symbols": sorted({s for m in members for s in m.get("symbols", [])}),
        "sources": sorted({m.get("source") for m in members if m.get("source")}),
        "article_count": len(members),
        "themes": themes_for(titles),
        "sentiment_label": label,
        "sentiment_score": mean,
        "related": [
            {"title": m.get("title"), "url": m.get("url"), "source": m.get("source")}
            for m in members
            if m is not lead
        ],
        "score": round(score, 3),
    }


def build_digest(
    articles: list[dict], now: datetime | None = None, max_stories: int = 5
) -> dict:
    """Rank ``articles`` into top stories and count the themes they cover.

    :return: ``{top_stories, themes}``; ``themes`` is ``[{name, count}]``,
        most-covered first, counting each article once per theme.
    """
    now = now or datetime.now(timezone.utc)
    ranked = sorted(
        (
            (members, _score_cluster(members, now))
            for members in cluster_articles(articles)
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    counts: dict[str, int] = {}
    for article in articles:
        for name in themes_for(str(article.get("title") or "")):
            counts[name] = counts.get(name, 0) + 1
    return {
        "top_stories": [
            _story(members, score) for members, score in ranked[:max_stories]
        ],
        "themes": [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }
