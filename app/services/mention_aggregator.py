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


_KIND_FILTER = {
    "CRYPTO": "AND MAX(json_extract(t.assets, '$[0].kind')) = 'CRYPTO'",
    "EQUITY": "AND MAX(json_extract(t.assets, '$[0].kind')) = 'EQUITY'",
    "FOREX":  "AND MAX(json_extract(t.assets, '$[0].kind')) = 'FOREX'",
}


async def get_mention_heat(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    min_mentions: int = 50,
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            AVG(CASE WHEN t.created_at >= :c24 THEN t.sentiment_score ELSE NULL END) AS avg_sentiment_24h,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind,
            AVG(CASE WHEN t.created_at >= :c24
                     THEN json_extract(t.assets, '$[0].financials.change_percent')
                     ELSE NULL END) AS price_direction
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) >= :min_m
        {kind_clause}
        ORDER BY mentions_24h DESC
        LIMIT 100
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c24": cutoff_24h, "min_m": min_mentions})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "avg_sentiment_24h": r["avg_sentiment_24h"] or 0.0,
            "sentiment_label_24h": _score_to_label(r["avg_sentiment_24h"]),
            "asset_kind": r["asset_kind"] or "EQUITY",
            "price_direction": r["price_direction"],
        }
        for r in rows
    ]


async def get_sentiment_shift(
    Session: async_sessionmaker,
    asset_kind: str = "all",
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_48h = now - timedelta(hours=48)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            AVG(CASE WHEN t.created_at >= :c24 THEN t.sentiment_score ELSE NULL END) AS avg_24h,
            AVG(CASE WHEN t.created_at >= :c48 AND t.created_at < :c24
                     THEN t.sentiment_score ELSE NULL END) AS avg_prev,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) > 0
          AND AVG(CASE WHEN t.created_at >= :c48 AND t.created_at < :c24
                       THEN t.sentiment_score ELSE NULL END) IS NOT NULL
        {kind_clause}
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c48": cutoff_48h, "c24": cutoff_24h})
        rows = result.mappings().all()

    _score = {"BULL": 1, "NEUTRAL": 0, "BEAR": -1}

    def swing(label_now: str, label_prev: str) -> int:
        return abs(_score.get(label_now, 0) - _score.get(label_prev, 0))

    items = []
    for r in rows:
        label_24h = _score_to_label(r["avg_24h"])
        label_prev = _score_to_label(r["avg_prev"])
        if swing(label_24h, label_prev) == 0:
            continue
        items.append({
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "avg_sentiment_24h": r["avg_24h"] or 0.0,
            "sentiment_label_24h": label_24h,
            "sentiment_label_prev": label_prev,
            "asset_kind": r["asset_kind"] or "EQUITY",
        })

    items.sort(key=lambda x: swing(x["sentiment_label_24h"], x["sentiment_label_prev"]), reverse=True)
    return items[:10]


async def get_volume_baseline(
    Session: async_sessionmaker,
    asset_kind: str = "all",
    threshold: float = 1.5,
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        SELECT
            j.value AS ticker,
            CAST(SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) AS INTEGER) AS mentions_24h,
            COUNT(*) / 7.0 AS baseline_7d_avg,
            CASE WHEN COUNT(*) > 0
                 THEN SUM(CASE WHEN t.created_at >= :c24 THEN 1.0 ELSE 0 END) / (COUNT(*) / 7.0)
                 ELSE NULL END AS volume_multiplier,
            MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
        FROM tweets t, json_each(t.tickers) j
        WHERE t.created_at >= :c7d
          AND t.tickers IS NOT NULL AND t.tickers != '[]'
        GROUP BY j.value
        HAVING SUM(CASE WHEN t.created_at >= :c24 THEN 1 ELSE 0 END) > 5
          AND (COUNT(*) / 7.0) > 0
          AND SUM(CASE WHEN t.created_at >= :c24 THEN 1.0 ELSE 0 END) / (COUNT(*) / 7.0) > :thr
        {kind_clause}
        ORDER BY volume_multiplier DESC
        LIMIT 10
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c7d": cutoff_7d, "c24": cutoff_24h, "thr": threshold})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "baseline_7d_avg": r["baseline_7d_avg"],
            "volume_multiplier": r["volume_multiplier"],
            "asset_kind": r["asset_kind"] or "EQUITY",
        }
        for r in rows
    ]


async def get_hidden_gems(
    Session: async_sessionmaker,
    asset_kind: str = "all",
) -> list[dict]:
    now = _now()
    cutoff_7d  = now - timedelta(days=7)
    cutoff_24h = now - timedelta(hours=24)
    kind_clause = _KIND_FILTER.get(asset_kind.upper(), "")

    sql = text(f"""
        WITH active AS (
            SELECT
                j.value AS ticker,
                CAST(COUNT(*) AS INTEGER) AS mentions_24h,
                MAX(json_extract(t.assets, '$[0].kind')) AS asset_kind
            FROM tweets t, json_each(t.tickers) j
            WHERE t.created_at >= :c24
              AND t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
            {kind_clause}
        ),
        history AS (
            SELECT
                j.value AS ticker,
                MIN(t.created_at) AS first_seen,
                MAX(CASE WHEN t.created_at < :c24 THEN t.created_at ELSE NULL END)
                    AS last_seen_before_window
            FROM tweets t, json_each(t.tickers) j
            WHERE t.tickers IS NOT NULL AND t.tickers != '[]'
            GROUP BY j.value
        )
        SELECT
            a.ticker,
            a.mentions_24h,
            a.asset_kind,
            h.first_seen,
            h.last_seen_before_window,
            CASE
                WHEN h.first_seen >= :c24 THEN 'new'
                WHEN h.last_seen_before_window IS NULL OR h.last_seen_before_window < :c7d
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
        ORDER BY a.mentions_24h DESC
        LIMIT 20
    """)

    async with Session() as s:
        result = await s.execute(sql, {"c24": cutoff_24h, "c7d": cutoff_7d})
        rows = result.mappings().all()

    return [
        {
            "ticker": r["ticker"],
            "mentions_24h": r["mentions_24h"],
            "asset_kind": r["asset_kind"] or "EQUITY",
            "gem_subtype": r["gem_subtype"],
            "days_since_last": r["days_since_last"],
            "first_seen": str(r["first_seen"]) if r["first_seen"] else None,
            "last_seen": str(r["last_seen_before_window"]) if r["last_seen_before_window"] else None,
        }
        for r in rows
    ]
