"""On-demand SQL aggregation over the tweets table using SQLite json_each()."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
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

    ``price_direction`` is the point-to-point % return over the window:
    ``(most_recent_price - nearest_to_cutoff_price) / nearest_to_cutoff_price * 100``.

    Both price CTEs search all tweets with no time restriction so that sparse
    data still produces a price estimate. A side-effect: when a ticker has no
    pre-window tweets, ``price_at_start`` falls back to the earliest in-window
    tweet, making ``price_direction`` reflect an intra-window range rather than
    a window-anchored return. This is acceptable; the alternative is returning
    NULL, which would hide tickers that have only been tracked recently.
    """
    now = _now()
    cutoff = now - timedelta(hours=window_hours)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")
    user_c = _user_clause(user_screen_name)
    sub_c = _subscriber_clause(subscriber_only)

    sql = text(f"""
        WITH
        price_recent AS (
            SELECT
                j.value AS ticker,
                json_extract(ae.value, '$.financials.price') AS price,
                ROW_NUMBER() OVER (
                    PARTITION BY j.value
                    ORDER BY t.created_at DESC
                ) AS rn
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
        ),
        price_at_start AS (
            SELECT
                j.value AS ticker,
                json_extract(ae.value, '$.financials.price') AS price,
                ROW_NUMBER() OVER (
                    PARTITION BY j.value
                    ORDER BY ABS(julianday(t.created_at) - julianday(:cutoff))
                ) AS rn
            FROM tweets t, json_each(t.tickers) j
            LEFT JOIN json_each(t.assets) ae
                   ON json_extract(ae.value, '$.symbol') = j.value
            WHERE json_extract(ae.value, '$.financials.price') IS NOT NULL
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
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
        )
        SELECT
            m.ticker,
            m.mentions,
            m.avg_sentiment_24h,
            m.asset_kind,
            CASE
                WHEN pr.price IS NOT NULL
                 AND ps.price IS NOT NULL
                 AND ps.price != 0
                THEN (pr.price - ps.price) / ps.price * 100.0
                ELSE NULL
            END AS price_direction
        FROM mentions m
        LEFT JOIN (SELECT ticker, price FROM price_recent WHERE rn = 1) pr ON pr.ticker = m.ticker
        LEFT JOIN (SELECT ticker, price FROM price_at_start WHERE rn = 1) ps ON ps.ticker = m.ticker
        ORDER BY m.mentions DESC
        LIMIT :limit
    """)

    params: dict = {"cutoff": cutoff, "limit": limit, "min_mentions": min_mentions}
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions": r["mentions"],
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
    cutoff_now  = now - timedelta(hours=window_hours)
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
        items.append({
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_now"],
            "avg_sentiment_24h": avg_now,
            "avg_sentiment_prev": avg_prev,
            "delta": delta,
            "sentiment_label_24h": _score_to_label(avg_now),
            "sentiment_label_prev": _score_to_label(avg_prev),
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
        })

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


async def get_hidden_gems(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    window_hours: int = 24,
    user_screen_name: str | None = None,
    subscriber_only: bool = False,
) -> list[dict]:
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

    sql = text(f"""
        WITH active AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions_now,
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
        history AS (
            SELECT
                j.value AS ticker,
                MIN(t.created_at) AS first_seen,
                MAX(CASE WHEN t.created_at < :c_now THEN t.created_at ELSE NULL END)
                    AS last_seen_before_window
            FROM tweets t, json_each(t.tickers) j
            WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
              {user_c}
              {sub_c}
            GROUP BY j.value
        )
        SELECT
            a.ticker,
            a.mentions_now,
            a.asset_kind,
            h.first_seen,
            h.last_seen_before_window,
            CASE
                WHEN h.first_seen >= :c_now THEN 'new'
                WHEN h.last_seen_before_window IS NULL
                     OR h.last_seen_before_window < :c_resurface
                     THEN 'resurfacing'
                ELSE NULL
            END AS gem_subtype,
            CASE
                WHEN h.last_seen_before_window IS NOT NULL
                THEN CAST(
                    (julianday('now') - julianday(h.last_seen_before_window))
                    AS INTEGER)
                ELSE NULL
            END AS days_since_last
        FROM active a
        JOIN history h ON a.ticker = h.ticker
        WHERE gem_subtype IS NOT NULL
          {kind_filter}
        ORDER BY a.mentions_now DESC
        LIMIT 20
    """)

    params: dict = {"c_now": cutoff_now, "c_resurface": cutoff_resurface}
    if user_screen_name:
        params["user_name_pat"] = f"%{user_screen_name.lower()}%"

    async with Session() as s:
        result = await s.execute(sql, params)
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_now"],
            "asset_kind": (r["asset_kind"] or "EQUITY").upper(),
            "gem_subtype": r["gem_subtype"],
            "days_since_last": r["days_since_last"],
            "first_seen": str(r["first_seen"]) if r["first_seen"] else None,
            "last_seen": str(r["last_seen_before_window"]) if r["last_seen_before_window"] else None,
        }
        for r in rows
    ]
