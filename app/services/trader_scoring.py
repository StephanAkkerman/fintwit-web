"""Trader credibility scoring.

A "call" is a non-neutral-sentiment tweet mentioning a ticker — the tweet's
sentiment (from FinTwitBERT) stands in for a buy/sell opinion, and the
ticker's price at enrichment time (already computed for the tweet's
``assets`` payload) is the entry price. No separate signal-detection model
is needed: both inputs already exist on every enriched tweet.

Since a tweet's holding-period intent is unknown (a quick scalp vs. a long
thesis), each call is graded at several fixed horizons rather than one
guessed timeframe — a trader's accuracy can then be read out per horizon
instead of being blended into a single, ambiguous number.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker

#: Grading horizons, in days after the call. Kept small and fixed rather than
#: inferring per-tweet intent (short-term vs. long-term) from the text.
HORIZONS: tuple[int, ...] = (1, 7, 30)

#: Sentiment score thresholds a call must clear to count as directional,
#: mirroring the BULL/BEAR split already used for the mention widgets.
_BULLISH_MIN = 0.1
_BEARISH_MAX = -0.1

#: A graded move above this (an 11x in at most 30 days) is treated as a
#: pricing mismatch, not a real call outcome: the ticker re-priced as a
#: different asset than the one quoted at call time — typically a symbol
#: shared by several coins. A single such row used to drag a trader's average
#: return into the billions of percent. Losses are bounded at -100%, so they
#: can't blow up an average the same way and need no mirror-image cap.
MAX_PLAUSIBLE_RETURN_PCT = 1000.0

#: SQL predicate selecting the result rows (alias ``r``) that count towards a
#: score. The ``return_pct`` bound also screens rows graded before
#: ``excluded`` existed, so no data migration is needed.
_SCORED = (
    "(r.excluded IS NULL OR NOT r.excluded) "
    f"AND r.return_pct <= {MAX_PLAUSIBLE_RETURN_PCT}"
)

#: Direction-signed return: what following the call would have made.
_SIGNED_RETURN = (
    "CASE WHEN c.direction = 'bullish' THEN r.return_pct ELSE -r.return_pct END"
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value) -> datetime | None:
    """Normalize a tweet's ``created_at`` to the naive-UTC convention this
    project stores all timestamps in (see infra/repos.py)."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _direction(sentiment_score: float | None) -> str | None:
    if sentiment_score is None:
        return None
    if sentiment_score > _BULLISH_MIN:
        return "bullish"
    if sentiment_score < _BEARISH_MAX:
        return "bearish"
    return None


def extract_calls(tweet: dict) -> list[dict]:
    """Turn one enriched tweet dict into zero or more candidate call rows.

    A call is created per ticker the tweet mentions that also has a resolved
    price in ``tweet["assets"]`` — no extra price fetch is needed, both are
    already computed as part of normal tweet enrichment.

    :param tweet: A tweet payload shaped like the ``t_dict`` built in
        ``runtime/streamer.py`` (or an equivalent DB row dict).
    :return: Call dicts ready for ``TraderCallRepo.insert_calls`` (missing
        only ``created_at``, which the repo stamps).
    """
    tickers = tweet.get("tickers") or []
    if not tickers:
        return []

    # A tweet is not one opinion. "Long $NVDA, short $INTC" is a bullish call
    # on one and a bearish call on the other; grading both as bullish would
    # credit or punish the trader for a call they never made. The classifier
    # attributes a score per ticker where the tweet says different things
    # about them, and the tweet's own score stands for the rest.
    tweet_score = tweet.get("sentiment_score")
    per_ticker = tweet.get("ticker_sentiment") or {}
    if _direction(tweet_score) is None and not any(
        _direction(score) for score in per_ticker.values()
    ):
        return []

    called_at = _as_naive_utc(tweet.get("created_at"))
    if called_at is None:
        return []

    tweet_id = tweet.get("id")
    if tweet_id is None:
        return []

    user_screen_name = tweet.get("user_screen_name")
    if not user_screen_name:
        return []

    assets_by_symbol: dict[str, dict] = {}
    for asset in tweet.get("assets") or []:
        symbol = str(asset.get("symbol") or "").strip().upper()
        if symbol:
            assets_by_symbol[symbol] = asset

    seen: set[str] = set()
    calls: list[dict] = []
    for raw_ticker in tickers:
        ticker = str(raw_ticker or "").strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)

        score = per_ticker.get(ticker, tweet_score)
        direction = _direction(score)
        if direction is None:
            continue

        asset = assets_by_symbol.get(ticker)
        if not asset:
            continue

        price = (asset.get("financials") or {}).get("price")
        if not isinstance(price, (int, float)) or price <= 0:
            continue

        kind = asset.get("kind")
        calls.append(
            {
                "tweet_id": int(tweet_id),
                "ticker": ticker,
                "user_screen_name": user_screen_name,
                "direction": direction,
                "sentiment_score": float(score),
                "asset_kind": str(kind).upper() if kind else None,
                "price_at_call": float(price),
                "called_at": called_at,
            }
        )

    return calls


async def find_due_calls(
    Session: async_sessionmaker,
    horizon_days: int,
    limit: int = 200,
) -> list[dict]:
    """Calls at ``horizon_days`` old or older that have not been graded yet.

    :param horizon_days: One of :data:`HORIZONS`.
    :param limit: Maximum calls to return, oldest-due first.
    """
    cutoff = _now() - timedelta(days=horizon_days)

    sql = text("""
        SELECT c.id, c.ticker, c.user_screen_name, c.direction,
               c.price_at_call, c.asset_kind, c.called_at
        FROM trader_calls c
        LEFT JOIN trader_call_results r
               ON r.call_id = c.id AND r.horizon_days = :horizon
        WHERE r.id IS NULL AND c.called_at <= :cutoff
        ORDER BY c.called_at ASC
        LIMIT :limit
    """)

    async with Session() as s:
        result = await s.execute(
            sql, {"horizon": horizon_days, "cutoff": cutoff, "limit": limit}
        )
        rows = result.mappings().all()

    return [dict(r) for r in rows]


def is_plausible_return(return_pct: float | None) -> bool:
    """Whether a graded move is believable as the same asset's price change."""
    return return_pct is not None and return_pct <= MAX_PLAUSIBLE_RETURN_PCT


def grade_call(direction: str, price_at_call: float, price_now: float) -> dict:
    """Compute the return and correctness of one call against a later price.

    ``excluded`` flags a result that shouldn't count towards any score — see
    :data:`MAX_PLAUSIBLE_RETURN_PCT`.
    """
    if not price_at_call or price_at_call <= 0:
        return {"return_pct": 0.0, "correct": False, "excluded": True}
    return_pct = (price_now - price_at_call) / price_at_call * 100.0
    correct = return_pct > 0 if direction == "bullish" else return_pct < 0
    return {
        "return_pct": return_pct,
        "correct": correct,
        "excluded": not is_plausible_return(return_pct),
    }


async def get_leaderboard(
    Session: async_sessionmaker,
    horizon_days: int = 7,
    min_calls: int = 5,
    limit: int = 25,
) -> list[dict]:
    """Rank traders by hit-rate at a single horizon.

    :param horizon_days: One of :data:`HORIZONS`.
    :param min_calls: Minimum graded calls at this horizon to be ranked —
        keeps a single lucky/unlucky call from producing a 0% or 100% row.
    :param limit: Maximum traders to return.
    """
    sql = text(f"""
        SELECT
            c.user_screen_name AS user_screen_name,
            CAST(COUNT(*) AS INTEGER) AS graded_calls,
            CAST(SUM(CASE WHEN r.correct THEN 1 ELSE 0 END) AS INTEGER) AS correct_calls,
            AVG({_SIGNED_RETURN}) AS avg_return_pct
        FROM trader_call_results r
        JOIN trader_calls c ON c.id = r.call_id
        WHERE r.horizon_days = :horizon AND {_SCORED}
        GROUP BY c.user_screen_name
        HAVING COUNT(*) >= :min_calls
        ORDER BY
            CAST(SUM(CASE WHEN r.correct THEN 1 ELSE 0 END) AS REAL) / COUNT(*) DESC,
            graded_calls DESC
        LIMIT :limit
    """)

    async with Session() as s:
        result = await s.execute(
            sql, {"horizon": horizon_days, "min_calls": min_calls, "limit": limit}
        )
        rows = result.mappings().all()

    return [
        {
            "user_screen_name": r["user_screen_name"],
            "horizon_days": horizon_days,
            "graded_calls": r["graded_calls"],
            "correct_calls": r["correct_calls"],
            "hit_rate": r["correct_calls"] / r["graded_calls"],
            "avg_return_pct": r["avg_return_pct"],
        }
        for r in rows
    ]


#: Minimum graded calls at a horizon before the batched lookup (used for the
#: per-tweet inline badge) reports a trader at all — same rationale as
#: `get_leaderboard`'s `min_calls`, just a lower bar since this isn't a
#: competitive ranking, only a quick "is there any track record here" hint.
MIN_CALLS_FOR_BADGE = 3


async def get_credibility_batch(
    Session: async_sessionmaker,
    screen_names: list[str],
    horizon_days: int = 7,
) -> dict[str, dict]:
    """Hit-rate summaries for many traders at once, keyed by lowercased handle.

    Built for the tweet-card credibility badge: one batched lookup per visible
    page of authors instead of one request per card. Traders with fewer than
    :data:`MIN_CALLS_FOR_BADGE` graded calls at this horizon are omitted
    entirely rather than returned with a misleadingly certain 0%/100%.

    :param screen_names: Author handles to look up (case-insensitive).
    :param horizon_days: One of :data:`HORIZONS`.
    :return: ``{lowercased_screen_name: {graded_calls, correct_calls,
        hit_rate, avg_return_pct}}`` — missing keys mean no qualifying
        track record yet.
    """
    names = sorted({n.strip().lower() for n in screen_names if n and n.strip()})
    if not names:
        return {}

    sql = text(f"""
        SELECT
            LOWER(c.user_screen_name) AS user_screen_name,
            CAST(COUNT(*) AS INTEGER) AS graded_calls,
            CAST(SUM(CASE WHEN r.correct THEN 1 ELSE 0 END) AS INTEGER) AS correct_calls,
            AVG({_SIGNED_RETURN}) AS avg_return_pct
        FROM trader_call_results r
        JOIN trader_calls c ON c.id = r.call_id
        WHERE r.horizon_days = :horizon AND {_SCORED}
          AND LOWER(c.user_screen_name) IN :names
        GROUP BY LOWER(c.user_screen_name)
        HAVING COUNT(*) >= :min_calls
    """).bindparams(bindparam("names", expanding=True))

    async with Session() as s:
        result = await s.execute(
            sql,
            {
                "horizon": horizon_days,
                "names": names,
                "min_calls": MIN_CALLS_FOR_BADGE,
            },
        )
        rows = result.mappings().all()

    return {
        r["user_screen_name"]: {
            "horizon_days": horizon_days,
            "graded_calls": r["graded_calls"],
            "correct_calls": r["correct_calls"],
            "hit_rate": r["correct_calls"] / r["graded_calls"],
            "avg_return_pct": r["avg_return_pct"],
        }
        for r in rows
    }


async def get_trader_detail(
    Session: async_sessionmaker,
    user_screen_name: str,
    horizon_days: int = 7,
    recent_limit: int = 50,
) -> dict:
    """Per-horizon accuracy, per-ticker breakdown and recent calls for one trader.

    Unlike :func:`get_leaderboard`, this has no minimum-sample floor — it is
    a profile view for one already-chosen trader, not a fairness-adjusted
    ranking.

    :param horizon_days: One of :data:`HORIZONS`; the horizon the per-ticker
        hit-rate and average return are graded at.
    :param recent_limit: Maximum recent calls to return, newest first.
    :return: ``{user_screen_name, horizon_days, summary, horizons, tickers,
        recent_calls}``. Each recent call carries the text/url of the tweet it
        came from when that tweet is still stored, and a ``results[]`` entry
        per horizon already graded (``excluded`` marks a result left out of
        the scores as a pricing mismatch).
    """
    params = {"user": user_screen_name}

    by_horizon_sql = text(f"""
        SELECT
            r.horizon_days AS horizon_days,
            CAST(COUNT(*) AS INTEGER) AS graded_calls,
            CAST(SUM(CASE WHEN r.correct THEN 1 ELSE 0 END) AS INTEGER) AS correct_calls,
            AVG({_SIGNED_RETURN}) AS avg_return_pct
        FROM trader_call_results r
        JOIN trader_calls c ON c.id = r.call_id
        WHERE LOWER(c.user_screen_name) = LOWER(:user) AND {_SCORED}
        GROUP BY r.horizon_days
    """)

    summary_sql = text("""
        SELECT
            CAST(COUNT(*) AS INTEGER) AS total_calls,
            CAST(SUM(CASE WHEN direction = 'bullish' THEN 1 ELSE 0 END) AS INTEGER)
                AS bullish_calls,
            CAST(SUM(CASE WHEN direction = 'bearish' THEN 1 ELSE 0 END) AS INTEGER)
                AS bearish_calls,
            CAST(COUNT(DISTINCT ticker) AS INTEGER) AS distinct_tickers,
            MIN(called_at) AS first_called_at,
            MAX(called_at) AS last_called_at
        FROM trader_calls
        WHERE LOWER(user_screen_name) = LOWER(:user)
    """)

    # The scored filter sits in the ON clause so a ticker whose calls are all
    # still pending (or excluded) keeps its row, just with nothing graded.
    tickers_sql = text(f"""
        SELECT
            c.ticker AS ticker,
            MAX(c.asset_kind) AS asset_kind,
            CAST(COUNT(*) AS INTEGER) AS calls,
            CAST(SUM(CASE WHEN c.direction = 'bullish' THEN 1 ELSE 0 END) AS INTEGER)
                AS bullish_calls,
            CAST(SUM(CASE WHEN c.direction = 'bearish' THEN 1 ELSE 0 END) AS INTEGER)
                AS bearish_calls,
            MAX(c.called_at) AS last_called_at,
            CAST(COUNT(r.id) AS INTEGER) AS graded_calls,
            CAST(SUM(CASE WHEN r.correct THEN 1 ELSE 0 END) AS INTEGER) AS correct_calls,
            AVG(CASE WHEN r.id IS NULL THEN NULL ELSE {_SIGNED_RETURN} END)
                AS avg_return_pct
        FROM trader_calls c
        LEFT JOIN trader_call_results r
               ON r.call_id = c.id AND r.horizon_days = :horizon AND {_SCORED}
        WHERE LOWER(c.user_screen_name) = LOWER(:user)
        GROUP BY c.ticker
        ORDER BY calls DESC, last_called_at DESC
        LIMIT 50
    """)

    calls_sql = text("""
        SELECT c.id, c.tweet_id, c.ticker, c.direction, c.sentiment_score,
               c.asset_kind, c.price_at_call, c.called_at,
               t.text AS tweet_text, t.url AS tweet_url
        FROM trader_calls c
        LEFT JOIN tweets t ON t.id = c.tweet_id
        WHERE LOWER(c.user_screen_name) = LOWER(:user)
        ORDER BY c.called_at DESC, c.id DESC
        LIMIT :limit
    """)

    async with Session() as s:
        by_horizon_rows = (await s.execute(by_horizon_sql, params)).mappings().all()
        summary_row = (await s.execute(summary_sql, params)).mappings().first()
        ticker_rows = (
            (await s.execute(tickers_sql, {**params, "horizon": horizon_days}))
            .mappings()
            .all()
        )
        call_rows = (
            (await s.execute(calls_sql, {**params, "limit": recent_limit}))
            .mappings()
            .all()
        )
        call_ids = [r["id"] for r in call_rows]
        results_by_call: dict[int, list[dict]] = {}
        if call_ids:
            results_sql = text(
                "SELECT call_id, horizon_days, price_at_horizon, return_pct, "
                "correct, excluded, evaluated_at FROM trader_call_results "
                "WHERE call_id IN :call_ids"
            ).bindparams(bindparam("call_ids", expanding=True))
            result_rows = (
                (await s.execute(results_sql, {"call_ids": call_ids})).mappings().all()
            )
            for r in result_rows:
                results_by_call.setdefault(r["call_id"], []).append(
                    {
                        "horizon_days": r["horizon_days"],
                        "price_at_horizon": r["price_at_horizon"],
                        "return_pct": r["return_pct"],
                        "correct": bool(r["correct"]),
                        "excluded": bool(r["excluded"])
                        or not is_plausible_return(r["return_pct"]),
                        "evaluated_at": str(r["evaluated_at"]),
                    }
                )

    horizons = {
        h: {
            "horizon_days": h,
            "graded_calls": 0,
            "correct_calls": 0,
            "hit_rate": None,
            "avg_return_pct": None,
        }
        for h in HORIZONS
    }
    for r in by_horizon_rows:
        h = int(r["horizon_days"])
        if h not in horizons:
            continue
        graded = r["graded_calls"]
        horizons[h] = {
            "horizon_days": h,
            "graded_calls": graded,
            "correct_calls": r["correct_calls"],
            "hit_rate": r["correct_calls"] / graded if graded else None,
            "avg_return_pct": r["avg_return_pct"],
        }

    summary_row = summary_row or {}
    summary = {
        "total_calls": summary_row.get("total_calls") or 0,
        "bullish_calls": summary_row.get("bullish_calls") or 0,
        "bearish_calls": summary_row.get("bearish_calls") or 0,
        "distinct_tickers": summary_row.get("distinct_tickers") or 0,
        "first_called_at": _str_or_none(summary_row.get("first_called_at")),
        "last_called_at": _str_or_none(summary_row.get("last_called_at")),
    }

    tickers = [
        {
            "ticker": r["ticker"],
            "asset_kind": r["asset_kind"],
            "calls": r["calls"],
            "bullish_calls": r["bullish_calls"],
            "bearish_calls": r["bearish_calls"],
            "last_called_at": _str_or_none(r["last_called_at"]),
            "graded_calls": r["graded_calls"],
            "correct_calls": r["correct_calls"] or 0,
            "hit_rate": (
                (r["correct_calls"] or 0) / r["graded_calls"]
                if r["graded_calls"]
                else None
            ),
            "avg_return_pct": r["avg_return_pct"],
        }
        for r in ticker_rows
    ]

    recent_calls = [
        {
            "id": r["id"],
            "tweet_id": r["tweet_id"],
            "ticker": r["ticker"],
            "direction": r["direction"],
            "sentiment_score": r["sentiment_score"],
            "asset_kind": r["asset_kind"],
            "price_at_call": r["price_at_call"],
            "called_at": str(r["called_at"]),
            "tweet_text": r["tweet_text"],
            "tweet_url": r["tweet_url"],
            "results": sorted(
                results_by_call.get(r["id"], []), key=lambda x: x["horizon_days"]
            ),
        }
        for r in call_rows
    ]

    return {
        "user_screen_name": user_screen_name,
        "horizon_days": horizon_days,
        "summary": summary,
        "horizons": [horizons[h] for h in HORIZONS],
        "tickers": tickers,
        "recent_calls": recent_calls,
    }


def _str_or_none(value) -> str | None:
    return None if value is None else str(value)
