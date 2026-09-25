"""On-demand SQL aggregation over the tweets table using SQLite json_each()."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import async_sessionmaker


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _score_to_label(score: float | None) -> str:
    if score is None:
        return "NEUTRAL"
    if score > 0.1:
        return "BULL"
    if score < -0.1:
        return "BEAR"
    return "NEUTRAL"


# Appended after an existing HAVING clause. References ae.value which is
# produced by the per-function LEFT JOIN on json_each(t.assets) matched by symbol.
#
# The ticker-classifier emits `kind` in mixed forms — e.g. "crypto" (lowercase
# from its resolve path) and "CRYPTOCURRENCY" (Yahoo quoteType) for crypto;
# "EQUITY" / "ETF" / "INDEX" / "FUTURE" / "COMMODITY" for stock-like; "forex"
# (lowercase) for FX. Match case-insensitively and group equity-like kinds.
_KIND_FILTER = {
    "CRYPTO": (
        "AND UPPER(MAX(json_extract(ae.value, '$.kind'))) "
        "IN ('CRYPTO', 'CRYPTOCURRENCY')"
    ),
    "EQUITY": (
        "AND UPPER(MAX(json_extract(ae.value, '$.kind'))) "
        "IN ('EQUITY', 'ETF', 'INDEX', 'FUTURE', 'COMMODITY', 'MUTUALFUND')"
    ),
    "FOREX": "AND UPPER(MAX(json_extract(ae.value, '$.kind'))) = 'FOREX'",
}


def _user_clause(user_screen_name: str | None) -> str:
    if not user_screen_name:
        return ""
    return (
        "AND ("
        "  LOWER(t.user_screen_name) LIKE :user_name_pat"
        "  OR LOWER(t.user_name) LIKE :user_name_pat"
        "  OR LOWER(json_extract(t.quoted_tweet, '$.user_screen_name')) LIKE :user_name_pat"
        ")"
    )


def _subscriber_clause(subscriber_only: bool) -> str:
    if not subscriber_only:
        return ""
    return (
        "AND ("
        "  t.is_subscriber_only = 1"
        "  OR json_extract(t.quoted_tweet, '$.is_subscriber_only') = 1"
        ")"
    )


# Per-author cap applied when computing get_mention_heat's ranking score
# (issue #101): one account retweeting/spamming a ticker shouldn't be able to
# out-rank a ticker genuinely mentioned by several distinct people. Each
# author contributes at most this many mentions toward the score; raw
# `mentions` is still returned unclipped for display.
AUTHOR_MENTION_CAP = 3


async def get_mention_heat(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    limit: int = 50,
    min_mentions: int = 1,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
    """Return the top-mentioned tickers in the last ``window_hours`` hours.

    Ranking uses a fairness-adjusted ``mention_score`` rather than raw
    ``mentions`` (issue #101): each author's contribution to a ticker is
    capped at ``AUTHOR_MENTION_CAP`` before summing, so one account
    retweeting/spamming a ticker can't out-rank a ticker genuinely spread
    across several distinct authors. ``mentions`` and ``unique_authors`` are
    still returned uncapped so callers can see the raw numbers.

    ``price_direction`` is the point-to-point % return over the window:
    ``(most_recent_price - nearest_to_cutoff_price) / nearest_to_cutoff_price * 100``.

    Both prices come from a single ``prices`` CTE bounded to
    ``[cutoff - window_hours, now]`` — the window again before the cutoff, so a
    ticker whose last pre-window mention is somewhat stale still anchors
    against a real pre-window price. Bounding it matters: an unbounded scan
    costs O(all tweets ever) per request, and because the heatmap only ever
    displays the last 24h-7d that cost is pure waste that grows forever (see
    the "Performance" note below).

    When a ticker has no priced mention in that lookback, ``price_at_start``
    falls back to the earliest in-window one, making ``price_direction``
    reflect an intra-window range rather than a window-anchored return. This
    is acceptable; the alternative is returning NULL, which would hide
    tickers that have only been tracked recently. Conversely, a ticker whose
    only priced mentions predate the lookback now yields NULL rather than
    anchoring on an arbitrarily old price — anchoring a "24h move" to a price
    from months ago produced a number that was worse than no number.

    Performance
    -----------
    The price lookup drives off ``json_each(t.assets)`` alone and takes the
    ticker from the asset's own ``$.symbol``, rather than expanding
    ``json_each(t.tickers)`` and joining ``json_each(t.assets)`` onto it. The
    two are equivalent here — ``streamer.py`` builds ``assets`` from
    ``tickers`` (``asset_symbols = [*tickers]``), so every asset symbol comes
    from ``tickers``, and the outer ``LEFT JOIN`` on ``m.ticker`` discards
    anything not in the mention set anyway — but it avoids a nested loop per
    row.
    """
    now = _now()
    cutoff = now - timedelta(hours=window_hours)
    # Price lookback: the window again before the cutoff, so `price_at_start`
    # can reach a real pre-window price without scanning all of history.
    price_floor = now - timedelta(hours=window_hours * 2)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        WITH
        -- One bounded pass over priced assets, shared by both price CTEs so
        -- the tweets table is scanned once rather than twice.
        prices AS (
            SELECT
                json_extract(ae.value, '$.symbol') AS ticker,
                t.created_at AS created_at,
                json_extract(ae.value, '$.financials.price') AS price
            FROM tweets t, json_each(t.assets) ae
            WHERE t.created_at >= :price_floor
              AND json_extract(ae.value, '$.financials.price') IS NOT NULL
        ),
        price_recent AS (
            SELECT
                ticker,
                price,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY created_at DESC
                ) AS rn
            FROM prices
        ),
        price_at_start AS (
            SELECT
                ticker,
                price,
                ROW_NUMBER() OVER (
                    PARTITION BY ticker
                    ORDER BY ABS(julianday(created_at) - julianday(:cutoff))
                ) AS rn
            FROM prices
        ),
        mentions AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions,
                AVG(t.sentiment_score) AS avg_sentiment_24h,
                MAX(json_extract(ae.value, '$.kind')) AS asset_kind
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE t.created_at >= :cutoff
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
            GROUP BY j.value
            HAVING COUNT(*) >= :min_mentions
            {kind_clause}
        ),
        author_mentions AS (
            SELECT
                LOWER(t.user_screen_name) AS author,
                j.value AS ticker,
                COUNT(*) AS author_mentions
            FROM tweets t, json_each(t.tickers) j
            WHERE t.created_at >= :cutoff
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
            GROUP BY author, j.value
        ),
        fair_score AS (
            SELECT
                ticker,
                CAST(COUNT(*) AS INTEGER) AS unique_authors,
                CAST(SUM(MIN(author_mentions, :author_cap)) AS INTEGER) AS mention_score
            FROM author_mentions
            GROUP BY ticker
        )
        SELECT
            m.ticker,
            m.mentions,
            m.avg_sentiment_24h,
            m.asset_kind,
            fs.unique_authors,
            fs.mention_score,
            CASE
                WHEN pr.price IS NOT NULL
                 AND ps.price IS NOT NULL
                 AND ps.price != 0
                THEN (pr.price - ps.price) / ps.price * 100.0
                ELSE NULL
            END AS price_direction
        FROM mentions m
        JOIN fair_score fs ON fs.ticker = m.ticker
        LEFT JOIN (SELECT ticker, price FROM price_recent WHERE rn = 1) pr ON pr.ticker = m.ticker
        LEFT JOIN (SELECT ticker, price FROM price_at_start WHERE rn = 1) ps ON ps.ticker = m.ticker
        ORDER BY fs.mention_score DESC
        LIMIT :limit
    """)

    params: dict = {
        "cutoff": cutoff,
        "price_floor": price_floor,
        "limit": limit,
        "min_mentions": min_mentions,
        "author_cap": AUTHOR_MENTION_CAP,
    }
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions": r["mentions"],
            "unique_authors": r["unique_authors"],
            "mention_score": r["mention_score"],
            "avg_sentiment_24h": r["avg_sentiment_24h"] or 0.0,
            "sentiment_label_24h": _score_to_label(r["avg_sentiment_24h"]),
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
            "price_direction": r["price_direction"],
        }
        for r in rows
    ]


async def get_sentiment_shift(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    limit: int = 10,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
    """Rank tickers by absolute change in average sentiment between the active
    window and the prior baseline. Returns the top `limit` movers, no
    categorical-label-change filter — sentiment scores can cluster on one side
    of zero (e.g. probability outputs), so a strict label flip would hide real
    movement.

    The "prior" baseline is everything in the lookback span before c_now (not
    a strict equal-length window), so the widget still produces results when
    there are gaps in the prior equal-length slice but earlier history exists.
    """
    now = _now()
    cutoff_now = now - timedelta(hours=window_hours)
    cutoff_span = now - timedelta(hours=max(window_hours * 2, 24 * 7))
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c_now THEN 1 ELSE 0 END) AS INTEGER) AS mentions_now,
            AVG(CASE WHEN t.created_at >= :c_now THEN t.sentiment_score ELSE NULL END) AS avg_now,
            AVG(CASE WHEN t.created_at <  :c_now THEN t.sentiment_score ELSE NULL END) AS avg_prev,
            MAX(json_extract(ae.value, '$.kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        LEFT JOIN json_each(t.assets) ae
               ON json_extract(ae.value, '$.symbol') = j.value
        WHERE t.created_at >= :c_span
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
          {user_c}
          {sub_c}
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c_now THEN 1 ELSE 0 END) > 0
          AND AVG(CASE WHEN t.created_at >= :c_now THEN t.sentiment_score ELSE NULL END) IS NOT NULL
          AND AVG(CASE WHEN t.created_at <  :c_now THEN t.sentiment_score ELSE NULL END) IS NOT NULL
        {kind_clause}
    """)

    params: dict = {"c_span": cutoff_span, "c_now": cutoff_now}
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    items = []
    for r in rows:
        avg_now = r["avg_now"]
        avg_prev = r["avg_prev"]
        delta = avg_now - avg_prev
        items.append(
            {
                "ticker": r["ticker"],
                "mentions_24h": r["mentions_now"],
                "avg_sentiment_24h": avg_now,
                "avg_sentiment_prev": avg_prev,
                "delta": delta,
                "sentiment_label_24h": _score_to_label(avg_now),
                "sentiment_label_prev": _score_to_label(avg_prev),
                "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
            }
        )

    items.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return items[:limit]


async def get_volume_baseline(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    threshold: float = 1.5,
    window_hours: int = 24,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
    now = _now()
    # Baseline span = 4× the active window, floored at 7d.
    # This ensures spikes are detectable even when window_hours = 168 (7d).
    baseline_hours = max(24 * 7, 4 * window_hours)
    cutoff_span = now - timedelta(hours=baseline_hours)
    cutoff_now = now - timedelta(hours=window_hours)
    # Number of `window_hours`-sized buckets in the baseline span; used to
    # express the baseline as the *expected* mentions per active window.
    buckets = baseline_hours / float(window_hours)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c_now THEN 1 ELSE 0 END) AS INTEGER) AS mentions_now,
            COUNT(*) / :buckets AS baseline_avg,
            CASE WHEN COUNT(*) > 0
                 THEN SUM(CASE WHEN t.created_at >= :c_now THEN 1.0 ELSE 0 END) / (COUNT(*) / :buckets)
                 ELSE NULL END AS volume_multiplier,
            MAX(json_extract(ae.value, '$.kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        LEFT JOIN json_each(t.assets) ae
               ON json_extract(ae.value, '$.symbol') = j.value
        WHERE t.created_at >= :c_span
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
          {user_c}
          {sub_c}
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c_now THEN 1 ELSE 0 END) > 5
          AND (COUNT(*) / :buckets) > 0
          AND SUM(CASE WHEN t.created_at >= :c_now THEN 1.0 ELSE 0 END) / (COUNT(*) / :buckets) > :thr
        {kind_clause}
        ORDER BY volume_multiplier DESC
        LIMIT 10
    """)

    params: dict = {
        "c_span": cutoff_span,
        "c_now": cutoff_now,
        "thr": threshold,
        "buckets": buckets,
    }
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_now"],
            "baseline_7d_avg": r["baseline_avg"],
            "volume_multiplier": r["volume_multiplier"],
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
        }
        for r in rows
    ]


# Tweet-level counterpart of _KIND_FILTER: a tweet belongs to an asset kind
# when any of its assets does. Used where rows are tweets, not tickers.
_TWEET_KIND_FILTER = {
    "CRYPTO": "('CRYPTO', 'CRYPTOCURRENCY')",
    "EQUITY": "('EQUITY', 'ETF', 'INDEX', 'FUTURE', 'COMMODITY', 'MUTUALFUND')",
    "FOREX": "('FOREX')",
}


def _tweet_kind_clause(asset_kind: str) -> str:
    kinds = _TWEET_KIND_FILTER.get(asset_kind.upper())
    if kinds is None:
        return ""
    return (
        "AND EXISTS ("
        "  SELECT 1 FROM json_each(t.assets) ae"
        f"  WHERE UPPER(json_extract(ae.value, '$.kind')) IN {kinds}"
        ")"
    )


def _bull_pct(bull: int, bear: int) -> float | None:
    directional = bull + bear
    if directional == 0:
        return None
    return bull / directional * 100.0


def _ticker_summary(item: dict) -> dict:
    return {
        "ticker": item["ticker"],
        "mentions": item["mentions"],
        "unique_authors": item["unique_authors"],
        "avg_sentiment": item["avg_sentiment_24h"],
        "sentiment_label": item["sentiment_label_24h"],
        "asset_kind": item["asset_kind"],
        "price_direction": item["price_direction"],
    }


async def get_activity_summary(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> dict:
    """Summarise tweet activity in the active window against the one before.

    Returns tweet and distinct-author counts plus the bull/bear split for both
    the current window ``[now - window_hours, now)`` and the equal-length
    previous one, so the frontend can show deltas. Tweets are classified by
    ``sentiment_score`` with the same thresholds as ``_score_to_label``;
    ``bull_pct`` is bull / (bull + bear), ``None`` when no tweet was
    directional.

    ``top_ticker`` is the leader of ``get_mention_heat`` (fairness-adjusted
    ranking), and ``top_mover`` is the ticker with the largest absolute
    ``price_direction`` among the heat list, so both answer to the same
    filters as the rest of the overview. Either is ``None`` when there is
    nothing to show.
    """
    now = _now()
    c_now = now - timedelta(hours=window_hours)
    c_prev = now - timedelta(hours=window_hours * 2)
    kind_c = _tweet_kind_clause(asset_kind)
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        SELECT
            CAST(SUM(CASE WHEN t.created_at >= :c_now THEN 1 ELSE 0 END) AS INTEGER) AS tweets_now,
            CAST(SUM(CASE WHEN t.created_at <  :c_now THEN 1 ELSE 0 END) AS INTEGER) AS tweets_prev,
            COUNT(DISTINCT CASE WHEN t.created_at >= :c_now THEN LOWER(t.user_screen_name) END) AS authors_now,
            COUNT(DISTINCT CASE WHEN t.created_at <  :c_now THEN LOWER(t.user_screen_name) END) AS authors_prev,
            CAST(SUM(CASE WHEN t.created_at >= :c_now AND t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS INTEGER) AS bull_now,
            CAST(SUM(CASE WHEN t.created_at >= :c_now AND t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS INTEGER) AS bear_now,
            CAST(SUM(CASE WHEN t.created_at <  :c_now AND t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS INTEGER) AS bull_prev,
            CAST(SUM(CASE WHEN t.created_at <  :c_now AND t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS INTEGER) AS bear_prev
        FROM tweets t
        WHERE t.created_at >= :c_prev
          {kind_c}
          {user_c}
          {sub_c}
    """)

    params: dict = {"c_now": c_now, "c_prev": c_prev}
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        row = result.mappings().one()

    counts = {k: row[k] or 0 for k in row.keys()}

    heat = await get_mention_heat(
        Session,
        asset_kind=asset_kind,
        window_hours=window_hours,
        user_screen_name=user_screen_name,
        subscriber_only=subscriber_only,
    )
    top_ticker = _ticker_summary(heat[0]) if heat else None
    priced = [h for h in heat if h["price_direction"] is not None]
    top_mover = (
        _ticker_summary(max(priced, key=lambda h: abs(h["price_direction"])))
        if priced
        else None
    )

    return {
        "window_hours": window_hours,
        "tweets": {"current": counts["tweets_now"], "previous": counts["tweets_prev"]},
        "authors": {
            "current": counts["authors_now"],
            "previous": counts["authors_prev"],
        },
        "sentiment": {
            "bull": counts["bull_now"],
            "bear": counts["bear_now"],
            "bull_pct": _bull_pct(counts["bull_now"], counts["bear_now"]),
            "prev_bull_pct": _bull_pct(counts["bull_prev"], counts["bear_prev"]),
        },
        "top_ticker": top_ticker,
        "top_mover": top_mover,
    }


async def get_hidden_gems(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
    """Surface newly-appeared or resurfacing tickers in the active window.

    Ordering uses the same fairness-adjusted ``mention_score`` as
    ``get_mention_heat`` (issue #101): each author's contribution is capped
    at ``AUTHOR_MENTION_CAP`` before summing, so one account bursting
    retweets on a ticker can't push it to the top — or push genuinely
    multi-author gems out of the ``LIMIT 20`` cutoff. Unlike
    ``get_mention_heat`` there is no minimum-mentions floor: a single
    early mention is the whole point of a "hidden gem", so it isn't
    filtered out — it just won't outrank gems several people are talking
    about.

    Classification
    --------------
    A ticker mentioned in the active window qualifies as a gem exactly when
    it has no mention in the *quiet zone* ``[c_resurface, c_now)``. From
    there ``gem_subtype`` follows from whether any older mention exists:
    ``resurfacing`` if one does, ``new`` if none ever has.

    That is the same classification the previous, more literal formulation
    made — ``first_seen >= c_now`` for new, ``last_seen_before_window <
    c_resurface`` for resurfacing — restated so it can be answered without
    an all-time ``MIN(created_at)`` per ticker. The old form computed that
    aggregate for *every* ticker on *every* request by expanding
    ``json_each(tickers)`` across the whole table, which made this endpoint
    scale with total tweet volume: measured at a fixed ingest rate with
    identical recent data, it went from 11ms at 30 days of history to 139ms
    at 360 days and 461ms at 1200 days, all of it that one scan.

    Now the quiet-zone check is a bounded window, and the only unbounded
    question — "has this ticker ever been mentioned before?" — is asked of
    the ``ticker_mentions`` index for the handful of candidates that get
    that far, as a seek on ``(ticker, created_at)``. The same measurement
    holds flat at ~1.3ms regardless of history depth.
    """
    now = _now()
    cutoff_now = now - timedelta(hours=window_hours)
    # "Resurfacing" means the prior occurrence is at least one full lookback
    # window further back than the active window — and never less than 7 days.
    cutoff_resurface = now - timedelta(hours=max(window_hours * 7, 24 * 7))

    _kind_upper = asset_kind.upper()
    if _kind_upper == "CRYPTO":
        kind_filter = "AND UPPER(a.asset_kind) IN ('CRYPTO', 'CRYPTOCURRENCY')"
    elif _kind_upper == "EQUITY":
        kind_filter = (
            "AND UPPER(a.asset_kind) IN ('EQUITY', 'ETF', 'INDEX', "
            "'FUTURE', 'COMMODITY', 'MUTUALFUND')"
        )
    elif _kind_upper == "FOREX":
        kind_filter = "AND UPPER(a.asset_kind) = 'FOREX'"
    else:
        kind_filter = ""

    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    # The `ticker_mentions` lookups below only need `tweets` when a user or
    # subscriber filter has to be applied; without one, the index answers
    # alone and the join is pure overhead.
    tm_join = "JOIN tweets t ON t.id = tm.tweet_id" if (user_c or sub_c) else ""

    sql = text(f"""
        WITH active AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions_now,
                MIN(t.created_at) AS first_in_window,
                MAX(json_extract(ae.value, '$.kind')) AS asset_kind
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE t.created_at >= :c_now
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
            GROUP BY j.value
        ),
        -- Any mention in the quiet zone [c_resurface, c_now) disqualifies a
        -- ticker: it is neither new nor has it been away long enough.
        quiet AS (
            SELECT DISTINCT tm.ticker
            FROM ticker_mentions tm
            {tm_join}
            WHERE tm.created_at >= :c_resurface
              AND tm.created_at < :c_now
              {user_c}
              {sub_c}
        ),
        candidates AS (
            SELECT a.*
            FROM active a
            WHERE a.ticker NOT IN (SELECT ticker FROM quiet)
        ),
        -- History before the quiet zone, for candidates only. Seeks the
        -- `(ticker, created_at)` index per candidate instead of expanding
        -- every tweet in the table, so cost tracks the handful of candidates
        -- rather than how much history has piled up.
        prior AS (
            SELECT
                tm.ticker AS ticker,
                MIN(tm.created_at) AS first_seen,
                MAX(tm.created_at) AS last_seen_before_window
            FROM ticker_mentions tm
            {tm_join}
            WHERE tm.created_at < :c_resurface
              AND tm.ticker IN (SELECT ticker FROM candidates)
              {user_c}
              {sub_c}
            GROUP BY tm.ticker
        ),
        author_mentions AS (
            SELECT
                LOWER(t.user_screen_name) AS author,
                j.value AS ticker,
                COUNT(*) AS author_mentions
            FROM tweets t, json_each(t.tickers) j
            WHERE t.created_at >= :c_now
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
            GROUP BY author, j.value
        ),
        fair_score AS (
            SELECT
                ticker,
                CAST(COUNT(*) AS INTEGER) AS unique_authors,
                CAST(SUM(MIN(author_mentions, :author_cap)) AS INTEGER) AS mention_score
            FROM author_mentions
            GROUP BY ticker
        )
        SELECT
            a.ticker,
            a.mentions_now,
            a.asset_kind,
            -- All-time first mention. A candidate has nothing in the quiet
            -- zone, so its earliest pre-window mention (if any) is also its
            -- earliest ever; a genuinely new ticker starts in this window.
            COALESCE(p.first_seen, a.first_in_window) AS first_seen,
            p.last_seen_before_window,
            fs.unique_authors,
            fs.mention_score,
            -- No pre-quiet-zone history at all means the ticker has never
            -- been seen before this window.
            CASE
                WHEN p.ticker IS NULL THEN 'new'
                ELSE 'resurfacing'
            END AS gem_subtype,
            CASE
                WHEN p.last_seen_before_window IS NOT NULL
                THEN CAST(
                    (julianday('now') - julianday(p.last_seen_before_window))
                    AS INTEGER)
                ELSE NULL
            END AS days_since_last
        FROM candidates a
        JOIN fair_score fs ON fs.ticker = a.ticker
        LEFT JOIN prior p ON p.ticker = a.ticker
        WHERE 1 = 1
          {kind_filter}
        ORDER BY fs.mention_score DESC
        LIMIT 20
    """)

    params: dict = {
        "c_now": cutoff_now,
        "c_resurface": cutoff_resurface,
        "author_cap": AUTHOR_MENTION_CAP,
    }
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_now"],
            "unique_authors": r["unique_authors"],
            "mention_score": r["mention_score"],
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
            "gem_subtype": r["gem_subtype"],
            "days_since_last": r["days_since_last"],
            "first_seen": str(r["first_seen"]) if r["first_seen"] else None,
            "last_seen": str(r["last_seen_before_window"])
            if r["last_seen_before_window"]
            else None,
        }
        for r in rows
    ]


# Sector/industry trend classification (issue #146): compares the active
# window's mention count against the same-length window immediately before
# it. Kept deliberately simple (absolute + relative thresholds) rather than
# reusing `_derive_stat`'s per-ticker machinery, since sectors only need the
# four buckets the issue asks for plus a quiet default.
SECTOR_RARE_MENTIONS = 3  # fewer than this in the window barely registers
SECTOR_HOT_MENTIONS = 20  # high absolute volume this window
SECTOR_TREND_THRESHOLD = 0.3  # |Δ| vs prior window to flag rising/cooling


def _sector_trend(mentions: int, prev_mentions: int) -> str:
    """Classify a sector/industry's momentum: hot, rising, cooling, rare, or steady."""
    if mentions < SECTOR_RARE_MENTIONS:
        return "rare"
    if prev_mentions <= 0:
        return "hot" if mentions >= SECTOR_HOT_MENTIONS else "rising"
    pct_change = (mentions - prev_mentions) / prev_mentions
    if mentions >= SECTOR_HOT_MENTIONS and pct_change >= SECTOR_TREND_THRESHOLD:
        return "hot"
    if pct_change >= SECTOR_TREND_THRESHOLD:
        return "rising"
    if pct_change <= -SECTOR_TREND_THRESHOLD:
        return "cooling"
    return "steady"


async def get_sector_mentions(
    Session: async_sessionmaker,
    window_hours: int = 24,
    limit: int = 15,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
    """Aggregate ticker mentions by equity sector and industry (issue #104).

    Surfaces which sectors — and, within a sector, which industries — are
    getting talked about the most, so a cluster of mentions across several
    tickers (e.g. "Technology > Semiconductors") reads as a sector-level
    trend rather than scattered per-ticker noise. Only assets with resolved
    sector metadata are counted; sector/industry is populated by
    ticker-classifier for equities/ETFs only, so crypto and forex tickers
    are excluded here (unlike the other mention endpoints).

    Ranking uses the same fairness-adjusted ``mention_score`` as
    ``get_mention_heat`` (issue #101): each author's contribution to a
    sector is capped at ``AUTHOR_MENTION_CAP`` before summing, so one
    account spamming a sector's tickers can't out-rank a sector genuinely
    discussed by several distinct authors.

    Each sector and industry also carries a momentum ``trend`` (issue #146:
    ``hot``/``rising``/``cooling``/``rare``/``steady``) derived from
    ``mentions`` vs. ``prev_mentions`` — the same-length window immediately
    before the active one — so the frontend can render an emoji/colour cue
    without re-deriving it client-side.
    """
    now = _now()
    cutoff = now - timedelta(hours=window_hours)
    prev_cutoff = cutoff - timedelta(hours=window_hours)
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        WITH ticker_sector AS (
            SELECT
                t.user_screen_name AS author,
                t.sentiment_score AS sentiment_score,
                j.value AS ticker,
                json_extract(ae.value, '$.sector') AS sector,
                json_extract(ae.value, '$.industry') AS industry
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE t.created_at >= :cutoff
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
        ),
        sector_scoped AS (
            SELECT * FROM ticker_sector WHERE sector IS NOT NULL AND sector != ''
        ),
        ticker_rollup AS (
            SELECT
                sector,
                COALESCE(NULLIF(industry, ''), 'Other') AS industry,
                ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions,
                AVG(sentiment_score) AS avg_sentiment
            FROM sector_scoped
            GROUP BY sector, industry, ticker
        ),
        author_sector AS (
            SELECT
                LOWER(author) AS author,
                sector,
                COUNT(*) AS author_mentions
            FROM sector_scoped
            GROUP BY author, sector
        ),
        fair_score AS (
            SELECT
                sector,
                CAST(COUNT(*) AS INTEGER) AS unique_authors,
                CAST(SUM(MIN(author_mentions, :author_cap)) AS INTEGER) AS mention_score
            FROM author_sector
            GROUP BY sector
        )
        SELECT
            tr.sector, tr.industry, tr.ticker, tr.mentions, tr.avg_sentiment,
            fs.unique_authors, fs.mention_score
        FROM ticker_rollup tr
        JOIN fair_score fs ON fs.sector = tr.sector
    """)

    # Prior-window mention counts per sector/industry, for the `trend` field.
    # A separate, lighter query rather than folding into the main one above:
    # it only needs raw counts (no fairness score, no ticker breakdown), so
    # it stays a simple GROUP BY over the same-length window immediately
    # before `cutoff`.
    prior_sql = text(f"""
        SELECT
            json_extract(ae.value, '$.sector') AS sector,
            COALESCE(NULLIF(json_extract(ae.value, '$.industry'), ''), 'Other') AS industry,
            CAST(COUNT(*) AS INTEGER) AS mentions
        FROM tweets t, json_each(t.tickers) j
        LEFT JOIN json_each(t.assets) ae
               ON json_extract(ae.value, '$.symbol') = j.value
        WHERE t.created_at >= :prev_cutoff AND t.created_at < :cutoff
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
          AND json_extract(ae.value, '$.sector') IS NOT NULL
          AND json_extract(ae.value, '$.sector') != ''
          {user_c}
          {sub_c}
        GROUP BY sector, industry
    """)

    params: dict = {"cutoff": cutoff, "author_cap": AUTHOR_MENTION_CAP}
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()
        result = await s.execute(prior_sql, {**params, "prev_cutoff": prev_cutoff})
        prior_rows = result.mappings().all()

    prior_sector_mentions: dict[str, int] = {}
    prior_industry_mentions: dict[tuple[str, str], int] = {}
    for r in prior_rows:
        mentions = int(r["mentions"])
        prior_sector_mentions[r["sector"]] = (
            prior_sector_mentions.get(r["sector"], 0) + mentions
        )
        key = (r["sector"], r["industry"])
        prior_industry_mentions[key] = prior_industry_mentions.get(key, 0) + mentions

    sectors: dict[str, dict] = {}
    for r in rows:
        sector = sectors.setdefault(
            r["sector"],
            {
                "sector": r["sector"],
                "mentions": 0,
                "mention_score": r["mention_score"],
                "unique_authors": r["unique_authors"],
                "sentiment_sum": 0.0,
                "tickers": {},
                "industries": {},
            },
        )
        mentions = int(r["mentions"])
        sector["mentions"] += mentions
        sector["sentiment_sum"] += (r["avg_sentiment"] or 0.0) * mentions
        sector["tickers"][r["ticker"]] = (
            sector["tickers"].get(r["ticker"], 0) + mentions
        )

        industry = sector["industries"].setdefault(
            r["industry"], {"industry": r["industry"], "mentions": 0, "tickers": {}}
        )
        industry["mentions"] += mentions
        industry["tickers"][r["ticker"]] = (
            industry["tickers"].get(r["ticker"], 0) + mentions
        )

    def _top_tickers(ticker_counts: dict[str, int], n: int) -> list[dict]:
        ranked = sorted(ticker_counts.items(), key=lambda kv: kv[1], reverse=True)
        return [{"ticker": t, "mentions": m} for t, m in ranked[:n]]

    out = []
    for sector in sectors.values():
        avg_sentiment = (
            sector["sentiment_sum"] / sector["mentions"] if sector["mentions"] else 0.0
        )
        industries = sorted(
            sector["industries"].values(), key=lambda i: i["mentions"], reverse=True
        )
        sector_prev = prior_sector_mentions.get(sector["sector"], 0)
        out.append(
            {
                "sector": sector["sector"],
                "mentions": sector["mentions"],
                "mention_score": sector["mention_score"],
                "unique_authors": sector["unique_authors"],
                "unique_tickers": len(sector["tickers"]),
                "avg_sentiment_24h": avg_sentiment,
                "sentiment_label_24h": _score_to_label(avg_sentiment),
                "top_tickers": _top_tickers(sector["tickers"], 5),
                "prev_mentions": sector_prev,
                "pct_change": (
                    (sector["mentions"] - sector_prev) / sector_prev
                    if sector_prev > 0
                    else None
                ),
                "trend": _sector_trend(sector["mentions"], sector_prev),
                "industries": [
                    {
                        "industry": i["industry"],
                        "mentions": i["mentions"],
                        "unique_tickers": len(i["tickers"]),
                        "top_tickers": _top_tickers(i["tickers"], 3),
                        "trend": _sector_trend(
                            i["mentions"],
                            prior_industry_mentions.get(
                                (sector["sector"], i["industry"]), 0
                            ),
                        ),
                    }
                    for i in industries
                ],
            }
        )

    out.sort(key=lambda s: s["mention_score"], reverse=True)
    return out[:limit]


def _choose_bucket_hours(window_hours: int) -> int:
    """Pick a bucket width that keeps a ticker's timeseries chart readable."""
    if window_hours <= 48:
        return 1
    if window_hours <= 168:
        return 6
    return 24


async def get_ticker_timeseries(
    Session: async_sessionmaker,
    ticker: str,
    window_hours: int = 168,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> dict:
    """Bucketed mention/sentiment history for a single ticker, plus a summary.

    Bucket width scales with the window (hourly under 48h, 6-hourly up to 7d,
    daily beyond) so the chart stays readable at any lookback. Buckets with no
    mentions are zero-filled across the full window so the chart has no gaps.
    """
    now = _now()
    cutoff = now - timedelta(hours=window_hours)
    bucket_hours = _choose_bucket_hours(window_hours)
    bucket_seconds = bucket_hours * 3600
    ticker_u = ticker.strip().upper()
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    params: dict = {
        "ticker": ticker_u,
        "cutoff": cutoff,
        "bucket_seconds": bucket_seconds,
    }
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    buckets_sql = text(f"""
        SELECT
            CAST(strftime('%s', t.created_at) AS INTEGER) / :bucket_seconds
                * :bucket_seconds AS bucket_epoch,
            CAST(COUNT(*) AS INTEGER) AS mentions,
            SUM(CASE WHEN t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS bullish,
            SUM(CASE WHEN t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS bearish,
            AVG(t.sentiment_score) AS avg_sentiment
        FROM tweets t, json_each(t.tickers) j
        WHERE UPPER(j.value) = :ticker
          AND t.created_at >= :cutoff
          {user_c}
          {sub_c}
        GROUP BY bucket_epoch
    """)

    summary_sql = text(f"""
        SELECT
            CAST(COUNT(*) AS INTEGER) AS total_mentions,
            SUM(CASE WHEN t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS bullish,
            SUM(CASE WHEN t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS bearish,
            AVG(t.sentiment_score) AS avg_sentiment,
            COUNT(DISTINCT LOWER(t.user_screen_name)) AS unique_authors,
            SUM(CASE WHEN t.has_chart = 1 THEN 1 ELSE 0 END) AS chart_mentions,
            AVG(COALESCE(t.likes, 0) + COALESCE(t.retweets, 0) + COALESCE(t.replies, 0))
                AS avg_engagement,
            MAX(json_extract(ae.value, '$.kind')) AS asset_kind,
            MIN(t.created_at) AS first_seen,
            MAX(t.created_at) AS last_seen
        FROM tweets t, json_each(t.tickers) j
        LEFT JOIN json_each(t.assets) ae
               ON UPPER(json_extract(ae.value, '$.symbol')) = UPPER(j.value)
        WHERE UPPER(j.value) = :ticker
          AND t.created_at >= :cutoff
          {user_c}
          {sub_c}
    """)

    price_sql = text("""
        SELECT
            (SELECT json_extract(ae.value, '$.financials.price')
             FROM tweets t, json_each(t.assets) ae
             WHERE UPPER(json_extract(ae.value, '$.symbol')) = :ticker
               AND json_extract(ae.value, '$.financials.price') IS NOT NULL
             ORDER BY t.created_at DESC LIMIT 1) AS price_recent,
            (SELECT json_extract(ae.value, '$.financials.price')
             FROM tweets t, json_each(t.assets) ae
             WHERE UPPER(json_extract(ae.value, '$.symbol')) = :ticker
               AND json_extract(ae.value, '$.financials.price') IS NOT NULL
             ORDER BY ABS(julianday(t.created_at) - julianday(:cutoff)) LIMIT 1)
                AS price_at_start
    """)

    async with Session() as s:
        result = await s.execute(buckets_sql, params)
        bucket_rows = result.mappings().all()
        result = await s.execute(summary_sql, params)
        summary_row = result.mappings().first()
        result = await s.execute(price_sql, {"ticker": ticker_u, "cutoff": cutoff})
        price_row = result.mappings().first()

    by_bucket = {int(r["bucket_epoch"]): r for r in bucket_rows}

    start_epoch = (
        int(cutoff.replace(tzinfo=timezone.utc).timestamp())
        // bucket_seconds
        * bucket_seconds
    )
    end_epoch = (
        int(now.replace(tzinfo=timezone.utc).timestamp())
        // bucket_seconds
        * bucket_seconds
    )

    points = []
    epoch = start_epoch
    while epoch <= end_epoch:
        row = by_bucket.get(epoch)
        mentions = int(row["mentions"]) if row else 0
        bullish = int(row["bullish"] or 0) if row else 0
        bearish = int(row["bearish"] or 0) if row else 0
        points.append(
            {
                "bucket": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
                "mentions": mentions,
                "bullish": bullish,
                "bearish": bearish,
                "neutral": max(mentions - bullish - bearish, 0),
                "avg_sentiment": row["avg_sentiment"] if row else None,
            }
        )
        epoch += bucket_seconds

    total_mentions = int(summary_row["total_mentions"] or 0) if summary_row else 0
    bullish_total = int(summary_row["bullish"] or 0) if summary_row else 0
    bearish_total = int(summary_row["bearish"] or 0) if summary_row else 0
    avg_sentiment = summary_row["avg_sentiment"] if summary_row else None

    price_recent = price_row["price_recent"] if price_row else None
    price_start = price_row["price_at_start"] if price_row else None
    price_direction = None
    if price_recent is not None and price_start not in (None, 0):
        price_direction = (price_recent - price_start) / price_start * 100.0

    asset_kind = (
        summary_row["asset_kind"].upper()
        if summary_row and summary_row["asset_kind"]
        else None
    )

    return {
        "ticker": ticker_u,
        "window_hours": window_hours,
        "bucket_hours": bucket_hours,
        "points": points,
        "summary": {
            "total_mentions": total_mentions,
            "avg_mentions_per_bucket": (
                total_mentions / len(points) if points else 0.0
            ),
            "bullish": bullish_total,
            "bearish": bearish_total,
            "neutral": max(total_mentions - bullish_total - bearish_total, 0),
            "avg_sentiment": avg_sentiment,
            "sentiment_label": _score_to_label(avg_sentiment),
            "unique_authors": int(summary_row["unique_authors"] or 0)
            if summary_row
            else 0,
            "chart_mentions": int(summary_row["chart_mentions"] or 0)
            if summary_row
            else 0,
            "avg_engagement": summary_row["avg_engagement"] if summary_row else None,
            "asset_kind": asset_kind,
            "price_direction": price_direction,
            "first_seen": str(summary_row["first_seen"])
            if summary_row and summary_row["first_seen"]
            else None,
            "last_seen": str(summary_row["last_seen"])
            if summary_row and summary_row["last_seen"]
            else None,
        },
    }


async def get_extended_hours_stats(
    Session: async_sessionmaker,
    since_dt: datetime,
    until_dt: datetime,
    top_n: int = 10,
) -> dict:
    """Aggregate tweet-ticker mentions in a fixed window for the extended-hours panel."""
    sql = text("""
        SELECT
            j.value AS ticker,
            CAST(COUNT(*) AS INTEGER) AS mentions,
            SUM(CASE WHEN t.sentiment_score >  0.1 THEN 1 ELSE 0 END) AS bull_count,
            SUM(CASE WHEN t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS bear_count
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :since_dt
          AND t.created_at <  :until_dt
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        ORDER BY mentions DESC
    """)

    async with Session() as s:
        result = await s.execute(sql, {"since_dt": since_dt, "until_dt": until_dt})
        rows = result.mappings().all()

    total_bull = sum(int(r["bull_count"] or 0) for r in rows)
    total_bear = sum(int(r["bear_count"] or 0) for r in rows)
    total_mentions = sum(int(r["mentions"]) for r in rows)

    top_tickers = []
    for r in rows[:top_n]:
        bull = int(r["bull_count"] or 0)
        bear = int(r["bear_count"] or 0)
        sentiment = "BULL" if bull > bear else ("BEAR" if bear > bull else "NEUTRAL")
        top_tickers.append(
            {
                "ticker": r["ticker"],
                "mentions": int(r["mentions"]),
                "sentiment": sentiment,
            }
        )

    return {
        "total_mentions": total_mentions,
        "top_tickers": top_tickers,
        "sentiment_distribution": {
            "BULL": total_bull,
            "BEAR": total_bear,
            "NEUTRAL": total_mentions - total_bull - total_bear,
        },
    }


# ─── Per-tweet mention frequency (personal + global) ──────────────────────────
#
# Powers the "Mentions" strip on each tweet card. For every (author, ticker)
# we compute, over the last ``WINDOW_DAYS`` days, how often the author (personal
# scope) and everyone (global scope) mentions that ticker, plus a primary
# ``signal`` and a sentiment ``stance``. Both scopes share the same aggregate
# shape; only the grouping / filtering and the "hot" threshold differ.

WINDOW_DAYS = 30
HOT_PERSONAL = 8  # ≈ twice a week over 30d
HOT_GLOBAL = 100
TREND_THRESHOLD = 0.25  # |Δ| vs prior window to flag 📈 / 📉
RANK_MIN_MENTIONS = 2  # min mentions for a #1 rank to read as 🥇
STANCE_MIN = 3  # min sentiment-bearing mentions to assign a stance
STANCE_FRAC = 0.6  # share of one side needed for a decisive stance

# Conditional aggregates shared by the personal and global queries. References
# the ``t`` (tweets) alias and binds :w_start / :prev_start.
_FREQ_AGG_COLS = """
    SUM(CASE WHEN t.created_at >= :w_start THEN 1 ELSE 0 END) AS mentions,
    SUM(CASE WHEN t.created_at >= :prev_start AND t.created_at < :w_start
             THEN 1 ELSE 0 END) AS prev_mentions,
    MIN(t.created_at) AS first_seen,
    MAX(CASE WHEN t.created_at < :w_start THEN t.created_at ELSE NULL END) AS last_before,
    SUM(CASE WHEN t.created_at >= :w_start AND t.sentiment_score > 0.1
             THEN 1 ELSE 0 END) AS bull,
    SUM(CASE WHEN t.created_at >= :w_start AND t.sentiment_score < -0.1
             THEN 1 ELSE 0 END) AS bear,
    SUM(CASE WHEN t.created_at >= :w_start AND t.sentiment_score IS NOT NULL
             THEN 1 ELSE 0 END) AS stance_total,
    SUM(CASE WHEN t.created_at >= :prev_start AND t.created_at < :w_start
             AND t.sentiment_score > 0.1 THEN 1 ELSE 0 END) AS prev_bull,
    SUM(CASE WHEN t.created_at >= :prev_start AND t.created_at < :w_start
             AND t.sentiment_score < -0.1 THEN 1 ELSE 0 END) AS prev_bear,
    SUM(CASE WHEN t.created_at >= :prev_start AND t.created_at < :w_start
             AND t.sentiment_score IS NOT NULL THEN 1 ELSE 0 END) AS prev_total
"""


def _as_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _direction(
    bull: int, bear: int, total: int, min_total: int = STANCE_MIN
) -> str | None:
    """Simple majority lean, used for the prior-window flip comparison."""
    if total < min_total:
        return None
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return None


def _stance(bull: int, bear: int, total: int) -> str | None:
    """Decisive stance over the active window (needs a clear ≥60% majority)."""
    if total < STANCE_MIN:
        return None
    if bull >= STANCE_FRAC * total and bull > bear:
        return "bullish"
    if bear >= STANCE_FRAC * total and bear > bull:
        return "bearish"
    if bull > 0 and bear > 0:
        return "mixed"
    return None


def _derive_stat(
    row: dict, now: datetime, w_start: datetime, hot_threshold: int
) -> dict:
    """Turn a raw aggregate row into a ``TickerScopeStat`` payload."""
    mentions = int(row.get("mentions") or 0)
    prev_mentions = int(row.get("prev_mentions") or 0)
    rank = int(row["rnk"]) if row.get("rnk") is not None else None
    bull = int(row.get("bull") or 0)
    bear = int(row.get("bear") or 0)
    stance_total = int(row.get("stance_total") or 0)
    prev_bull = int(row.get("prev_bull") or 0)
    prev_bear = int(row.get("prev_bear") or 0)
    prev_total = int(row.get("prev_total") or 0)

    first_seen = _as_dt(row.get("first_seen"))
    last_before = _as_dt(row.get("last_before"))

    is_new = first_seen is not None and first_seen >= w_start
    days_since_last = (now - last_before).days if last_before is not None else None
    # Resurfacing = quiet through the entire prior window then back. Requiring an
    # empty prior window (rather than just an old last_before) keeps it disjoint
    # from the trend signal, which needs prior-window activity to compare against.
    is_resurfacing = not is_new and prev_mentions == 0 and last_before is not None

    pct_change = (
        (mentions - prev_mentions) / prev_mentions if prev_mentions > 0 else None
    )

    # Single primary signal by precedence: novelty → rank → volume → trend.
    if mentions <= 0:
        signal = "neutral"
    elif is_new:
        signal = "new"
    elif is_resurfacing:
        signal = "resurfacing"
    elif rank == 1 and mentions >= RANK_MIN_MENTIONS:
        signal = "top"
    elif mentions >= hot_threshold:
        signal = "hot"
    elif pct_change is not None and abs(pct_change) >= TREND_THRESHOLD:
        signal = "rising" if pct_change > 0 else "falling"
    else:
        signal = "neutral"

    stance = _stance(bull, bear, stance_total)
    cur_dir = _direction(bull, bear, stance_total)
    prev_dir = _direction(prev_bull, prev_bear, prev_total)
    stance_flipped = bool(cur_dir and prev_dir and cur_dir != prev_dir)

    return {
        "mentions": mentions,
        "prev_mentions": prev_mentions,
        "signal": signal,
        "pct_change": pct_change,
        "rank": rank,
        "days_since_last": days_since_last,
        "first_ever": is_new,
        "stance": stance,
        "stance_bull": bull,
        "stance_bear": bear,
        "stance_total": stance_total,
        "stance_flipped": stance_flipped,
        "notable": signal != "neutral" or stance_flipped,
    }


async def get_mention_frequency(
    Session: async_sessionmaker,
    requests: list[dict],
    window_days: int = WINDOW_DAYS,
) -> dict:
    """Batch per-(author, ticker) mention-frequency stats for the tweet feed.

    ``requests`` is a list of ``{"author": str, "tickers": [str]}``. Returns
    ``{"personal": {author: {ticker: stat}}, "global": {ticker: stat}}`` where
    each ``stat`` is a ``TickerScopeStat``. Personal rank is computed across all
    of the author's tickers; global rank across all tickers in the window.
    """
    cleaned = [r for r in (requests or []) if r.get("author") and r.get("tickers")]
    now = _now()
    w_start = now - timedelta(days=window_days)
    prev_start = now - timedelta(days=2 * window_days)

    authors = sorted({r["author"].lower() for r in cleaned})
    tickers = sorted({t.upper() for r in cleaned for t in r["tickers"]})
    if not authors and not tickers:
        return {"personal": {}, "global": {}}

    time_params = {"w_start": w_start, "prev_start": prev_start}

    # ── Personal: one row per (author, ticker) across all of the author's
    #    history, ranked within each author by active-window mentions.
    personal_rows: dict[tuple[str, str], dict] = {}
    if authors:
        personal_sql = text(
            f"""
            WITH agg AS (
                SELECT LOWER(t.user_screen_name) AS author, j.value AS ticker,
                {_FREQ_AGG_COLS}
                FROM tweets t, json_each(t.tickers) j
                WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
                  AND LOWER(t.user_screen_name) IN :authors
                GROUP BY author, j.value
            )
            SELECT agg.*,
                   RANK() OVER (PARTITION BY author ORDER BY mentions DESC) AS rnk
            FROM agg
            """
        ).bindparams(bindparam("authors", expanding=True))
        async with Session() as s:
            res = await s.execute(personal_sql, {**time_params, "authors": authors})
            for m in res.mappings().all():
                key = (str(m["author"]).lower(), str(m["ticker"]).upper())
                personal_rows[key] = dict(m)

    # ── Global: rank across all tickers (window-bounded), plus full-history
    #    aggregates for just the requested tickers.
    global_rows: dict[str, dict] = {}
    if tickers:
        rank_sql = text(
            """
            SELECT j.value AS ticker, COUNT(*) AS mentions,
                   RANK() OVER (ORDER BY COUNT(*) DESC) AS rnk
            FROM tweets t, json_each(t.tickers) j
            WHERE t.created_at >= :w_start
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
            """
        )
        agg_sql = text(
            f"""
            SELECT UPPER(j.value) AS ticker,
            {_FREQ_AGG_COLS}
            FROM tweets t, json_each(t.tickers) j
            WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
              AND UPPER(j.value) IN :tickers
            GROUP BY UPPER(j.value)
            """
        ).bindparams(bindparam("tickers", expanding=True))
        async with Session() as s:
            res = await s.execute(rank_sql, {"w_start": w_start})
            rank_map = {
                str(m["ticker"]).upper(): m["rnk"] for m in res.mappings().all()
            }
            res = await s.execute(agg_sql, {**time_params, "tickers": tickers})
            for m in res.mappings().all():
                tk = str(m["ticker"]).upper()
                d = dict(m)
                d["rnk"] = rank_map.get(tk)
                global_rows[tk] = d

    personal_out: dict[str, dict] = {}
    for r in cleaned:
        author = r["author"]
        a_lower = author.lower()
        bucket = personal_out.setdefault(author, {})
        for tk in r["tickers"]:
            tku = tk.upper()
            row = personal_rows.get((a_lower, tku))
            if row is not None:
                bucket[tku] = _derive_stat(row, now, w_start, HOT_PERSONAL)

    global_out = {
        tk: _derive_stat(row, now, w_start, HOT_GLOBAL)
        for tk, row in global_rows.items()
    }

    return {"personal": personal_out, "global": global_out}
