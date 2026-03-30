import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import sys
from unittest.mock import MagicMock
sys.modules['xclient'] = MagicMock()
sys.modules['xtimeline'] = MagicMock()
sys.modules['ticker_classifier'] = MagicMock()
sys.modules['ticker_classifier.classifier'] = MagicMock()
sys.modules['app.runtime.streamer'] = MagicMock()
sys.modules['app.runtime.streamer'].run_stream = MagicMock()

from app.api.main import app
from app.infra.db import init_db
from app.infra.repos import TweetRepo

# ---------------------------------------------------------------------------
# Sample tweet data used across multiple test modules
# ---------------------------------------------------------------------------

SAMPLE_TWEETS = [
    {
        "id": 1001,
        "text": "$AAPL is looking bullish! Great earnings report.",
        "user_name": "FinancialGuru",
        "user_screen_name": "finguru",
        "user_img": "https://example.com/avatar1.jpg",
        "url": "https://twitter.com/finguru/status/1001",
        "media": [],
        "tickers": ["AAPL"],
        "hashtags": ["stocks", "investing"],
        "title": "AAPL bullish signal",
        "media_types": [],
        "created_at": None,
        "assets": [
            {
                "symbol": "AAPL",
                "kind": "EQUITY",
                "name": "Apple Inc.",
                "market_cap": 3_000_000_000_000,
                "meta": {},
                "financials": {
                    "price": 185.0,
                    "change_percent": 1.5,
                    "volume": 80_000_000,
                    "website": "https://finance.yahoo.com/quote/AAPL",
                },
            }
        ],
    },
    {
        "id": 1002,
        "text": "#BTC to the moon! #crypto",
        "user_name": "CryptoKing",
        "user_screen_name": "cryptoking",
        "user_img": "https://example.com/avatar2.jpg",
        "url": "https://twitter.com/cryptoking/status/1002",
        "media": ["https://example.com/image.jpg"],
        "tickers": ["BTC"],
        "hashtags": ["BTC", "crypto"],
        "title": "BTC moon shot",
        "media_types": ["photo"],
        "created_at": None,
        "assets": [
            {
                "symbol": "BTC",
                "kind": "CRYPTO",
                "name": "Bitcoin",
                "market_cap": 900_000_000_000,
                "meta": {},
                "financials": {
                    "price": 45000.0,
                    "change_percent": 3.2,
                    "volume": 25_000_000_000.0,
                    "website": "https://www.coingecko.com/en/coins/bitcoin",
                },
            }
        ],
    },
    {
        "id": 1003,
        "text": "Markets looking volatile today. $SPY $QQQ",
        "user_name": "MarketWatcher",
        "user_screen_name": "mktwatch",
        "user_img": "https://example.com/avatar3.jpg",
        "url": "https://twitter.com/mktwatch/status/1003",
        "media": [],
        "tickers": ["SPY", "QQQ"],
        "hashtags": [],
        "title": "Market volatility",
        "media_types": [],
        "created_at": None,
        "assets": [],
    },
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client():
    # httpx ASGITransport does not guarantee FastAPI lifespan startup in tests,
    # so initialize auth state explicitly for dependency checks.
    app.state.API_KEY = "test-api-key"
    # ASGITransport is the modern way to test FastAPI apps with httpx
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def db_engine():
    """In-memory async SQLite engine with schema applied."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    await init_db(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def tweet_repo(db_engine):
    """TweetRepo backed by an in-memory database."""
    Session = async_sessionmaker(db_engine, expire_on_commit=False)
    return TweetRepo(Session)
