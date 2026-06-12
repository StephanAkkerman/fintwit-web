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
            "last_seen": str(r["last_seen_before_window"])
            if r["last_seen_before_window"]
            else None,
        }
        for r in rows
    ]


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
