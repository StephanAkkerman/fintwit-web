# app/api/main.py (updated bits)
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker
from ticker_price_data import close_shared_pool, get_stock_info

from ..infra.db import create_engine, init_db
from ..infra.repos import (
    IbkrRepo,
    PortfolioRepo,
    RedditTrendRepo,
    TraderCallRepo,
    TweetRepo,
)
from ..ml.sentiment import FinTwitSentiment
from ..runtime.broadcast import Broadcaster
from ..runtime.enricher import AssetEnricher
from ..runtime.ibkr_sync import run_ibkr_sync
from ..runtime.options_intent import classify_options_intent
from ..runtime.reddit_trends import (
    DEFAULT_INTERVAL as REDDIT_TREND_INTERVAL,
)
from ..runtime.reddit_trends import (
    run_reddit_trends,
)
from ..runtime.portfolio_snapshot import (
    DEFAULT_INTERVAL as SNAPSHOT_INTERVAL,
    run_portfolio_snapshots,
)
from ..runtime.portfolio_valuation import (
    build_asset_insights,
    build_diversification,
    build_value_history,
    resolve_holdings,
    value_holdings,
)
from ..runtime.streamer import run_stream
from ..runtime.symbols import merge_symbols
from ..runtime.trader_evaluator import (
    DEFAULT_INTERVAL as TRADER_EVAL_INTERVAL,
    run_trader_call_evaluation,
)
from ..services.binance_service import get_gainers_losers
from ..services.cmc import get_trending_crypto
from ..services import cloudflare_access
from ..services.coin360_service import get_treemap_data
from ..services.earnings_service import get_earnings_calendar
from ..services.events_service import get_economic_events
from ..services.fear_greed_service import get_feargreed
from ..services.ibkr import IbkrGateway
from ..services.macro_market import get_macro_snapshot
from ..services.market_hours_service import get_stock_market_hours
from ..services.nasdaq_service import get_halt_data
from ..services.news_service import get_company_news
from ..services.options_chain_service import get_options_chain
from ..services.options_service import get_options_overview
from ..services.price_history_service import (
    DEFAULT_RANGE as DEFAULT_HISTORY_RANGE,
    RANGE_PRESETS,
    normalize_range,
)
from ..services.reddit_service import get_reddit_hot_posts, is_valid_subreddit_name
from ..services import reddit_trends_service
from ..services.signa import get_signa_best_trades, get_signa_live_feed
from ..services.stock_fear_greed_service import get_stock_feargreed
from ..services.stocktwits_service import get_stocktwits_data
from ..services.trader_scoring import extract_calls
from ..services.unusual_whales import get_spy_heatmap, summarize_spy_sectors
from ..services.extended_hours_service import (
    get_snapshot as get_extended_hours_snapshot,
)
from ..services.market_movers_service import (
    CATEGORIES as MOVERS_CATEGORIES,
    MARKETS as MOVERS_MARKETS,
    get_market_movers,
)
from ..services.market_movers_service import get_movers as get_market_movers_multi

with suppress(Exception):
    from dotenv import load_dotenv

    # Keep existing process env (for Docker/Compose) authoritative.
    load_dotenv(
        dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False
    )

ENGINE = create_engine(os.getenv("DB_URL", "sqlite+aiosqlite:///./data.db"))
Session = async_sessionmaker(ENGINE, expire_on_commit=False)
REPO = TweetRepo(Session)
PORTFOLIO_REPO = PortfolioRepo(Session)
IBKR_REPO = IbkrRepo(Session)
TRADER_CALL_REPO = TraderCallRepo(Session)
REDDIT_TREND_REPO = RedditTrendRepo(Session)
BROADCAST = Broadcaster()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("httpcore").setLevel(logging.INFO)


async def api_key_dep(request: Request):
    expected = getattr(request.app.state, "API_KEY", "")
    got = request.headers.get("X-API-Key")
    if expected and got != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_started = time.perf_counter()
    logger.info("[startup] initializing application")

    await init_db(ENGINE)
    app.state.API_KEY = os.getenv("API_KEY", "")
    app.state.http_client = httpx.AsyncClient()

    sentiment_model: FinTwitSentiment | None = FinTwitSentiment()
    try:
        await sentiment_model.warmup()
    except Exception as exc:
        logger.warning("[startup] sentiment model warmup failed: %r", exc)
        sentiment_model = None

    app.state.sentiment_model = sentiment_model

    # start background stream: persist THEN broadcast
    task = asyncio.create_task(
        run_stream(REPO, BROADCAST, sentiment_model, TRADER_CALL_REPO)
    )

    # start IBKR sync worker if enabled
    ibkr_task: asyncio.Task | None = None
    if os.getenv("IBKR_ENABLED", "").lower() in ("1", "true", "yes"):
        gateway = IbkrGateway()
        app.state.ibkr_gateway = gateway
        ibkr_interval = int(os.getenv("IBKR_SYNC_INTERVAL", "60"))
        ibkr_task = asyncio.create_task(
            run_ibkr_sync(IBKR_REPO, gateway, interval=ibkr_interval)
        )
        logger.info(
            "[ibkr] sync worker started (host=%s port=%s interval=%ds)",
            os.getenv("IBKR_HOST", "ibgateway"),
            os.getenv("IBKR_PORT", "4001"),
            ibkr_interval,
        )
    else:
        app.state.ibkr_gateway = None

    snapshot_interval = int(os.getenv("PORTFOLIO_SNAPSHOT_INTERVAL", SNAPSHOT_INTERVAL))
    snapshot_task = asyncio.create_task(
        run_portfolio_snapshots(PORTFOLIO_REPO, IBKR_REPO, interval=snapshot_interval)
    )
    logger.info("[portfolio] snapshot worker started (interval=%ds)", snapshot_interval)

    trader_eval_interval = int(os.getenv("TRADER_EVAL_INTERVAL", TRADER_EVAL_INTERVAL))
    trader_eval_task = asyncio.create_task(
        run_trader_call_evaluation(
            Session, TRADER_CALL_REPO, interval=trader_eval_interval
        )
    )
    logger.info(
        "[trader-eval] call evaluation worker started (interval=%ds)",
        trader_eval_interval,
    )

    reddit_task: asyncio.Task | None = None
    if os.getenv("REDDIT_TRENDS_ENABLED", "1").lower() in ("1", "true", "yes"):
        reddit_interval = int(os.getenv("REDDIT_TREND_INTERVAL", REDDIT_TREND_INTERVAL))
        reddit_task = asyncio.create_task(
            run_reddit_trends(
                REDDIT_TREND_REPO,
                interval=reddit_interval,
                window_hours=float(os.getenv("REDDIT_TREND_WINDOW_HOURS", "24")),
            )
        )
        logger.info(
            "[reddit-trends] worker started (interval=%ds)",
            reddit_interval,
        )

    try:
        logger.info(
            "[startup] application ready in %.2fs",
            time.perf_counter() - startup_started,
        )
        yield
    finally:
        logger.info("[shutdown] stopping background workers")
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        snapshot_task.cancel()
        with suppress(asyncio.CancelledError):
            await snapshot_task
        trader_eval_task.cancel()
        with suppress(asyncio.CancelledError):
            await trader_eval_task
        if reddit_task is not None:
            reddit_task.cancel()
            with suppress(asyncio.CancelledError):
                await reddit_task
            await reddit_trends_service.close()
        if ibkr_task is not None:
            ibkr_task.cancel()
            with suppress(asyncio.CancelledError):
                await ibkr_task
            if app.state.ibkr_gateway is not None:
                app.state.ibkr_gateway.stop()
        await app.state.http_client.aclose()
        close_shared_pool()


app = FastAPI(title="X Stream API", lifespan=lifespan)

from .overview import router as overview_router  # noqa: E402
from .traders import router as traders_router  # noqa: E402

app.include_router(overview_router)
app.include_router(traders_router)


@app.get("/api/posts")
async def list_posts(
    limit: int = Query(200, ge=1, le=2000),
    before_id: int | None = Query(default=None, ge=1),
    since_hours: int | None = Query(default=None, ge=1, le=168),
    options_only: bool = Query(default=False),
    _=Depends(api_key_dep),
):
    if since_hours is None:
        return await REPO.latest(limit, before_id=before_id, options_only=options_only)

    return await REPO.latest(
        limit,
        before_id=before_id,
        options_only=options_only,
        since_hours=since_hours,
    )


@app.get("/api/stream")
async def stream(options_only: bool = Query(default=False), _=Depends(api_key_dep)):
    async def gen():
        q = await BROADCAST.subscribe()
        try:
            while True:
                item = await q.get()
                if options_only and item.get("is_options_tweet") is not True:
                    continue
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            await BROADCAST.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/fear-greed")
async def fear_greed(_=Depends(api_key_dep)):
    data = await get_feargreed()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/events/economic")
async def economic_events(
    request: Request,
    limit: int = Query(25, ge=1, le=100),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_economic_events(client, limit=limit)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/forex/macro")
async def forex_macro(_=Depends(api_key_dep)):
    data = await get_macro_snapshot()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stock-halts")
async def stock_halts(request: Request, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_halt_data(client)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/earnings/calendar")
async def earnings_calendar(
    request: Request,
    days: int = Query(7, ge=1, le=14),
    limit_per_day: int = Query(10, ge=1, le=50),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_earnings_calendar(client, days=days, limit_per_day=limit_per_day)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/binance/gainers-losers")
async def binance_gainers_losers(request: Request, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_gainers_losers(client)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stocktwits")
async def stocktwits(
    request: Request, keyword: str = Query("ts"), _=Depends(api_key_dep)
):
    if keyword not in ["ts", "m_day", "wl_ct_day"]:
        raise HTTPException(status_code=400, detail="Invalid keyword")
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_stocktwits_data(client, keyword)
    if data is None:
        # StockTwits can intermittently block requests; return empty payload to avoid UI hard-fail.
        return []
    return data


@app.get("/api/options/overview")
async def options_overview(
    request: Request,
    symbols: str | None = Query(default=None),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    parsed_symbols = None
    if symbols:
        parsed_symbols = [
            part.strip().upper() for part in symbols.split(",") if part.strip()
        ]

    data = await get_options_overview(client, parsed_symbols)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/options/chain")
async def options_chain(
    symbol: str = Query(...),
    expiration: str | None = Query(default=None),
    _=Depends(api_key_dep),
):
    data = await get_options_chain(symbol, expiration)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/news/company")
async def news_company(
    symbols: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    _=Depends(api_key_dep),
):
    parsed_symbols = [
        part.strip().upper() for part in symbols.split(",") if part.strip()
    ]
    data = await get_company_news(parsed_symbols, limit)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return {"articles": data, "source": "yfinance"}


@app.get("/api/stocks/fear-greed")
async def stock_fear_greed(request: Request, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_stock_feargreed(client)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stocks/market-hours")
async def stock_market_hours(_=Depends(api_key_dep)):
    data = await get_stock_market_hours()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stocks/extended-hours")
async def stocks_extended_hours(_=Depends(api_key_dep)):
    data = await get_extended_hours_snapshot(Session)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/stocks/market-movers")
async def stocks_market_movers(_=Depends(api_key_dep)):
    data = await get_market_movers()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/markets/movers")
async def markets_movers(
    market: str = Query("usa"),
    category: str = Query("gainers"),
    _=Depends(api_key_dep),
):
    if market not in MOVERS_MARKETS:
        raise HTTPException(status_code=400, detail="Invalid market")
    if category not in MOVERS_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    movers = await get_market_movers_multi(market, category)
    if movers is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return {"market": market, "category": category, "movers": movers}


_SPY_HEATMAP_DATE_RANGES = [
    "one_day",
    "after_hours",
    "yesterday",
    "one_week",
    "one_month",
    "ytd",
    "one_year",
]


@app.get("/api/spy-heatmap")
async def spy_heatmap(
    request: Request,
    date: str = Query("one_day", enum=_SPY_HEATMAP_DATE_RANGES),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_spy_heatmap(client, date=date)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/spy-heatmap/sectors")
async def spy_heatmap_sectors(
    request: Request,
    date: str = Query("one_day", enum=_SPY_HEATMAP_DATE_RANGES),
    _=Depends(api_key_dep),
):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_spy_heatmap(client, date=date)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return {"sectors": summarize_spy_sectors(data)}


@app.get("/api/treemap")
async def treemap(request: Request, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_treemap_data(client)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/reddit/wsb")
async def reddit_wsb(
    request: Request,
    limit: int = Query(10, ge=1, le=50),
    subreddit: str = Query("wallstreetbets"),
    _=Depends(api_key_dep),
):
    if not is_valid_subreddit_name(subreddit):
        raise HTTPException(status_code=400, detail="Invalid subreddit")

    client: httpx.AsyncClient = request.app.state.http_client
    data = await get_reddit_hot_posts(client, subreddit_name=subreddit, limit=limit)
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/reddit/trends")
async def reddit_trends(
    limit: int = Query(25, ge=1, le=100),
    _=Depends(api_key_dep),
):
    """Latest stored ranking of the tickers finance subreddits are discussing.

    Served from the last completed worker run rather than scraping on request:
    a scrape is several subreddit listings plus two model passes over every
    post. `available` is False when `reddit-stock-analyzer` is not installed,
    and `captured_at` is null until the first run completes — the UI needs to
    tell "nothing installed" apart from "nothing scraped yet".
    """
    run = await REDDIT_TREND_REPO.latest_run(limit=limit)
    if run is None:
        return {
            "available": reddit_trends_service.is_available(),
            "captured_at": None,
            "subreddits": reddit_trends_service.default_subreddits(),
            "tickers": [],
        }
    return {"available": True, **run}


@app.get("/api/reddit/trends/{symbol}/history")
async def reddit_trend_history(
    symbol: str,
    days: int = Query(30, ge=1, le=365),
    _=Depends(api_key_dep),
):
    """One ticker's mention/sentiment history across stored runs, oldest first."""
    points = await REDDIT_TREND_REPO.ticker_history(symbol, days=days)
    return {"symbol": symbol.upper(), "days": days, "points": points}


@app.get("/api/reddit/categories")
async def reddit_categories(_=Depends(api_key_dep)):
    """The subreddit catalogue, grouped by the kind of discussion it carries."""
    return {
        "available": reddit_trends_service.is_available(),
        "default": reddit_trends_service.default_subreddits(),
        "categories": reddit_trends_service.subreddit_categories(),
    }


@app.get("/api/reddit/summary/{subreddit}")
async def reddit_subreddit_summary(
    subreddit: str,
    limit: int = Query(50, ge=1, le=100),
    _=Depends(api_key_dep),
):
    """Ticker and sentiment snapshot for one subreddit, computed on request.

    Affordable live because it is a single listing with no baseline window —
    unlike the full trend report, which the worker owns.
    """
    if not is_valid_subreddit_name(subreddit):
        raise HTTPException(status_code=400, detail="Invalid subreddit")

    try:
        return await reddit_trends_service.fetch_subreddit_summary(
            subreddit, limit=limit
        )
    except reddit_trends_service.RedditAnalyzerUnavailable:
        raise HTTPException(
            status_code=503,
            detail="Reddit trend analysis is not available in this deployment",
        ) from None
    except Exception as exc:
        logger.warning("[reddit-trends] subreddit summary failed: %r", exc)
        raise HTTPException(status_code=503, detail="Service Unavailable") from None


class DebugTweet(BaseModel):
    text: str = "Test tweet"
    user_name: str = "Debug User"
    user_screen_name: str = "debuguser"
    user_img: str = ""
    tickers: list[str] = []
    hashtags: list[str] = []
    media: list[str] = []
    media_types: list[str] = []
    title: str = ""


class PortfolioPositionCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    quantity: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    broker: Literal["IBKR"] = "IBKR"
    currency: str = Field(default="USD", min_length=1, max_length=8)
    opened_at: datetime | None = None
    notes: str | None = None
    is_active: bool = True


class PortfolioPositionUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=16)
    quantity: float | None = Field(default=None, gt=0)
    avg_cost: float | None = Field(default=None, ge=0)
    broker: Literal["IBKR"] | None = None
    currency: str | None = Field(default=None, min_length=1, max_length=8)
    opened_at: datetime | None = None
    notes: str | None = None
    is_active: bool | None = None


def _normalize_portfolio_payload(payload: dict) -> dict:
    normalized = dict(payload)

    if "symbol" in normalized and normalized["symbol"] is not None:
        normalized["symbol"] = str(normalized["symbol"]).strip().upper()

    if "currency" in normalized and normalized["currency"] is not None:
        normalized["currency"] = str(normalized["currency"]).strip().upper()

    return normalized


@app.post("/api/debug/tweet")
async def debug_tweet(body: DebugTweet, request: Request):
    tickers, hashtags = merge_symbols(body.text, body.tickers, body.hashtags)
    asset_symbols = list(tickers)
    assets = []
    if asset_symbols:
        enricher = AssetEnricher()
        assets = await enricher.classify(asset_symbols)

    main_sentiment = None
    quoted_sentiment = None
    ticker_sentiment = {}
    sentiment_model = getattr(request.app.state, "sentiment_model", None)
    if sentiment_model is not None and body.text.strip():
        try:
            sentiment_parts = await sentiment_model.classify_parts(
                body.text, asset_symbols
            )
            main_sentiment = sentiment_parts.get("main")
            quoted_sentiment = sentiment_parts.get("quoted")
            ticker_sentiment = sentiment_parts.get("tickers") or {}
        except Exception as exc:
            logger.warning("[debug-tweet] sentiment classification failed: %r", exc)

    options_signal = classify_options_intent(body.text)

    tweet = {
        **body.model_dump(),
        "tickers": tickers,
        "hashtags": hashtags,
        "id": int(datetime.now(timezone.utc).timestamp() * 1000),
        "url": "",
        "created_at": datetime.now(timezone.utc),
        "assets": assets,
        "replies": 0,
        "likes": 0,
        "views": 0,
        "retweets": 0,
        "sentiment_label": main_sentiment["label"] if main_sentiment else None,
        "sentiment_emoji": main_sentiment["emoji"] if main_sentiment else None,
        "sentiment_score": main_sentiment["score"] if main_sentiment else None,
        "quoted_sentiment_label": (
            quoted_sentiment["label"] if quoted_sentiment else None
        ),
        "quoted_sentiment_emoji": (
            quoted_sentiment["emoji"] if quoted_sentiment else None
        ),
        "quoted_sentiment_score": (
            quoted_sentiment["score"] if quoted_sentiment else None
        ),
        "ticker_sentiment": ticker_sentiment or None,
        "is_options_tweet": options_signal["is_options_tweet"],
        "options_context": (
            options_signal["options_context"]
            if options_signal["is_options_tweet"]
            else None
        ),
    }
    await REPO.upsert_many([tweet])
    await BROADCAST.publish(tweet)
    calls = extract_calls(tweet)
    if calls:
        await TRADER_CALL_REPO.insert_calls(calls)
    return tweet


class AccessEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


def _normalize_access_email(email: str) -> str:
    normalized = email.strip().lower()
    local, _, domain = normalized.partition("@")
    if not local or not domain or "." not in domain or "/" in normalized:
        raise HTTPException(status_code=422, detail="Not a valid email address")
    return normalized


@app.get("/api/admin/access-emails")
async def list_access_emails(request: Request, _=Depends(api_key_dep)):
    """Who can log in to the publicly-tunneled dashboard via Cloudflare Access."""
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        emails = await cloudflare_access.list_allowed_emails(client)
    except cloudflare_access.CloudflareAccessError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"emails": emails}


@app.post("/api/admin/access-emails")
async def add_access_email(
    request: Request, body: AccessEmailRequest, _=Depends(api_key_dep)
):
    client: httpx.AsyncClient = request.app.state.http_client
    email = _normalize_access_email(body.email)
    try:
        emails = await cloudflare_access.add_allowed_email(client, email)
    except cloudflare_access.CloudflareAccessError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"emails": emails}


@app.delete("/api/admin/access-emails/{email}")
async def remove_access_email(request: Request, email: str, _=Depends(api_key_dep)):
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        emails = await cloudflare_access.remove_allowed_email(
            client, email.strip().lower()
        )
    except cloudflare_access.CloudflareAccessError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"emails": emails}


@app.get("/api/portfolio/positions")
async def list_portfolio_positions(
    active_only: bool | None = Query(default=None), _=Depends(api_key_dep)
):
    return await PORTFOLIO_REPO.list_positions(active_only=active_only)


@app.post("/api/portfolio/positions")
async def create_portfolio_position(
    body: PortfolioPositionCreate, _=Depends(api_key_dep)
):
    payload = _normalize_portfolio_payload(body.model_dump())
    return await PORTFOLIO_REPO.create_position(payload)


@app.patch("/api/portfolio/positions/{position_id}")
async def update_portfolio_position(
    position_id: int, body: PortfolioPositionUpdate, _=Depends(api_key_dep)
):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        current = await PORTFOLIO_REPO.by_id(position_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Position not found")
        return current

    normalized_updates = _normalize_portfolio_payload(updates)
    updated = await PORTFOLIO_REPO.update_position(position_id, normalized_updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return updated


@app.delete("/api/portfolio/positions/{position_id}")
async def delete_portfolio_position(position_id: int, _=Depends(api_key_dep)):
    deleted = await PORTFOLIO_REPO.delete_position(position_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Position not found")
    return {"ok": True, "id": position_id}


@app.get("/api/portfolio/summary")
async def portfolio_summary(_=Depends(api_key_dep)):
    positions = await PORTFOLIO_REPO.list_positions(active_only=True)
    if not positions:
        return {
            "totals": {
                "positions": 0,
                "market_value": 0.0,
                "cost_basis": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_percent": 0.0,
            },
            "positions": [],
        }

    quote_tasks = [get_stock_info(p["symbol"]) for p in positions]
    quote_results = await asyncio.gather(*quote_tasks, return_exceptions=True)

    enriched_positions: list[dict] = []
    total_market_value = 0.0
    total_cost_basis = 0.0

    for pos, quote in zip(positions, quote_results):
        quote_data = quote if isinstance(quote, dict) else None
        market_price = quote_data.get("price") if quote_data else None

        qty = float(pos["quantity"])
        avg_cost = float(pos["avg_cost"])
        cost_basis = qty * avg_cost
        market_value = qty * (
            float(market_price) if market_price is not None else avg_cost
        )
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_percent = (
            (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
        )

        total_market_value += market_value
        total_cost_basis += cost_basis

        enriched_positions.append(
            {
                **pos,
                "market_price": (
                    float(market_price) if market_price is not None else None
                ),
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_percent,
                "website": quote_data.get("website") if quote_data else None,
            }
        )

    total_pnl = total_market_value - total_cost_basis
    total_pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis else 0.0

    return {
        "totals": {
            "positions": len(enriched_positions),
            "market_value": total_market_value,
            "cost_basis": total_cost_basis,
            "unrealized_pnl": total_pnl,
            "unrealized_pnl_percent": total_pnl_pct,
        },
        "positions": enriched_positions,
    }


_RANGE_LOOKBACK_DAYS: dict[str, int | None] = {
    "1W": 7,
    "1M": 31,
    "3M": 93,
    "6M": 186,
    "YTD": None,  # resolved against Jan 1 of the current year
    "1Y": 366,
    "5Y": 1830,
    "MAX": None,
}


def _snapshot_cutoff(range_key: str) -> datetime | None:
    """Earliest snapshot timestamp worth loading for a chart range."""
    now = datetime.now(timezone.utc)
    if range_key == "YTD":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)

    days = _RANGE_LOOKBACK_DAYS.get(range_key)
    return now - timedelta(days=days) if days else None


@app.get("/api/portfolio/history")
async def portfolio_history(
    range: str = Query(default=DEFAULT_HISTORY_RANGE),
    source: str = Query(default="auto"),
    _=Depends(api_key_dep),
):
    """Portfolio value over time for the requested range.

    Values are reconstructed from each holding's historical closes and
    overridden by stored snapshots wherever one exists for that day.
    """
    range_key = normalize_range(range)
    resolved_source, holdings = await resolve_holdings(
        PORTFOLIO_REPO, IBKR_REPO, source
    )

    if not holdings:
        return {
            "source": resolved_source,
            "range": range_key,
            "available_ranges": list(RANGE_PRESETS),
            "holdings": [],
            "points": [],
            "cost_basis": 0.0,
            "start_value": None,
            "end_value": None,
            "change": None,
            "change_percent": None,
            "missing_symbols": [],
        }

    snapshots = await PORTFOLIO_REPO.list_snapshots(
        source=resolved_source, since=_snapshot_cutoff(range_key)
    )
    valuation = await value_holdings(holdings)
    history = await build_value_history(
        holdings,
        range_key,
        snapshots=snapshots,
        live_totals=valuation["totals"],
    )

    return {
        "source": resolved_source,
        "available_ranges": list(RANGE_PRESETS),
        "holdings": [h["symbol"] for h in holdings],
        "totals": valuation["totals"],
        **history,
    }


@app.get("/api/portfolio/insights")
async def portfolio_insights(
    source: str = Query(default="auto"),
    _=Depends(api_key_dep),
):
    """Per-asset context and portfolio-level balance: ATH/ATL distance,
    52-week range, sector allocation and holding/sector concentration."""
    resolved_source, holdings = await resolve_holdings(
        PORTFOLIO_REPO, IBKR_REPO, source
    )

    if not holdings:
        empty_diversification = await build_diversification([])
        return {
            "source": resolved_source,
            "totals": {
                "positions": 0,
                "market_value": 0.0,
                "cost_basis": 0.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_percent": 0.0,
            },
            "positions": [],
            "highlights": [],
            **empty_diversification,
        }

    valuation = await value_holdings(holdings)
    positions = await build_asset_insights(valuation["positions"])
    diversification = await build_diversification(valuation["positions"])

    highlights = [
        {
            "symbol": position["symbol"],
            "code": flag["code"],
            "label": flag["label"],
            "tone": flag["tone"],
            "weight_percent": position.get("weight_percent"),
        }
        for position in positions
        for flag in ((position.get("stats") or {}).get("flags") or [])
    ]

    return {
        "source": resolved_source,
        "totals": valuation["totals"],
        "positions": positions,
        "highlights": highlights,
        **diversification,
    }


@app.get("/api/ibkr/status")
async def ibkr_status(request: Request, _=Depends(api_key_dep)):
    gateway: IbkrGateway | None = request.app.state.ibkr_gateway
    if gateway is None:
        return {
            "configured": False,
            "connected": False,
            "last_sync": None,
            "last_error": None,
        }
    return {
        "configured": True,
        "connected": gateway.is_connected(),
        "last_sync": gateway.last_sync.isoformat() if gateway.last_sync else None,
        "last_error": gateway.last_error,
    }


@app.get("/api/ibkr/positions")
async def ibkr_positions(_=Depends(api_key_dep)):
    positions = await IBKR_REPO.list_positions()
    if not positions:
        return []

    stock_positions = [p for p in positions if p["sec_type"] == "STK"]
    quote_tasks = [get_stock_info(p["symbol"]) for p in stock_positions]
    quote_results = await asyncio.gather(*quote_tasks, return_exceptions=True)
    quote_map = {
        pos["symbol"]: q
        for pos, q in zip(stock_positions, quote_results)
        if isinstance(q, dict)
    }

    enriched = []
    for p in positions:
        quote = quote_map.get(p["symbol"])
        market_price = quote.get("price") if quote else None
        qty = float(p["quantity"])
        avg_cost = float(p["avg_cost"])
        cost_basis = qty * avg_cost
        market_value = qty * (
            float(market_price) if market_price is not None else avg_cost
        )
        unrealized_pnl = market_value - cost_basis
        enriched.append(
            {
                **p,
                "market_price": (
                    float(market_price) if market_price is not None else None
                ),
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": (
                    unrealized_pnl / cost_basis * 100 if cost_basis else 0.0
                ),
            }
        )
    return enriched


@app.get("/api/ibkr/trades")
async def ibkr_trades(
    limit: int = Query(50, ge=1, le=200),
    before_id: int | None = Query(default=None),
    min_value: float = Query(100.0, ge=0),
    _=Depends(api_key_dep),
):
    return await IBKR_REPO.list_trades(
        limit=limit, before_id=before_id, min_value=min_value
    )


@app.get("/api/ibkr/account")
async def ibkr_account(request: Request, _=Depends(api_key_dep)):
    gateway: IbkrGateway | None = request.app.state.ibkr_gateway
    if gateway is None or not gateway.is_connected():
        return {}
    return await gateway.get_account_summary()


@app.get("/api/trending-crypto")
async def trending_crypto(_=Depends(api_key_dep)):
    data = await get_trending_crypto()
    if data is None:
        raise HTTPException(status_code=503, detail="Service Unavailable")
    return data


@app.get("/api/signa/best-trades")
async def signa_best_trades(
    limit: int = Query(100, ge=1, le=250),
    _=Depends(api_key_dep),
):
    # Public getsigna.ai signals feed (tier 1/2; tier 3 is gated server-side).
    return await get_signa_best_trades(limit=limit)


@app.get("/api/signa/live-feed")
async def signa_live_feed(
    limit: int = Query(1500, ge=1, le=15000),
    _=Depends(api_key_dep),
):
    # Public getsigna.ai raw per-model live feed; only directional
    # (BUY/SELL/SHORT) signals are returned — AVOID/HOLD/WATCH are dropped.
    return await get_signa_live_feed(limit=limit)
