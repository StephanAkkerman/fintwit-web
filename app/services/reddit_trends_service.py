"""Reddit trend scraping via the `reddit-stock-analyzer` package (issue #6).

The scraping, ticker recognition and sentiment all live in
`reddit-stock-analyzer <https://github.com/StephanAkkerman/reddit-stock-analyzer>`_,
which is the extracted and tested version of this pipeline. This module is the
adapter: it owns the single long-lived service object, keeps the import lazy,
and turns the package's dataclasses into the JSON the API serves.

Two things are deliberate here.

The import is lazy because the package depends on ``stock-recognizer``, which
pulls in torch — the same reason ``app/ml`` imports inside functions. It is
therefore absent from the ``[test]`` extra, and every entry point below
degrades to an empty result rather than raising when it cannot be imported, so
a deployment without the ML stack still boots and serves every other route.

Nothing here is called per request. A report scrapes several subreddits and
runs two models over every post, which is far too slow for a request to wait
on; `app/runtime/reddit_trends.py` computes it on an interval and the API
serves the stored result.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: Subreddits scraped when no explicit list is configured. Overridable with
#: the ``REDDIT_SUBREDDITS`` env var (comma-separated) so a deployment can
#: widen or narrow the scrape without a code change.
DEFAULT_WINDOW_HOURS = 24.0

#: Posts requested per subreddit per listing. Reddit caps a listing at 100.
DEFAULT_LIMIT = 50

_service: Any = None
_unavailable = False


class RedditAnalyzerUnavailable(RuntimeError):
    """Raised when `reddit-stock-analyzer` is not installed."""


def _load_service() -> Any:
    """Build the shared ``RedditTrendService``, once per process.

    The service owns an HTTP session and two loaded models (ticker recognition
    and sentiment), so rebuilding it per call would re-read the recognizer's
    market-data snapshot every time.

    :raises RedditAnalyzerUnavailable: If the package cannot be imported.
    """
    global _service, _unavailable

    if _service is not None:
        return _service
    if _unavailable:
        raise RedditAnalyzerUnavailable(
            "reddit-stock-analyzer is not installed; Reddit trend analysis is off"
        )

    try:
        from reddit_stock_analyzer import RedditClient, RedditTrendService
    except ImportError as exc:
        _unavailable = True
        logger.warning(
            "[reddit-trends] reddit-stock-analyzer not installed (%s); "
            "trend analysis is disabled",
            exc,
        )
        raise RedditAnalyzerUnavailable(str(exc)) from exc

    logger.info("[reddit-trends] building RedditTrendService")
    _service = RedditTrendService(client=RedditClient())
    return _service


def is_available() -> bool:
    """Whether trend analysis can run in this deployment."""
    try:
        _load_service()
    except RedditAnalyzerUnavailable:
        return False
    return True


def reset_service() -> None:
    """Drop the cached service (used by tests)."""
    global _service, _unavailable
    _service = None
    _unavailable = False


def default_subreddits() -> list[str]:
    """The subreddits a scrape covers by default.

    Reads ``REDDIT_SUBREDDITS`` (comma-separated) first, then the package's own
    curated default, then a hard-coded fallback so the caller always gets a
    usable list even with the package absent.
    """
    import os

    configured = os.getenv("REDDIT_SUBREDDITS", "").strip()
    if configured:
        return [name.strip() for name in configured.split(",") if name.strip()]

    try:
        from reddit_stock_analyzer import DEFAULT_SUBREDDITS

        return list(DEFAULT_SUBREDDITS)
    except ImportError:
        return ["wallstreetbets", "stocks", "StockMarket", "investing"]


def subreddit_categories() -> dict[str, list[str]]:
    """The package's subreddit catalogue, grouped by kind of discussion.

    Empty when the package is absent — the API surfaces that as an empty
    catalogue rather than an error, so the UI can still render.
    """
    try:
        from reddit_stock_analyzer import SUBREDDIT_CATEGORIES
    except ImportError:
        return {}
    return {name: list(subs) for name, subs in SUBREDDIT_CATEGORIES.items()}


def resolve_subreddits(
    subreddits: Sequence[str] | None = None, category: str | None = None
) -> list[str]:
    """Work out which subreddits to scrape.

    :param subreddits: An explicit list, which wins when given.
    :param category: A catalogue category name (``retail``, ``trading``...).
    :raises KeyError: If *category* is not in the catalogue.
    """
    if subreddits:
        return [str(name).strip() for name in subreddits if str(name).strip()]

    if category:
        from reddit_stock_analyzer import subreddits_for

        return list(subreddits_for(category))

    return default_subreddits()


async def fetch_trend_report(
    subreddits: Sequence[str] | None = None,
    *,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    baseline_hours: float | None = None,
    limit: int = DEFAULT_LIMIT,
    top_n: int = 25,
) -> dict[str, Any]:
    """Scrape, analyse and rank — the expensive call the worker makes.

    :returns: ``TrendReport.to_dict()``: ranked tickers with mention counts,
        momentum, spike scores and per-ticker sentiment, plus the
        rising/emerging/fading shortlists and per-subreddit breakdown.
    :raises RedditAnalyzerUnavailable: If the package is not installed.
    """
    service = _load_service()
    targets = resolve_subreddits(subreddits)

    report = await service.trend_report(
        targets,
        window_hours=window_hours,
        baseline_hours=baseline_hours,
        limit=limit,
        top_n=top_n,
    )
    logger.info(
        "[reddit-trends] ranked %d tickers from %d posts across %d subreddit(s)",
        len(report.tickers),
        report.posts_analyzed,
        len(targets),
    )
    return report.to_dict()


async def fetch_subreddit_summary(
    subreddit: str, *, limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """Ticker and sentiment snapshot for a single subreddit.

    Cheaper than a trend report — one listing, no baseline window, no momentum
    — so this one is affordable on request.

    :raises RedditAnalyzerUnavailable: If the package is not installed.
    """
    service = _load_service()
    return await service.subreddit_overview(subreddit, limit=limit)


async def warmup() -> None:
    """Load both models ahead of the first scrape, best-effort."""
    try:
        service = _load_service()
    except RedditAnalyzerUnavailable:
        return

    import asyncio

    try:
        await asyncio.to_thread(service.analyzer.warm_up)
    except Exception as exc:  # pragma: no cover - model loading is environmental
        logger.warning("[reddit-trends] model warmup failed: %r", exc)


async def close() -> None:
    """Release the shared service's HTTP session."""
    global _service
    if _service is not None:
        try:
            await _service.close()
        except Exception as exc:  # pragma: no cover - shutdown best-effort
            logger.warning("[reddit-trends] service close failed: %r", exc)
        _service = None
