"""Background worker that scrapes finance subreddits and ranks tickers (issue #6).

A trend report costs several subreddit listings plus two model passes over
every post, so it is computed here on an interval and stored; the API serves
the stored result rather than making a request wait for a scrape.

Storing each run rather than overwriting one is what gives the per-ticker
history its depth — a live scrape can only ever see as far back as the posts
still sitting on the listing pages.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..infra.repos import RedditTrendRepo
from ..services.reddit_trends_service import (
    RedditAnalyzerUnavailable,
    fetch_trend_report,
    warmup,
)

logger = logging.getLogger(__name__)

#: 15 minutes. Comfortably inside Reddit's rate limits for a handful of
#: subreddits, and mention counts do not move meaningfully faster than that.
DEFAULT_INTERVAL = 900

_MIN_BACKOFF = 60
_MAX_BACKOFF = 1800

#: Runs older than this are dropped on each pass, so the table stays bounded.
DEFAULT_RETENTION_DAYS = 90

#: What the worker is doing right now, served alongside the stored run so the
#: UI can say *why* there is nothing to show. Without it a scrape that raises
#: on every pass (a model that will not load, Reddit answering 403) reads as
#: "waiting for the first scrape" forever, and the only trace is a log line.
_status: dict = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_status() -> None:
    """Back to the never-started state (used by tests and at worker start)."""
    _status.clear()
    _status.update(
        {
            "state": "idle",
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error": None,
            "last_posts_analyzed": None,
            "next_attempt_at": None,
        }
    )


def _set_status(**fields) -> None:
    _status.update(fields)


def worker_status() -> dict:
    """A copy of the worker's current status.

    ``state`` is one of ``idle`` (never started, e.g. disabled), ``warming_up``,
    ``scraping``, ``ok``, ``empty`` (Reddit returned no posts), ``error`` (the
    last pass raised; ``last_error`` says what) or ``unavailable`` (the
    analyzer package is not installed).
    """
    return dict(_status)


reset_status()


async def capture_trends(
    repo: RedditTrendRepo,
    *,
    window_hours: float = 24.0,
    limit: int = 50,
    top_n: int = 25,
) -> dict | None:
    """Run one scrape-and-rank pass and persist it.

    :return: The stored report, or ``None`` when the scrape found no posts —
        every subreddit request failing should not write an empty run that
        would then read as "nothing is being discussed".
    :raises RedditAnalyzerUnavailable: If the analyzer package is missing.
    """
    report = await fetch_trend_report(
        window_hours=window_hours, limit=limit, top_n=top_n
    )
    if not report.get("posts_analyzed"):
        logger.warning("[reddit-trends] scrape returned no posts; not storing a run")
        return None

    await repo.save_report(report)
    return report


async def run_reddit_trends(
    repo: RedditTrendRepo,
    interval: int = DEFAULT_INTERVAL,
    *,
    window_hours: float = 24.0,
    limit: int = 50,
    top_n: int = 25,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> None:
    """Capture a trend report every ``interval`` seconds.

    Skips the scrape when a run already exists within half the interval, so an
    app restart loop cannot hammer Reddit or flood the table.

    :param repo: Where runs are stored.
    :param interval: Seconds between scrapes.
    :param window_hours: Length of the trend window (and of its baseline).
    :param limit: Posts requested per subreddit per listing.
    :param top_n: Tickers kept per run.
    :param retention_days: Runs older than this are pruned.
    """
    reset_status()
    _set_status(state="warming_up")
    await warmup()

    backoff = _MIN_BACKOFF
    min_gap = timedelta(seconds=max(interval // 2, 60))

    while True:
        try:
            latest = await repo.latest_run(limit=1)
            captured = latest.get("captured_at") if latest else None
            recent = False
            if captured:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(captured)
                recent = age < min_gap

            if recent:
                logger.debug("[reddit-trends] recent run exists, skipping this pass")
                _set_status(state="ok", last_success_at=captured)
            else:
                _set_status(state="scraping", last_attempt_at=_now_iso())
                report = await capture_trends(
                    repo, window_hours=window_hours, limit=limit, top_n=top_n
                )
                if report is None:
                    _set_status(
                        state="empty",
                        last_posts_analyzed=0,
                        last_error=(
                            "Reddit returned no posts. It may be rate limiting or "
                            "blocking this server; configure REDDIT_CLIENT_ID and "
                            "REDDIT_CLIENT_SECRET to scrape authenticated."
                        ),
                    )
                else:
                    _set_status(
                        state="ok",
                        last_success_at=_now_iso(),
                        last_error=None,
                        last_posts_analyzed=report.get("posts_analyzed", 0),
                    )
                    top = report.get("tickers") or []
                    logger.info(
                        "[reddit-trends] stored run: %d tickers from %d posts, top=%s",
                        len(top),
                        report.get("posts_analyzed", 0),
                        ", ".join(t["symbol"] for t in top[:5]) or "none",
                    )
                    await repo.prune(keep_days=retention_days)

            backoff = _MIN_BACKOFF

        except RedditAnalyzerUnavailable as exc:
            # Nothing to retry: the package will not appear mid-process. Stop
            # the worker rather than logging the same failure every interval.
            logger.warning(
                "[reddit-trends] reddit-stock-analyzer is not installed; "
                "trend worker stopping"
            )
            _set_status(state="unavailable", last_error=str(exc), next_attempt_at=None)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "[reddit-trends] iteration failed (%r); retrying in %ds",
                exc,
                backoff,
                exc_info=True,
            )
            _set_status(
                state="error",
                last_error=f"{type(exc).__name__}: {exc}",
                next_attempt_at=(
                    datetime.now(timezone.utc) + timedelta(seconds=backoff)
                ).isoformat(),
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
            continue

        _set_status(
            next_attempt_at=(
                datetime.now(timezone.utc) + timedelta(seconds=interval)
            ).isoformat()
        )
        await asyncio.sleep(interval)
