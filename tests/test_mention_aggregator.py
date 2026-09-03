import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base, TweetRow

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def Session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _tweet(
    id,
    tickers,
    label,
    score,
    hours_ago,
    kind="EQUITY",
    change_pct=0.0,
    price=None,
    author="u",
    sector=None,
    industry=None,
):
    financials = {"change_percent": change_pct}
    if price is not None:
        financials["price"] = price
    asset = {"kind": kind, "financials": financials}
    if sector is not None:
        asset["sector"] = sector
    if industry is not None:
        asset["industry"] = industry
    return TweetRow(
        id=id,
        text="x",
        user_name=author,
        user_screen_name=author,
        user_img="",
        url="",
        media=[],
        tickers=tickers,
        hashtags=[],
        title="",
        media_types=[],
        created_at=_now() - timedelta(hours=hours_ago),
        sentiment_label=label,
        sentiment_score=score,
        assets=[{"symbol": t, **asset} for t in tickers],
        is_options_tweet=False,
    )


async def _insert(Session, rows):
    async with Session() as s:
        async with s.begin():
            for r in rows:
                s.add(r)


async def test_mention_heat_counts(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
            _tweet(2, ["BTC"], "BULL", 0.6, 3, "CRYPTO"),
            _tweet(3, ["AAPL"], "BEAR", -0.7, 2, "EQUITY"),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert btc["mentions"] == 2
    assert btc["asset_kind"] == "CRYPTO"
    assert btc["sentiment_label_24h"] == "BULL"
    # Both BTC tweets are from the same default author.
    assert btc["unique_authors"] == 1
    assert btc["mention_score"] == 2


async def test_mention_heat_avg_sentiment(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            _tweet(1, ["BTC"], "BULL", 0.8, 1, "CRYPTO"),
            _tweet(2, ["BTC"], "BULL", 0.4, 2, "CRYPTO"),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24, min_mentions=1)
    btc = next(r for r in rows if r["ticker"] == "BTC")

    assert abs(btc["avg_sentiment_24h"] - 0.6) < 0.01


async def test_mention_heat_min_mentions_filter(Session):
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            _tweet(1, ["BIG"], "BULL", 0.5, 1),
            _tweet(2, ["BIG"], "BULL", 0.5, 2),
            _tweet(3, ["TINY"], "BULL", 0.5, 1),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24, min_mentions=2)
    tickers = [r["ticker"] for r in rows]
    assert "BIG" in tickers
    assert "TINY" not in tickers


async def test_mention_heat_fair_score_caps_single_spammy_author(Session):
    """A ticker spammed by one account should not out-rank a ticker spread
    across several distinct authors, even though it has more raw mentions."""
    from app.services.mention_aggregator import get_mention_heat

    spam = [
        _tweet(i, ["SPAM"], "NEUTRAL", 0.0, 1, author="loud_one") for i in range(1, 11)
    ]
    fair = [
        _tweet(i + 100, ["FAIR"], "NEUTRAL", 0.0, 1, author=f"author_{i}")
        for i in range(1, 5)
    ]
    await _insert(Session, spam + fair)

    rows = await get_mention_heat(Session, window_hours=24, min_mentions=1)
    spam_row = next(r for r in rows if r["ticker"] == "SPAM")
    fair_row = next(r for r in rows if r["ticker"] == "FAIR")

    assert spam_row["mentions"] == 10
    assert spam_row["unique_authors"] == 1
    assert spam_row["mention_score"] == 3  # capped at AUTHOR_MENTION_CAP

    assert fair_row["mentions"] == 4
    assert fair_row["unique_authors"] == 4
    assert fair_row["mention_score"] == 4

    assert fair_row["mention_score"] > spam_row["mention_score"]
    assert rows[0]["ticker"] == "FAIR"  # ranked ahead despite fewer raw mentions


async def test_sector_mentions_groups_by_sector_and_industry(Session):
    from app.services.mention_aggregator import get_sector_mentions

    await _insert(
        Session,
        [
            _tweet(
                1,
                ["NVDA"],
                "BULL",
                0.5,
                1,
                sector="Technology",
                industry="Semiconductors",
            ),
            _tweet(
                2,
                ["MU"],
                "BULL",
                0.3,
                2,
                sector="Technology",
                industry="Semiconductors",
            ),
            _tweet(
                3,
                ["MSFT"],
                "NEUTRAL",
                0.0,
                1,
                sector="Technology",
                industry="Software",
            ),
            _tweet(4, ["BTC"], "BULL", 0.5, 1, kind="CRYPTO"),  # no sector, excluded
        ],
    )

    rows = await get_sector_mentions(Session, window_hours=24)
    tech = next(r for r in rows if r["sector"] == "Technology")

    assert tech["mentions"] == 3
    assert tech["unique_tickers"] == 3
    assert {t["ticker"] for t in tech["top_tickers"]} == {"NVDA", "MU", "MSFT"}

    industries = {i["industry"]: i for i in tech["industries"]}
    assert industries["Semiconductors"]["mentions"] == 2
    assert industries["Semiconductors"]["unique_tickers"] == 2
    assert industries["Software"]["mentions"] == 1

    assert all(r["sector"] != "" for r in rows)


async def test_sector_mentions_excludes_untagged_assets(Session):
    from app.services.mention_aggregator import get_sector_mentions

    await _insert(
        Session,
        [
            _tweet(1, ["BTC"], "BULL", 0.5, 1, kind="CRYPTO"),
            _tweet(2, ["EURUSD"], "NEUTRAL", 0.0, 1, kind="FOREX"),
        ],
    )

    rows = await get_sector_mentions(Session, window_hours=24)
    assert rows == []


async def test_sector_mentions_fair_score_caps_single_spammy_author(Session):
    from app.services.mention_aggregator import get_sector_mentions

    spam = [
        _tweet(
            i,
            ["MU"],
            "NEUTRAL",
            0.0,
            1,
            author="loud_one",
            sector="Technology",
            industry="Semiconductors",
        )
        for i in range(1, 11)
    ]
    fair = [
        _tweet(
            i + 100,
            ["JPM"],
            "NEUTRAL",
            0.0,
            1,
            author=f"author_{i}",
            sector="Financials",
            industry="Banks",
        )
        for i in range(1, 5)
    ]
    await _insert(Session, spam + fair)

    rows = await get_sector_mentions(Session, window_hours=24)
    tech = next(r for r in rows if r["sector"] == "Technology")
    fin = next(r for r in rows if r["sector"] == "Financials")

    assert tech["mentions"] == 10
    assert tech["mention_score"] == 3  # capped at AUTHOR_MENTION_CAP
    assert fin["mentions"] == 4
    assert fin["mention_score"] == 4

    assert rows[0]["sector"] == "Financials"  # ranked ahead despite fewer raw mentions


async def test_volume_baseline_multiplier(Session):
    from app.services.mention_aggregator import get_volume_baseline

    tweets = [_tweet(i, ["GME"], "NEUTRAL", 0.0, i * 0.5) for i in range(1, 8)]
    tweets += [_tweet(i + 10, ["GME"], "NEUTRAL", 0.0, i * 24) for i in range(1, 7)]
    await _insert(Session, tweets)

    rows = await get_volume_baseline(Session, threshold=2.0)
    gme = next((r for r in rows if r["ticker"] == "GME"), None)
    assert gme is not None
    assert gme["volume_multiplier"] > 2.0


async def test_sentiment_shift_detects_swing(Session):
    from app.services.mention_aggregator import get_sentiment_shift

    await _insert(
        Session,
        [
            _tweet(1, ["ETH"], "BULL", 0.7, 2),
            _tweet(2, ["ETH"], "BEAR", -0.5, 30),
        ],
    )

    rows = await get_sentiment_shift(Session)
    eth = next((r for r in rows if r["ticker"] == "ETH"), None)
    assert eth is not None
    assert eth["sentiment_label_24h"] == "BULL"
    assert eth["sentiment_label_prev"] == "BEAR"


async def test_hidden_gems_detects_new(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(Session, [_tweet(1, ["NEWCO"], "BULL", 0.5, 0.5)])

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "NEWCO"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "new"


async def test_hidden_gems_detects_resurfacing(Session):
    from app.services.mention_aggregator import get_hidden_gems

    await _insert(
        Session,
        [
            _tweet(1, ["OLD"], "BULL", 0.5, 0.5),
            _tweet(2, ["OLD"], "BULL", 0.5, 24 * 10),
        ],
    )

    rows = await get_hidden_gems(Session)
    gem = next((r for r in rows if r["ticker"] == "OLD"), None)
    assert gem is not None
    assert gem["gem_subtype"] == "resurfacing"
    assert gem["days_since_last"] is not None and gem["days_since_last"] >= 9


async def test_hidden_gems_fair_score_caps_single_spammy_author(Session):
    """Same fairness concern as mention-heat (issue #101): a ticker spammed
    by one account shouldn't out-rank a ticker several distinct authors are
    genuinely discovering, even though it has more raw mentions."""
    from app.services.mention_aggregator import get_hidden_gems

    spam = [
        _tweet(i, ["SPAM"], "NEUTRAL", 0.0, 0.5, author="loud_one")
        for i in range(1, 11)
    ]
    fair = [
        _tweet(i + 100, ["FAIR"], "NEUTRAL", 0.0, 0.5, author=f"author_{i}")
        for i in range(1, 5)
    ]
    await _insert(Session, spam + fair)

    rows = await get_hidden_gems(Session)
    spam_row = next(r for r in rows if r["ticker"] == "SPAM")
    fair_row = next(r for r in rows if r["ticker"] == "FAIR")

    assert spam_row["gem_subtype"] == "new"
    assert spam_row["mentions_24h"] == 10
    assert spam_row["unique_authors"] == 1
    assert spam_row["mention_score"] == 3  # capped at AUTHOR_MENTION_CAP

    assert fair_row["gem_subtype"] == "new"
    assert fair_row["mentions_24h"] == 4
    assert fair_row["unique_authors"] == 4
    assert fair_row["mention_score"] == 4

    assert fair_row["mention_score"] > spam_row["mention_score"]
    assert rows[0]["ticker"] == "FAIR"  # ranked ahead despite fewer raw mentions


# ── Price direction tests ────────────────────────────────────────────────────


async def test_price_direction_rising(Session):
    """24h window: price up 10% → price_direction ≈ +10."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            # Outside 24h window but closest to the 24h cutoff → price_then
            _tweet(10, ["BTCX"], "BULL", 0.5, 25, kind="CRYPTO", price=100.0),
            # Inside 24h window, most recent → price_now
            _tweet(11, ["BTCX"], "BULL", 0.5, 1, kind="CRYPTO", price=110.0),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24)
    btcx = next(r for r in rows if r["ticker"] == "BTCX")
    assert btcx["price_direction"] == pytest.approx(10.0, abs=0.5)


async def test_price_direction_falling(Session):
    """24h window: price down 10% → price_direction ≈ -10."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            _tweet(20, ["ETHX"], "BEAR", -0.5, 25, kind="CRYPTO", price=200.0),
            _tweet(21, ["ETHX"], "BEAR", -0.5, 1, kind="CRYPTO", price=180.0),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24)
    ethx = next(r for r in rows if r["ticker"] == "ETHX")
    assert ethx["price_direction"] == pytest.approx(-10.0, abs=0.5)


async def test_price_direction_null_without_price(Session):
    """Ticker with no financials.price → price_direction is None."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            _tweet(30, ["NO_PRICE"], "NEUTRAL", 0.0, 25),  # outside window, no price
            _tweet(31, ["NO_PRICE"], "NEUTRAL", 0.0, 1),  # inside window, no price
        ],
    )

    rows = await get_mention_heat(Session, window_hours=24)
    item = next((r for r in rows if r["ticker"] == "NO_PRICE"), None)
    assert item is not None
    assert item["price_direction"] is None


async def test_price_direction_7d_window(Session):
    """168h window: tweet at 170h ago as price_then, 1h ago as price_now → +10%."""
    from app.services.mention_aggregator import get_mention_heat

    await _insert(
        Session,
        [
            # ~7d ago (170h) — outside 168h window, closest to cutoff → price_then
            _tweet(40, ["SPY"], "BULL", 0.5, 170, kind="EQUITY", price=400.0),
            # 1h ago — inside 168h window, most recent → price_now
            _tweet(41, ["SPY"], "BULL", 0.5, 1, kind="EQUITY", price=440.0),
        ],
    )

    rows = await get_mention_heat(Session, window_hours=168)
    spy = next((r for r in rows if r["ticker"] == "SPY"), None)
    assert spy is not None
    assert spy["price_direction"] == pytest.approx(10.0, abs=0.5)


async def test_volume_baseline_7d_window_detects_spike(Session):
    """With window_hours=168, baseline = 28d, so spikes within the week still register."""
    from app.services.mention_aggregator import get_volume_baseline

    # 7 tweets in the last 7d (active window) — enough to clear the >5 filter
    active = [
        _tweet(i, ["SPIKE"], "NEUTRAL", 0.0, hours_ago)
        for i, hours_ago in enumerate([10, 30, 50, 70, 90, 110, 130], start=1)
    ]
    # 2 tweets in the prior 21 days (within 28d baseline, outside 7d window)
    historical = [
        _tweet(20, ["SPIKE"], "NEUTRAL", 0.0, 200),
        _tweet(21, ["SPIKE"], "NEUTRAL", 0.0, 400),
    ]
    await _insert(Session, active + historical)

    rows = await get_volume_baseline(Session, window_hours=168, threshold=1.5)
    spike = next((r for r in rows if r["ticker"] == "SPIKE"), None)
    assert spike is not None, "Expected SPIKE to appear; widget was empty at 7d window"
    assert spike["volume_multiplier"] > 1.5


async def test_extended_hours_stats_counts(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    await _insert(
        Session,
        [
            _tweet(10, ["NVDA"], "BULL", 0.8, 1, "EQUITY"),  # in window
            _tweet(11, ["NVDA"], "BULL", 0.9, 1, "EQUITY"),  # in window
            _tweet(12, ["AAPL"], "BEAR", -0.5, 1, "EQUITY"),  # in window
            _tweet(13, ["NVDA"], "BULL", 0.7, 10, "EQUITY"),  # outside window
        ],
    )
    since = now - timedelta(hours=5)
    until = now + timedelta(hours=1)

    result = await get_extended_hours_stats(Session, since, until, top_n=10)

    assert result["total_mentions"] == 3
    assert result["top_tickers"][0]["ticker"] == "NVDA"
    assert result["top_tickers"][0]["mentions"] == 2
    assert result["top_tickers"][0]["sentiment"] == "BULL"
    assert result["sentiment_distribution"]["BULL"] == 2
    assert result["sentiment_distribution"]["BEAR"] == 1
    assert result["sentiment_distribution"]["NEUTRAL"] == 0


async def test_extended_hours_stats_empty_window(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    # Window is entirely in the future — no tweets match.
    since = now + timedelta(hours=1)
    until = now + timedelta(hours=6)

    result = await get_extended_hours_stats(Session, since, until)

    assert result["total_mentions"] == 0
    assert result["top_tickers"] == []
    assert result["sentiment_distribution"] == {"BULL": 0, "BEAR": 0, "NEUTRAL": 0}


async def test_extended_hours_stats_top_n(Session):
    from app.services.mention_aggregator import get_extended_hours_stats

    now = _now()
    # Insert 5 distinct tickers, 3 mentions each.
    for i, ticker in enumerate(["A", "B", "C", "D", "E"]):
        for j in range(3):
            await _insert(Session, [_tweet(i * 10 + j, [ticker], "NEUTRAL", 0.0, 1)])

    since = now - timedelta(hours=5)
    until = now + timedelta(hours=1)

    result = await get_extended_hours_stats(Session, since, until, top_n=3)

    assert len(result["top_tickers"]) == 3


async def test_ticker_timeseries_buckets_and_summary(Session):
    from app.services.mention_aggregator import get_ticker_timeseries

    await _insert(
        Session,
        [
            _tweet(1, ["AAPL"], "BULLISH", 0.6, 1, price=190.0),
            _tweet(2, ["AAPL"], "BULLISH", 0.5, 1),
            _tweet(3, ["AAPL"], "BEARISH", -0.4, 30, price=180.0),
            _tweet(4, ["MSFT"], "NEUTRAL", 0.0, 1),
        ],
    )

    result = await get_ticker_timeseries(Session, "aapl", window_hours=48)

    assert result["ticker"] == "AAPL"
    assert result["bucket_hours"] == 1
    # 48h window at hourly buckets zero-fills every hour, not just hits.
    assert len(result["points"]) >= 48
    assert sum(p["mentions"] for p in result["points"]) == 3

    summary = result["summary"]
    assert summary["total_mentions"] == 3
    assert summary["bullish"] == 2
    assert summary["bearish"] == 1
    assert summary["neutral"] == 0
    assert summary["unique_authors"] == 1
    assert summary["asset_kind"] == "EQUITY"
    # Most recent AAPL tweet (hours_ago=1) priced at 190, earliest in-window
    # tweet within the price CTE lookback (hours_ago=30) priced at 180.
    assert summary["price_direction"] == pytest.approx((190.0 - 180.0) / 180.0 * 100.0)


async def test_ticker_timeseries_no_data_still_zero_fills(Session):
    from app.services.mention_aggregator import get_ticker_timeseries

    result = await get_ticker_timeseries(Session, "GHOST", window_hours=24)

    assert result["points"]
    assert all(p["mentions"] == 0 for p in result["points"])
    assert result["summary"]["total_mentions"] == 0
    assert result["summary"]["avg_mentions_per_bucket"] == 0.0
    assert result["summary"]["price_direction"] is None
    assert result["summary"]["asset_kind"] is None


async def test_ticker_timeseries_bucket_width_scales_with_window(Session):
    from app.services.mention_aggregator import get_ticker_timeseries

    daily = await get_ticker_timeseries(Session, "AAPL", window_hours=24 * 30)
    weekly = await get_ticker_timeseries(Session, "AAPL", window_hours=168)

    assert daily["bucket_hours"] == 24
    assert weekly["bucket_hours"] == 6
