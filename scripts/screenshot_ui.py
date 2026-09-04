#!/usr/bin/env python3
"""Screenshot a dashboard route with the API stubbed, for review or in a PR.

Why stub rather than run the backend: the upstreams (Yahoo, CoinMarketCap, X)
are unreachable from sandboxed and CI environments, and live market data makes
every capture different anyway. Intercepting `/api/**` in the browser gives a
deterministic picture, needs no backend, and — more usefully — can render states
that are hard to reach on demand, like an asset sitting exactly at its all-time
high, or a holding whose price history failed to load.

    python scripts/screenshot_ui.py --route /portfolio
    python scripts/screenshot_ui.py --route /portfolio --scenario empty
    python scripts/screenshot_ui.py --route / --theme light --out /tmp/home.png

Requires the `dev` extra (`pip install -e ".[dev]"`) for Playwright. Chromium
comes from the environment; no `playwright install` is needed here.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import socket
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DEFAULT_PORT = 5179  # off the usual dev port so it never fights `npm run dev`


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _series(days: int, start: float, end: float, wobble: float) -> list[float]:
    """A smooth, deterministic price path from `start` to `end`."""
    return [
        start
        + (end - start) * (i / max(days - 1, 1))
        + wobble * math.sin(i / 3.0)
        + wobble * 0.4 * math.sin(i / 7.0)
        for i in range(days)
    ]


def _portfolio_history(days: int = 120) -> dict:
    insights = _portfolio_insights()
    cost_basis = insights["totals"]["cost_basis"]
    end_value = insights["totals"]["market_value"]
    today = date.today()
    values = _series(days, cost_basis * 0.94, end_value, end_value * 0.005)
    values[-1] = end_value

    points = []
    for offset, value in enumerate(values):
        stamp = (today - timedelta(days=days - 1 - offset)).isoformat()
        # The last third is "recorded" to show the three provenance labels.
        if offset == len(values) - 1:
            origin = "live"
        elif offset > days * 0.66:
            origin = "snapshot"
        else:
            origin = "reconstructed"
        points.append(
            {
                "t": stamp,
                "value": round(value, 2),
                "cost_basis": cost_basis,
                "pnl": round(value - cost_basis, 2),
                "pnl_percent": round((value - cost_basis) / cost_basis * 100, 2),
                "source": origin,
            }
        )

    end = points[-1]["value"]
    start = points[0]["value"]
    return {
        "source": "manual",
        "available_ranges": ["1W", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"],
        "holdings": [p["symbol"] for p in insights["positions"]],
        "totals": insights["totals"],
        "range": "3M",
        "points": points,
        "cost_basis": cost_basis,
        "start_value": start,
        "end_value": end,
        "change": round(end - start, 2),
        "change_percent": round((end - start) / start * 100, 2),
        "missing_symbols": [],
    }


def _position(
    symbol: str,
    quantity: float,
    avg_cost: float,
    price: float,
    weight: float,
    stats: dict | None,
) -> dict:
    cost_basis = quantity * avg_cost
    market_value = quantity * price
    pnl = market_value - cost_basis
    return {
        "symbol": symbol,
        "quantity": quantity,
        "avg_cost": avg_cost,
        "cost_basis": cost_basis,
        "currency": "USD",
        "market_price": price,
        "market_value": market_value,
        "unrealized_pnl": pnl,
        "unrealized_pnl_percent": pnl / cost_basis * 100,
        "change_percent": 1.4,
        "weight_percent": weight,
        "website": f"https://finance.yahoo.com/quote/{symbol}",
        "stats": stats,
    }


def _stats(
    symbol: str,
    price: float,
    ath: float,
    ath_date: str,
    atl: float,
    atl_date: str,
    low_52: float,
    high_52: float,
    flags: list[dict],
    days_since_ath: int,
) -> dict:
    return {
        "symbol": symbol,
        "price": price,
        "last_close": price,
        "history_start": "1999-01-04",
        "all_time_high": {"value": ath, "date": ath_date},
        "all_time_low": {"value": atl, "date": atl_date},
        "week_52_high": {"value": high_52, "date": ath_date},
        "week_52_low": {"value": low_52, "date": "2025-11-14"},
        "from_ath_percent": (price - ath) / ath * 100,
        "from_atl_percent": (price - atl) / atl * 100,
        "from_52w_high_percent": (price - high_52) / high_52 * 100,
        "from_52w_low_percent": (price - low_52) / low_52 * 100,
        "range_position_52w": max(
            0.0, min(100.0, (price - low_52) / (high_52 - low_52) * 100)
        ),
        "days_since_ath": days_since_ath,
        "days_since_atl": 4_100,
        "flags": flags,
    }


def _portfolio_insights() -> dict:
    positions = [
        _position(
            "NVDA",
            120,
            98.40,
            184.20,
            42.1,
            _stats(
                "NVDA",
                184.20,
                184.90,
                (date.today() - timedelta(days=1)).isoformat(),
                0.34,
                "1999-10-08",
                86.60,
                184.90,
                [{"code": "at_ath", "label": "All-time high", "tone": "bullish"}],
                1,
            ),
        ),
        _position(
            "AAPL",
            140,
            168.00,
            212.55,
            28.4,
            _stats(
                "AAPL",
                212.55,
                221.30,
                (date.today() - timedelta(days=18)).isoformat(),
                0.05,
                "1982-07-08",
                164.10,
                221.30,
                [{"code": "near_ath", "label": "4.0% below ATH", "tone": "bullish"}],
                18,
            ),
        ),
        _position(
            "MSFT",
            36,
            402.10,
            438.90,
            18.9,
            _stats(
                "MSFT",
                438.90,
                512.40,
                (date.today() - timedelta(days=64)).isoformat(),
                0.09,
                "1986-03-24",
                366.50,
                512.40,
                [],
                64,
            ),
        ),
        _position(
            "TSLA",
            48,
            268.00,
            186.40,
            10.6,
            _stats(
                "TSLA",
                186.40,
                479.86,
                "2021-11-04",
                1.05,
                "2010-07-06",
                181.20,
                402.00,
                [
                    {
                        "code": "near_52w_low",
                        "label": "Near 52-week low",
                        "tone": "bearish",
                    }
                ],
                1_390,
            ),
        ),
    ]

    market_value = sum(p["market_value"] for p in positions)
    cost_basis = sum(p["cost_basis"] for p in positions)
    highlights = [
        {
            "symbol": p["symbol"],
            "weight_percent": p["weight_percent"],
            **flag,
        }
        for p in positions
        for flag in (p["stats"] or {}).get("flags", [])
    ]

    return {
        "source": "manual",
        "totals": {
            "positions": len(positions),
            "market_value": market_value,
            "cost_basis": cost_basis,
            "unrealized_pnl": market_value - cost_basis,
            "unrealized_pnl_percent": (market_value - cost_basis) / cost_basis * 100,
        },
        "positions": positions,
        "highlights": highlights,
        **_diversification(positions, market_value),
    }


#: Static stand-in for the `ticker_classifier` sector lookup the real API
#: makes at request time — the screenshot fixture has no network access.
_SECTOR_BY_SYMBOL = {
    "NVDA": "Technology",
    "AAPL": "Technology",
    "MSFT": "Technology",
    "TSLA": "Consumer Cyclical",
}


def _diversification(positions: list[dict], total_value: float) -> dict:
    groups: dict[str, dict] = {}
    for position in positions:
        sector = _SECTOR_BY_SYMBOL.get(position["symbol"], "Unclassified")
        group = groups.setdefault(
            sector, {"sector": sector, "market_value": 0.0, "symbols": []}
        )
        group["market_value"] += position["market_value"]
        group["symbols"].append(position["symbol"])

    sectors = [
        {
            **group,
            "weight_percent": (
                group["market_value"] / total_value * 100 if total_value else 0.0
            ),
        }
        for group in groups.values()
    ]
    sectors.sort(key=lambda s: s["market_value"], reverse=True)

    top_holding = max(positions, key=lambda p: p["weight_percent"])
    top_sector = sectors[0]

    return {
        "sectors": sectors,
        "diversification": {
            "label": "moderate",
            "tone": "neutral",
            "holding_hhi": sum((p["weight_percent"] / 100) ** 2 for p in positions),
            "effective_holdings": len(positions),
            "sector_hhi": sum((s["weight_percent"] / 100) ** 2 for s in sectors),
            "effective_sectors": len(sectors),
            "top_holding": {
                "symbol": top_holding["symbol"],
                "weight_percent": top_holding["weight_percent"],
            },
            "top_sector": {
                "sector": top_sector["sector"],
                "weight_percent": top_sector["weight_percent"],
            },
        },
    }


def _empty_history() -> dict:
    return {
        "source": "manual",
        "range": "3M",
        "available_ranges": ["1W", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"],
        "holdings": [],
        "points": [],
        "cost_basis": 0.0,
        "start_value": None,
        "end_value": None,
        "change": None,
        "change_percent": None,
        "missing_symbols": [],
    }


def _empty_insights() -> dict:
    return {
        "source": "manual",
        "totals": {
            "positions": 0,
            "market_value": 0.0,
            "cost_basis": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
        },
        "positions": [],
        "highlights": [],
        "sectors": [],
        "diversification": {
            "label": "unrated",
            "tone": "neutral",
            "holding_hhi": None,
            "effective_holdings": None,
            "sector_hhi": None,
            "effective_sectors": None,
            "top_holding": None,
            "top_sector": None,
        },
    }


# (ticker, sector, industry, market cap in billions, change percent) -- a
# representative slice of the S&P 500 across sectors/industries, sized and
# priced so the market heatmap treemap renders with the same kind of shape
# (a few giant boxes, lots of small ones) as the real thing.
_SPY_HEATMAP_ROWS: list[tuple[str, str, str, float, float]] = [
    ("NVDA", "Technology", "Semiconductors", 3300, 4.06),
    ("AVGO", "Technology", "Semiconductors", 1450, 1.31),
    ("AMD", "Technology", "Semiconductors", 260, 2.48),
    ("INTC", "Technology", "Semiconductors", 180, 4.42),
    ("TXN", "Technology", "Semiconductors", 165, 2.25),
    ("QCOM", "Technology", "Semiconductors", 175, -3.24),
    ("MU", "Technology", "Semiconductors", 150, 4.99),
    ("ADI", "Technology", "Semiconductors", 105, 1.69),
    ("AAPL", "Technology", "Consumer Electronics", 3400, -0.76),
    ("MSFT", "Technology", "Software Infrastructure", 3150, -1.52),
    ("ORCL", "Technology", "Software Infrastructure", 480, -2.75),
    ("CRWD", "Technology", "Software Infrastructure", 90, 12.14),
    ("PANW", "Technology", "Software Infrastructure", 115, 6.97),
    ("PLTR", "Technology", "Software Infrastructure", 340, 2.88),
    ("JPM", "Financial Services", "Banks", 700, 2.52),
    ("BAC", "Financial Services", "Banks", 330, 1.92),
    ("WFC", "Financial Services", "Banks", 250, -2.59),
    ("C", "Financial Services", "Banks", 150, -5.28),
    ("MS", "Financial Services", "Capital Markets", 200, 3.38),
    ("GS", "Financial Services", "Capital Markets", 190, 9.3),
    ("SCHW", "Financial Services", "Capital Markets", 150, 0.32),
    ("V", "Financial Services", "Credit Services", 620, -0.49),
    ("MA", "Financial Services", "Credit Services", 480, 0.09),
    ("AXP", "Financial Services", "Credit Services", 210, 0.21),
    ("BRKB", "Financial Services", "Insurance", 1000, -2.23),
    ("CB", "Financial Services", "Insurance", 100, -2.23),
    ("PGR", "Financial Services", "Insurance", 140, -3.49),
    ("GOOGL", "Communication Services", "Internet Content & Information", 2200, 1.98),
    ("GOOG", "Communication Services", "Internet Content & Information", 2200, 1.88),
    ("META", "Communication Services", "Internet Content & Information", 1500, 0.67),
    ("NFLX", "Communication Services", "Entertainment", 450, -0.4),
    ("DIS", "Communication Services", "Entertainment", 200, -0.17),
    ("TMUS", "Communication Services", "Telecom Services", 260, -0.71),
    ("VZ", "Communication Services", "Telecom Services", 170, -0.54),
    ("AMZN", "Consumer Cyclical", "Internet Retail", 2200, 0.09),
    ("TSLA", "Consumer Cyclical", "Automotive", 1050, 0.37),
    ("MCD", "Consumer Cyclical", "Restaurants", 210, -1.35),
    ("SBUX", "Consumer Cyclical", "Restaurants", 110, -1.06),
    ("HD", "Consumer Cyclical", "Home Improvement Retail", 380, 0.24),
    ("BKNG", "Consumer Cyclical", "Travel & Leisure", 160, -0.57),
    ("LLY", "Healthcare", "Drug Manufacturers", 750, -2.37),
    ("JNJ", "Healthcare", "Drug Manufacturers", 380, -1.55),
    ("ABBV", "Healthcare", "Drug Manufacturers", 340, -1.29),
    ("MRK", "Healthcare", "Drug Manufacturers", 250, -2.62),
    ("UNH", "Healthcare", "Healthcare Plans", 460, -0.91),
    ("AMGN", "Healthcare", "Biotechnology", 160, -1.4),
    ("GILD", "Healthcare", "Biotechnology", 120, -0.95),
    ("TMO", "Healthcare", "Diagnostics & Research", 210, 1.11),
    ("RTX", "Industrials", "Aerospace & Defense", 170, -1.36),
    ("BA", "Industrials", "Aerospace & Defense", 130, 0.8),
    ("HON", "Industrials", "Aerospace & Defense", 140, 0.23),
    ("GE", "Industrials", "Specialty Industrial Machinery", 220, -0.01),
    ("CAT", "Industrials", "Specialty Industrial Machinery", 170, 0.27),
    ("UNP", "Industrials", "Railroads", 140, -0.33),
    ("WMT", "Consumer Defensive", "Discount Stores", 700, -0.98),
    ("COST", "Consumer Defensive", "Discount Stores", 400, -0.52),
    ("KO", "Consumer Defensive", "Beverages", 290, -1.38),
    ("PEP", "Consumer Defensive", "Beverages", 220, -2.16),
    ("PM", "Consumer Defensive", "Tobacco", 230, -2.31),
    ("XOM", "Energy", "Oil & Gas Integrated", 500, 0.39),
    ("CVX", "Energy", "Oil & Gas Integrated", 290, -0.24),
    ("NEE", "Utilities", "Utilities - Regulated Electric", 160, 1.36),
    ("GEV", "Utilities", "Utilities - Renewable", 130, 2.34),
    ("PLD", "Real Estate", "REIT - Industrial", 100, 0.66),
    ("WELL", "Real Estate", "REIT - Healthcare Facilities", 90, 0.66),
    ("LIN", "Basic Materials", "Chemicals", 220, -0.27),
    ("SHW", "Basic Materials", "Chemicals", 90, 1.01),
]


def _spy_heatmap_data() -> dict:
    rows = []
    for (
        ticker,
        sector,
        industry,
        marketcap_billions,
        change_percent,
    ) in _SPY_HEATMAP_ROWS:
        prev_close = 100.0
        close = prev_close * (1 + change_percent / 100)
        rows.append(
            {
                "ticker": ticker,
                "sector": sector,
                "industry": industry,
                "close": close,
                "prev_close": prev_close,
                "marketcap": marketcap_billions * 1_000_000_000,
            }
        )
    return {"data": rows}


# ---------------------------------------------------------------------------
# Market data fixtures (stocks/crypto/forex/options/home overview)
#
# One realistic payload per endpoint that the "loaded" scenario didn't cover
# before: without these, the catch-all answers with `[]`/`{}` and the widget
# is left on its empty or error state — which is what a first-time visitor to
# a route saw. Add here whenever a new widget/hook starts hitting a fresh
# endpoint, so the screenshot (and manual `npm run dev` browsing against this
# stub) show a populated dashboard instead of a wall of "no data" cards.
# ---------------------------------------------------------------------------


def _stock_fear_greed() -> dict:
    return {"value": 62, "status": "Greed", "change": "+4"}


def _crypto_fear_greed() -> dict:
    return {"value": 54, "status": "Neutral", "change": "-2"}


def _market_mover(
    symbol: str,
    name: str,
    price: float,
    extended_price: float,
    change_pct: float,
    volume: int,
    market_cap: int,
) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "extended_price": extended_price,
        "change_pct": change_pct,
        "volume": volume,
        "market_cap": market_cap,
    }


def _market_movers() -> dict:
    return {
        "session_type": "pre-market",
        "gainers": [
            _market_mover(
                "SMCI",
                "Super Micro Computer",
                42.10,
                46.80,
                11.16,
                8_200_000,
                25_000_000_000,
            ),
            _market_mover(
                "PLTR",
                "Palantir Technologies",
                68.40,
                71.20,
                4.09,
                5_600_000,
                150_000_000_000,
            ),
            _market_mover(
                "RIVN",
                "Rivian Automotive",
                12.30,
                13.05,
                6.10,
                4_100_000,
                12_000_000_000,
            ),
        ],
        "losers": [
            _market_mover(
                "INTC", "Intel Corp", 21.50, 19.80, -7.91, 6_900_000, 91_000_000_000
            ),
            _market_mover(
                "PYPL",
                "PayPal Holdings",
                58.10,
                55.60,
                -4.30,
                3_200_000,
                55_000_000_000,
            ),
            _market_mover(
                "BA", "Boeing Co", 178.20, 172.40, -3.25, 2_800_000, 105_000_000_000
            ),
        ],
        "stale": False,
    }


def _empty_market_movers() -> dict:
    return {"session_type": "pre-market", "gainers": [], "losers": [], "stale": False}


def _mover_item(
    symbol: str,
    name: str,
    price: float,
    change_pct: float,
    volume: int,
    market_cap: int,
) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "price": price,
        "change_pct": change_pct,
        "volume": volume,
        "market_cap": market_cap,
    }


def _markets_movers() -> dict:
    return {
        "market": "usa",
        "category": "gainers",
        "movers": [
            _mover_item(
                "SMCI", "Super Micro Computer", 46.80, 11.16, 8_200_000, 25_000_000_000
            ),
            _mover_item(
                "PLTR", "Palantir Technologies", 71.20, 4.09, 5_600_000, 150_000_000_000
            ),
            _mover_item(
                "RIVN", "Rivian Automotive", 13.05, 6.10, 4_100_000, 12_000_000_000
            ),
        ],
    }


def _empty_markets_movers() -> dict:
    return {"market": "usa", "category": "gainers", "movers": []}


def _extended_hours() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "session": "pre-market",
        "window_start": now.replace(hour=8, minute=0).isoformat(),
        "window_end": now.replace(hour=13, minute=30).isoformat(),
        "futures": [
            {
                "label": "S&P 500",
                "symbol": "ES=F",
                "price": 5920.25,
                "change_pct": 0.32,
            },
            {
                "label": "Nasdaq 100",
                "symbol": "NQ=F",
                "price": 21150.50,
                "change_pct": 0.48,
            },
            {
                "label": "Dow Jones",
                "symbol": "YM=F",
                "price": 44210.00,
                "change_pct": 0.11,
            },
        ],
        "etfs": [
            {
                "symbol": "SPY",
                "price": 590.12,
                "extended_price": 591.80,
                "extended_change_pct": 0.28,
            },
            {
                "symbol": "QQQ",
                "price": 512.44,
                "extended_price": 515.10,
                "extended_change_pct": 0.52,
            },
        ],
        "tweet_stats": {
            "total_mentions": 128,
            "top_tickers": [
                {"ticker": "NVDA", "mentions": 22, "sentiment": "BULL"},
                {"ticker": "AAPL", "mentions": 14, "sentiment": "NEUTRAL"},
                {"ticker": "TSLA", "mentions": 11, "sentiment": "BEAR"},
            ],
            "sentiment_distribution": {"BULL": 62, "BEAR": 30, "NEUTRAL": 36},
        },
    }


def _empty_extended_hours() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "session": "pre-market",
        "window_start": now.replace(hour=8, minute=0).isoformat(),
        "window_end": now.replace(hour=13, minute=30).isoformat(),
        "futures": [],
        "etfs": [],
        "tweet_stats": {
            "total_mentions": 0,
            "top_tickers": [],
            "sentiment_distribution": {"BULL": 0, "BEAR": 0, "NEUTRAL": 0},
        },
    }


def _market_hours() -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "exchange": "NYSE",
            "session": "pre-market",
            "is_open": False,
            "as_of": now,
            "timezone": "America/New_York",
            "next_open": None,
            "next_close": None,
        },
        {
            "exchange": "NASDAQ",
            "session": "pre-market",
            "is_open": False,
            "as_of": now,
            "timezone": "America/New_York",
            "next_open": None,
            "next_close": None,
        },
        {
            "exchange": "LSE",
            "session": "closed",
            "is_open": False,
            "as_of": now,
            "timezone": "Europe/London",
            "next_open": None,
            "next_close": None,
        },
    ]


def _stock_halts() -> list[dict]:
    return [
        {"Time": "09:42:11", "Issue Symbol": "GME", "Resumption Time": "09:47:11"},
        {"Time": "10:05:03", "Issue Symbol": "AMC"},
    ]


def _stocktwits() -> list[dict]:
    return [
        {
            "stock_id": 1,
            "symbol": "TSLA",
            "name": "Tesla Inc",
            "price": "186.40",
            "val": "3120",
        },
        {
            "stock_id": 2,
            "symbol": "NVDA",
            "name": "NVIDIA Corp",
            "price": "184.20",
            "val": "2894",
        },
        {
            "stock_id": 3,
            "symbol": "AAPL",
            "name": "Apple Inc",
            "price": "212.55",
            "val": "1745",
        },
        {
            "stock_id": 4,
            "symbol": "SMCI",
            "name": "Super Micro Computer",
            "price": "42.10",
            "val": "1032",
        },
    ]


def _binance_mover(symbol: str, pct: float, price: float, volume: int) -> dict:
    return {
        "symbol": symbol,
        "price_change_percent": pct,
        "price": price,
        "volume": volume,
        "website": f"https://www.binance.com/en/trade/{symbol}",
    }


def _binance_gainers_losers() -> dict:
    return {
        "gainers": [
            _binance_mover("SOLUSDT", 8.4, 224.10, 1_200_000),
            _binance_mover("SUIUSDT", 6.1, 3.82, 800_000),
        ],
        "losers": [
            _binance_mover("DOGEUSDT", -5.2, 0.198, 950_000),
            _binance_mover("ADAUSDT", -3.7, 0.71, 610_000),
        ],
    }


def _empty_binance_gainers_losers() -> dict:
    return {"gainers": [], "losers": []}


def _trending_crypto() -> list[dict]:
    return [
        {
            "name": "Bitcoin",
            "symbol": "BTC",
            "slug": "bitcoin",
            "price": 96_500.0,
            "change_24h": 2.14,
            "volume_24h": 38_000_000_000,
            "website": "https://coinmarketcap.com/currencies/bitcoin/",
        },
        {
            "name": "Ethereum",
            "symbol": "ETH",
            "slug": "ethereum",
            "price": 3_420.0,
            "change_24h": 1.32,
            "volume_24h": 15_000_000_000,
            "website": "https://coinmarketcap.com/currencies/ethereum/",
        },
        {
            "name": "Solana",
            "symbol": "SOL",
            "slug": "solana",
            "price": 224.10,
            "change_24h": 8.4,
            "volume_24h": 4_200_000_000,
            "website": "https://coinmarketcap.com/currencies/solana/",
        },
    ]


def _treemap() -> dict:
    coins = [
        ("Bitcoin", "BTC", 96_500.0, 2.14, 1_900_000_000_000, 38_000_000_000),
        ("Ethereum", "ETH", 3_420.0, 1.32, 410_000_000_000, 15_000_000_000),
        ("Solana", "SOL", 224.10, 8.4, 105_000_000_000, 4_200_000_000),
        ("XRP", "XRP", 2.31, -1.8, 132_000_000_000, 3_100_000_000),
        ("BNB", "BNB", 640.0, 0.6, 93_000_000_000, 1_800_000_000),
        ("DOGE", "DOGE", 0.198, -5.2, 29_000_000_000, 950_000_000),
    ]
    return {
        "data": [
            {"n": n, "s": s, "p": p, "ch": ch, "mc": mc, "v": v}
            for n, s, p, ch, mc, v in coins
        ]
    }


def _empty_treemap() -> dict:
    return {"data": []}


def _mention_heat() -> list[dict]:
    return [
        {
            "ticker": "NVDA",
            "mentions": 20,
            "avg_sentiment_24h": 0.42,
            "sentiment_label_24h": "BULL",
            "asset_kind": "EQUITY",
            "price_direction": 1,
        },
        {
            "ticker": "BTC",
            "mentions": 15,
            "avg_sentiment_24h": 0.18,
            "sentiment_label_24h": "BULL",
            "asset_kind": "CRYPTO",
            "price_direction": 1,
        },
        {
            "ticker": "TSLA",
            "mentions": 12,
            "avg_sentiment_24h": -0.22,
            "sentiment_label_24h": "BEAR",
            "asset_kind": "EQUITY",
            "price_direction": -1,
        },
        {
            "ticker": "SOL",
            "mentions": 9,
            "avg_sentiment_24h": 0.31,
            "sentiment_label_24h": "BULL",
            "asset_kind": "CRYPTO",
            "price_direction": 1,
        },
        {
            "ticker": "EURUSD",
            "mentions": 6,
            "avg_sentiment_24h": 0.02,
            "sentiment_label_24h": "NEUTRAL",
            "asset_kind": "FOREX",
            "price_direction": 0,
        },
    ]


def _sentiment_shift() -> list[dict]:
    return [
        {
            "ticker": "NVDA",
            "mentions_24h": 20,
            "avg_sentiment_24h": 0.42,
            "avg_sentiment_prev": 0.10,
            "delta": 0.32,
            "sentiment_label_24h": "BULL",
            "sentiment_label_prev": "NEUTRAL",
            "asset_kind": "EQUITY",
        },
        {
            "ticker": "TSLA",
            "mentions_24h": 12,
            "avg_sentiment_24h": -0.22,
            "avg_sentiment_prev": 0.05,
            "delta": -0.27,
            "sentiment_label_24h": "BEAR",
            "sentiment_label_prev": "NEUTRAL",
            "asset_kind": "EQUITY",
        },
        {
            "ticker": "SOL",
            "mentions_24h": 9,
            "avg_sentiment_24h": 0.31,
            "avg_sentiment_prev": 0.29,
            "delta": 0.02,
            "sentiment_label_24h": "BULL",
            "sentiment_label_prev": "BULL",
            "asset_kind": "CRYPTO",
        },
    ]


def _volume_baseline() -> list[dict]:
    return [
        {
            "ticker": "NVDA",
            "mentions_24h": 20,
            "baseline_7d_avg": 6.4,
            "volume_multiplier": 3.1,
            "asset_kind": "EQUITY",
        },
        {
            "ticker": "SOL",
            "mentions_24h": 9,
            "baseline_7d_avg": 2.1,
            "volume_multiplier": 4.3,
            "asset_kind": "CRYPTO",
        },
        {
            "ticker": "SMCI",
            "mentions_24h": 7,
            "baseline_7d_avg": 1.5,
            "volume_multiplier": 4.7,
            "asset_kind": "EQUITY",
        },
    ]


def _hidden_gems() -> list[dict]:
    today = date.today().isoformat()
    return [
        {
            "ticker": "SUI",
            "mentions_24h": 5,
            "gem_subtype": "new",
            "days_since_last": None,
            "first_seen": today,
            "last_seen": today,
            "asset_kind": "CRYPTO",
        },
        {
            "ticker": "IONQ",
            "mentions_24h": 4,
            "gem_subtype": "resurfacing",
            "days_since_last": 46,
            "first_seen": "2025-06-02",
            "last_seen": today,
            "asset_kind": "EQUITY",
        },
    ]


def _macro_strip() -> list[dict]:
    return [
        {
            "label": "SPX",
            "symbol": "^GSPC",
            "price": 5920.25,
            "change_pct": 0.32,
            "sparkline": [],
        },
        {
            "label": "NDX",
            "symbol": "^NDX",
            "price": 21150.50,
            "change_pct": 0.48,
            "sparkline": [],
        },
        {
            "label": "BTC",
            "symbol": "BTC",
            "price": 96_500.0,
            "change_pct": 2.14,
            "sparkline": [],
        },
        {
            "label": "ETH",
            "symbol": "ETH",
            "price": 3_420.0,
            "change_pct": 1.32,
            "sparkline": [],
        },
        {
            "label": "DXY",
            "symbol": "DX-Y.NYB",
            "price": 103.4,
            "change_pct": -0.12,
            "sparkline": [],
        },
        {
            "label": "VIX",
            "symbol": "^VIX",
            "price": 14.2,
            "change_pct": -1.8,
            "sparkline": [],
        },
    ]


def _forex_macro() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "as_of": now,
        "yield_curves": [
            {
                "label": "US Treasury",
                "points": [
                    {
                        "maturity": "3M",
                        "symbol": "US3M",
                        "yield_percent": 4.35,
                        "change_percent": -0.02,
                    },
                    {
                        "maturity": "2Y",
                        "symbol": "US2Y",
                        "yield_percent": 4.10,
                        "change_percent": 0.01,
                    },
                    {
                        "maturity": "10Y",
                        "symbol": "US10Y",
                        "yield_percent": 4.42,
                        "change_percent": 0.03,
                    },
                    {
                        "maturity": "30Y",
                        "symbol": "US30Y",
                        "yield_percent": 4.61,
                        "change_percent": 0.02,
                    },
                ],
                "spread_2s10s": 0.32,
            }
        ],
        "crypto_indices": [
            {
                "symbol": "BTC",
                "name": "Bitcoin",
                "price": 96_500.0,
                "category": "crypto",
                "change_percent": 2.14,
            },
            {
                "symbol": "ETH",
                "name": "Ethereum",
                "price": 3_420.0,
                "category": "crypto",
                "change_percent": 1.32,
            },
        ],
        "stock_forex_indices": [
            {
                "symbol": "SPX",
                "name": "S&P 500",
                "price": 5920.25,
                "category": "stock",
                "change_percent": 0.32,
            },
        ],
        "fx_indices": [
            {
                "symbol": "DXY",
                "name": "US Dollar Index",
                "price": 103.4,
                "category": "forex",
                "change_percent": -0.12,
            },
            {
                "symbol": "EURUSD",
                "name": "Euro / US Dollar",
                "price": 1.086,
                "category": "forex",
                "change_percent": 0.09,
            },
            {
                "symbol": "USDJPY",
                "name": "US Dollar / Yen",
                "price": 152.30,
                "category": "forex",
                "change_percent": -0.21,
            },
        ],
        "stock_forex_visible": True,
    }


def _empty_forex_macro() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "as_of": now,
        "yield_curves": [],
        "crypto_indices": [],
        "stock_forex_indices": [],
        "fx_indices": [],
        "stock_forex_visible": True,
    }


def _economic_events() -> list[dict]:
    today = date.today().isoformat()
    return [
        {
            "id": "cpi-us",
            "date": today,
            "time": "08:30",
            "zone": "united states",
            "currency": "USD",
            "event": "CPI m/m",
            "actual": "0.3%",
            "forecast": "0.2%",
            "previous": "0.2%",
            "impact_score": 3,
            "impact_emoji": "🔴",
            "source": "BLS",
        },
        {
            "id": "ecb-rate",
            "date": today,
            "time": "12:45",
            "zone": "euro zone",
            "currency": "EUR",
            "event": "ECB Rate Decision",
            "actual": None,
            "forecast": "3.25%",
            "previous": "3.25%",
            "impact_score": 3,
            "impact_emoji": "🔴",
            "source": "ECB",
        },
    ]


def _earnings_row(
    symbol: str,
    name: str,
    market_cap: float,
    eps_forecast: float | None,
    session: str,
    session_emoji: str | None,
    date_str: str,
) -> dict:
    return {
        "symbol": symbol,
        "name": name,
        "date": date_str,
        "session": session,
        "session_emoji": session_emoji,
        "market_cap": market_cap,
        "eps_forecast": eps_forecast,
        "num_estimates": 14 if eps_forecast is not None else None,
        "fiscal_quarter_ending": "Sep/2026",
        "last_year_eps": eps_forecast - 0.08 if eps_forecast is not None else None,
        "last_year_report_date": "08/01/2025",
        "website": f"https://www.nasdaq.com/market-activity/stocks/{symbol.lower()}/earnings",
    }


def _earnings_calendar() -> dict:
    today = date.today()
    day0 = today.isoformat()
    day1 = (today + timedelta(days=1)).isoformat()
    day2 = (today + timedelta(days=2)).isoformat()

    return {
        "start_date": day0,
        "end_date": (today + timedelta(days=6)).isoformat(),
        "days": [
            {
                "date": day0,
                "count": 2,
                "rows": [
                    _earnings_row(
                        "AAPL",
                        "Apple Inc.",
                        3_000_000_000_000,
                        1.25,
                        "after-hours",
                        "🌙",
                        day0,
                    ),
                    _earnings_row(
                        "NKE",
                        "Nike Inc.",
                        120_000_000_000,
                        0.55,
                        "pre-market",
                        "🌅",
                        day0,
                    ),
                ],
            },
            {
                "date": day1,
                "count": 1,
                "rows": [
                    _earnings_row(
                        "FDX",
                        "FedEx Corp.",
                        60_000_000_000,
                        4.10,
                        "unknown",
                        None,
                        day1,
                    ),
                ],
            },
            {"date": day2, "count": 0, "rows": []},
        ],
        "source": "nasdaq",
    }


def _empty_earnings_calendar() -> dict:
    today = date.today()
    return {
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=6)).isoformat(),
        "days": [
            {"date": (today + timedelta(days=i)).isoformat(), "count": 0, "rows": []}
            for i in range(7)
        ],
        "source": "nasdaq",
    }


def _option_contract(
    symbol: str,
    right: str,
    expiry: str,
    strike: float,
    last: float,
    change_pct: float,
    volume: int,
    open_interest: int,
) -> dict:
    return {
        "symbol": symbol,
        "contract_type": right,
        "expiry_date": expiry,
        "strike": strike,
        "last": last,
        "change_percent": change_pct,
        "volume": volume,
        "open_interest": open_interest,
        "website": None,
    }


def _options_overview() -> dict:
    return {
        "symbols": [
            {
                "symbol": "TSLA",
                "asset_class": "equity",
                "as_of": None,
                "call_volume": 82_000,
                "put_volume": 51_000,
                "total_volume": 133_000,
                "put_call_ratio": 0.62,
                "bullish_minus_bearish": 31_000,
                "top_call": _option_contract(
                    "TSLA", "CALL", "2026-09-19", 400, 8.20, 12.4, 5_400, 12_000
                ),
                "top_put": _option_contract(
                    "TSLA", "PUT", "2026-09-19", 350, 4.10, -6.2, 3_100, 8_900
                ),
            },
            {
                "symbol": "NVDA",
                "asset_class": "equity",
                "as_of": None,
                "call_volume": 64_000,
                "put_volume": 58_000,
                "total_volume": 122_000,
                "put_call_ratio": 0.91,
                "bullish_minus_bearish": 6_000,
                "top_call": None,
                "top_put": None,
            },
        ],
        "totals": {
            "call_volume": 146_000,
            "put_volume": 109_000,
            "total_volume": 255_000,
            "put_call_ratio": 0.75,
        },
        "bullish": [
            {
                "symbol": "TSLA",
                "call_volume": 82_000,
                "put_volume": 51_000,
                "bullish_minus_bearish": 31_000,
            },
        ],
        "bearish": [
            {
                "symbol": "NVDA",
                "call_volume": 64_000,
                "put_volume": 58_000,
                "bullish_minus_bearish": 6_000,
            },
        ],
        "most_active_contracts": [
            _option_contract(
                "TSLA", "CALL", "2026-09-19", 400, 8.20, 12.4, 5_400, 12_000
            ),
        ],
        "source": "nasdaq",
    }


def _options_chain() -> dict:
    return {
        "symbol": "AAPL",
        "underlying": {
            "name": "Apple Inc.",
            "last_price": 227.5,
            "change": 1.85,
            "change_percent": 0.82,
            "market_cap": 3_450_000_000_000,
            "year_high": 260.1,
            "year_low": 164.1,
            "volume": 48_000_000,
        },
        "expirations": ["2026-09-19", "2026-09-26", "2026-10-17"],
        "expiration": "2026-09-19",
        "contracts": [
            {
                "option_type": "CALL",
                "strike": 225.0,
                "bid": 6.10,
                "ask": 6.25,
                "last_price": 6.15,
                "volume": 4_200,
                "open_interest": 15_800,
                "implied_volatility": 0.28,
                "change_percent": 5.4,
                "in_the_money": True,
            },
            {
                "option_type": "PUT",
                "strike": 225.0,
                "bid": 3.40,
                "ask": 3.55,
                "last_price": 3.45,
                "volume": 2_600,
                "open_interest": 9_100,
                "implied_volatility": 0.31,
                "change_percent": -3.1,
                "in_the_money": False,
            },
            {
                "option_type": "CALL",
                "strike": 230.0,
                "bid": 3.20,
                "ask": 3.35,
                "last_price": 3.25,
                "volume": 3_100,
                "open_interest": 11_200,
                "implied_volatility": 0.27,
                "change_percent": 4.1,
                "in_the_money": False,
            },
        ],
        "source": "yfinance",
    }


def _empty_options_chain() -> dict:
    return {
        "symbol": "AAPL",
        "underlying": {},
        "expirations": [],
        "expiration": "",
        "contracts": [],
        "source": "yfinance",
    }


def _company_news() -> dict:
    return {
        "articles": [
            {
                "symbols": ["AAPL"],
                "title": "Apple unveils new product lineup ahead of holiday season",
                "excerpt": (
                    "The company announced updates across its product line "
                    "during a keynote event."
                ),
                "url": "https://example.com/news/aapl-lineup",
                "date": "2026-09-03T14:30:00Z",
                "source": "Reuters",
            },
            {
                "symbols": ["AAPL"],
                "title": "Analysts raise price targets after strong quarterly guidance",
                "excerpt": (
                    "Several Wall Street analysts increased their price targets "
                    "following the earnings call."
                ),
                "url": "https://example.com/news/aapl-targets",
                "date": "2026-09-02T09:15:00Z",
                "source": "Bloomberg",
            },
        ],
        "source": "yfinance",
    }


def _empty_company_news() -> dict:
    return {"articles": [], "source": "yfinance"}


def _signa_best_trades() -> list[dict]:
    return [
        {
            "source": "getsigna.ai",
            "symbol": "NVDA",
            "direction": "BULLISH",
            "grade": "A",
            "alert_tier": 1,
            "composite_score": 91.2,
            "confidence": 0.87,
            "model_count": 6,
            "regime": "trend",
            "categories": ["momentum"],
            "reason": "Breakout above 30d high with volume confirmation.",
            "key_drivers": ["volume surge", "sector strength"],
            "model_ids": ["m1", "m2"],
            "generated_at": None,
            "website": None,
        },
        {
            "source": "getsigna.ai",
            "symbol": "SOL",
            "direction": "BULLISH",
            "grade": "B+",
            "alert_tier": 2,
            "composite_score": 78.4,
            "confidence": 0.71,
            "model_count": 4,
            "regime": "trend",
            "categories": ["momentum", "on-chain"],
            "reason": "Relative strength breakout vs. majors.",
            "key_drivers": ["network activity"],
            "model_ids": ["m3"],
            "generated_at": None,
            "website": None,
        },
    ]


def _signa_live_feed() -> list[dict]:
    return [
        {
            "source": "getsigna.ai",
            "id": "sig-1",
            "symbol": "SOL",
            "signal": "BUY",
            "direction": "BULLISH",
            "model_id": "m1",
            "model_name": "Momentum-Alpha",
            "model_source": "getsigna.ai",
            "category": "momentum",
            "confidence": 0.78,
            "reason": "Relative strength breakout.",
            "entry_price": 224.10,
            "stop_level": 210.0,
            "target_price": 250.0,
            "position_size_pct": 2.5,
            "grade": "B+",
            "tier": 2,
            "score": 82.0,
            "conflict_detected": False,
            "created_at": None,
            "website": None,
        },
        {
            "source": "getsigna.ai",
            "id": "sig-2",
            "symbol": "INTC",
            "signal": "SHORT",
            "direction": "BEARISH",
            "model_id": "m2",
            "model_name": "Mean-Reversion-Beta",
            "model_source": "getsigna.ai",
            "category": "mean-reversion",
            "confidence": 0.64,
            "reason": "Rejected at 20d moving average on declining volume.",
            "entry_price": 21.50,
            "stop_level": 23.10,
            "target_price": 18.80,
            "position_size_pct": 1.5,
            "grade": "B",
            "tier": 2,
            "score": 70.0,
            "conflict_detected": False,
            "created_at": None,
            "website": None,
        },
    ]


def _trader_credibility() -> dict:
    """Keyed by lowercased screen name, matching `_sample_tweets()` authors
    (`chart_trader`, `crypto_watcher`) so the tweet-card badge has something
    to render in a `loaded` capture."""
    return {
        "chart_trader": {
            "horizon_days": 7,
            "graded_calls": 24,
            "correct_calls": 17,
            "hit_rate": 0.71,
            "avg_return_pct": 3.9,
        },
        "crypto_watcher": {
            "horizon_days": 7,
            "graded_calls": 9,
            "correct_calls": 3,
            "hit_rate": 0.33,
            "avg_return_pct": -2.4,
        },
    }


def _trader_leaderboard() -> list[dict]:
    return [
        {
            "user_screen_name": "finguru",
            "horizon_days": 7,
            "graded_calls": 42,
            "correct_calls": 29,
            "hit_rate": 0.69,
            "avg_return_pct": 4.8,
        },
        {
            "user_screen_name": "cryptoking",
            "horizon_days": 7,
            "graded_calls": 18,
            "correct_calls": 9,
            "hit_rate": 0.5,
            "avg_return_pct": 0.3,
        },
        {
            "user_screen_name": "bearishbob",
            "horizon_days": 7,
            "graded_calls": 11,
            "correct_calls": 3,
            "hit_rate": 0.27,
            "avg_return_pct": -6.1,
        },
    ]


def _reddit_wsb() -> list[dict]:
    now = int(datetime.now(timezone.utc).timestamp())
    return [
        {
            "id": "abc123",
            "subreddit": "wallstreetbets",
            "title": "NVDA to the moon \U0001f680",
            "description": "Loaded up on calls, this rally isn't done.",
            "author": "diamond_hands_42",
            "score": 4820,
            "num_comments": 312,
            "created_utc": now - 3_600,
            "url": "https://reddit.com/r/wallstreetbets/comments/abc123",
            "image_urls": [],
        },
        {
            "id": "def456",
            "subreddit": "wallstreetbets",
            "title": "Boeing puts printing",
            "description": "That guidance cut was brutal.",
            "author": "theta_gang_99",
            "score": 1204,
            "num_comments": 88,
            "created_utc": now - 7_200,
            "url": "https://reddit.com/r/wallstreetbets/comments/def456",
            "image_urls": [],
        },
    ]


def _sample_tweet(
    id_: int,
    text: str,
    user_name: str,
    screen_name: str,
    tickers: list[str],
    assets: list[dict],
    **extra: object,
) -> dict:
    now = datetime.now(timezone.utc)
    base: dict = {
        "id": id_,
        "text": text,
        "user_name": user_name,
        "user_screen_name": screen_name,
        "user_img": f"https://unavatar.io/twitter/{screen_name}",
        "url": f"https://x.com/{screen_name}/status/{id_}",
        "created_at": (now - timedelta(minutes=id_ * 7)).isoformat(),
        "media": [],
        "tickers": tickers,
        "hashtags": [],
        "title": "",
        "media_types": [],
        "replies": 12,
        "likes": 340,
        "views": 18_400,
        "retweets": 28,
        "sentiment_label": "BULLISH",
        "sentiment_emoji": "\U0001f7e2",
        "sentiment_score": 0.62,
        "assets": assets,
    }
    base.update(extra)
    return base


def _sample_tweets() -> list[dict]:
    return [
        _sample_tweet(
            1,
            "$NVDA breaking out on huge volume, semis leading the tape today.",
            "Chart Trader",
            "chart_trader",
            ["NVDA"],
            [
                {
                    "symbol": "NVDA",
                    "kind": "EQUITY",
                    "financials": {"price": 184.20, "change_percent": 4.06},
                }
            ],
        ),
        _sample_tweet(
            2,
            "$BTC reclaiming 96k, funding still neutral. Watching for a squeeze.",
            "Crypto Watcher",
            "crypto_watcher",
            ["BTC"],
            [
                {
                    "symbol": "BTC",
                    "kind": "CRYPTO",
                    "financials": {"price": 96_500.0, "change_percent": 2.14},
                }
            ],
        ),
        _sample_tweet(
            3,
            "$EURUSD holding the 1.08 handle ahead of the ECB decision.",
            "Macro Trader",
            "macro_trader",
            ["EURUSD"],
            [
                {
                    "symbol": "EURUSD",
                    "kind": "FOREX",
                    "financials": {"price": 1.086, "change_percent": 0.09},
                }
            ],
            sentiment_label="NEUTRAL",
            sentiment_emoji="⚪",
            sentiment_score=0.02,
        ),
        _sample_tweet(
            4,
            "$TSLA 400c volume is wild into the close, someone knows something.",
            "Options Flow",
            "options_flow",
            ["TSLA"],
            [
                {
                    "symbol": "TSLA",
                    "kind": "EQUITY",
                    "financials": {"price": 186.40, "change_percent": 0.37},
                }
            ],
            is_options_tweet=True,
        ),
        _sample_tweet(
            5,
            "$AAPL chart looking heavy under the 200d, watch $205 support.",
            "Chart Trader",
            "chart_trader",
            ["AAPL"],
            [
                {
                    "symbol": "AAPL",
                    "kind": "EQUITY",
                    "financials": {"price": 212.55, "change_percent": -0.76},
                }
            ],
            sentiment_label="BEARISH",
            sentiment_emoji="\U0001f534",
            sentiment_score=-0.31,
        ),
        _sample_tweet(
            6,
            "$SOL momentum building again, network activity at 3-month highs.",
            "Crypto Watcher",
            "crypto_watcher",
            ["SOL"],
            [
                {
                    "symbol": "SOL",
                    "kind": "CRYPTO",
                    "financials": {"price": 224.10, "change_percent": 8.4},
                }
            ],
        ),
    ]


def fixtures_for(scenario: str) -> dict[str, object]:
    """Map a URL fragment to the JSON served for it."""
    if scenario == "broken":
        # The payload that used to blank the whole dashboard: `summary` comes
        # back as a list, so `.totals.market_value` was read off it during
        # render. The panel now guards that access, so this renders with the
        # affected figures as N/A. It is a regression check on the degrade
        # path, not a demonstration of ErrorBoundary — that is covered by
        # ErrorBoundary.test.tsx, which is where a genuine throw is exercised.
        healthy = fixtures_for("loaded")
        return {**healthy, "/api/portfolio/summary": []}

    if scenario == "empty":
        return {
            "/api/portfolio/history": _empty_history(),
            "/api/portfolio/insights": _empty_insights(),
            "/api/portfolio/summary": {
                "totals": _empty_insights()["totals"],
                "positions": [],
            },
            "/api/ibkr/account": {},
            # Same object-shaped trap as the portfolio endpoints above: these
            # widgets read nested fields (`.gainers`, `.futures`, `.data`)
            # that don't exist on the catch-all's `[]`, so an explicit
            # zero-value shape is required to see the real empty state
            # instead of a render crash.
            "/api/stocks/market-movers": _empty_market_movers(),
            "/api/markets/movers": _empty_markets_movers(),
            "/api/stocks/extended-hours": _empty_extended_hours(),
            "/api/binance/gainers-losers": _empty_binance_gainers_losers(),
            "/api/treemap": _empty_treemap(),
            "/api/forex/macro": _empty_forex_macro(),
            "/api/spy-heatmap?": {"data": []},
            "/api/earnings/calendar": _empty_earnings_calendar(),
            "/api/options/chain": _empty_options_chain(),
            "/api/news/company": _empty_company_news(),
        }

    insights = _portfolio_insights()
    return {
        "/api/portfolio/history": _portfolio_history(),
        "/api/portfolio/insights": insights,
        # Object-shaped endpoints must be fixtured explicitly: the catch-all
        # below answers with a list, and a component reading `.totals` off it
        # throws during render.
        "/api/portfolio/summary": {
            "totals": insights["totals"],
            "positions": [
                {
                    "id": index + 1,
                    "broker": "IBKR",
                    "currency": "USD",
                    "is_active": True,
                    **position,
                }
                for index, position in enumerate(insights["positions"])
            ],
        },
        "/api/portfolio/positions": [
            {
                "id": index + 1,
                "broker": "IBKR",
                "symbol": position["symbol"],
                "quantity": position["quantity"],
                "avg_cost": position["avg_cost"],
                "currency": "USD",
                "opened_at": None,
                "notes": None,
                "is_active": True,
                "created_at": None,
                "updated_at": None,
            }
            for index, position in enumerate(insights["positions"])
        ],
        "/api/ibkr/account": {},
        "/api/ibkr/status": {
            "configured": False,
            "connected": False,
            "last_sync": None,
            "last_error": None,
        },
        # Object-shaped: the catch-all's `[]` would leave the heatmap and
        # SectorOverviewWidget on their empty states instead of rendering.
        # The trailing "?" keeps this from also matching the /sectors
        # sub-route below, since fragment matching is a plain substring test.
        "/api/spy-heatmap?": _spy_heatmap_data(),
        "/api/spy-heatmap/sectors": {
            "sectors": [
                {
                    "sector": "Technology",
                    "market_cap": 12_500_000_000_000,
                    "change_percent": 1.8,
                    "stock_count": 68,
                    "subsectors": [
                        {
                            "industry": "Semiconductors",
                            "market_cap": 5_200_000_000_000,
                            "change_percent": 3.4,
                            "stock_count": 14,
                        },
                        {
                            "industry": "Software",
                            "market_cap": 7_300_000_000_000,
                            "change_percent": 0.6,
                            "stock_count": 54,
                        },
                    ],
                },
                {
                    "sector": "Health Care",
                    "market_cap": 6_100_000_000_000,
                    "change_percent": -0.4,
                    "stock_count": 61,
                    "subsectors": [
                        {
                            "industry": "Biotechnology",
                            "market_cap": 1_900_000_000_000,
                            "change_percent": -1.9,
                            "stock_count": 20,
                        },
                        {
                            "industry": "Pharmaceuticals",
                            "market_cap": 4_200_000_000_000,
                            "change_percent": 0.3,
                            "stock_count": 41,
                        },
                    ],
                },
                {
                    "sector": "Financials",
                    "market_cap": 5_400_000_000_000,
                    "change_percent": 0.2,
                    "stock_count": 72,
                    "subsectors": [
                        {
                            "industry": "Other",
                            "market_cap": 5_400_000_000_000,
                            "change_percent": 0.2,
                            "stock_count": 72,
                        }
                    ],
                },
            ]
        },
        # Object-shaped list, but the catch-all's `[]` would leave
        # SectorMentionsWidget on its empty state instead of rendering.
        "/api/overview/sector-mentions": [
            {
                "sector": "Technology",
                "mentions": 41,
                "mention_score": 27,
                "unique_authors": 19,
                "unique_tickers": 3,
                "avg_sentiment_24h": 0.42,
                "sentiment_label_24h": "BULL",
                "top_tickers": [
                    {"ticker": "NVDA", "mentions": 20},
                    {"ticker": "MU", "mentions": 15},
                    {"ticker": "MSFT", "mentions": 6},
                ],
                "industries": [
                    {
                        "industry": "Semiconductors",
                        "mentions": 35,
                        "unique_tickers": 2,
                        "top_tickers": [
                            {"ticker": "NVDA", "mentions": 20},
                            {"ticker": "MU", "mentions": 15},
                        ],
                    },
                    {
                        "industry": "Software",
                        "mentions": 6,
                        "unique_tickers": 1,
                        "top_tickers": [{"ticker": "MSFT", "mentions": 6}],
                    },
                ],
            },
            {
                "sector": "Financials",
                "mentions": 18,
                "mention_score": 14,
                "unique_authors": 11,
                "unique_tickers": 2,
                "avg_sentiment_24h": 0.05,
                "sentiment_label_24h": "NEUTRAL",
                "top_tickers": [
                    {"ticker": "JPM", "mentions": 11},
                    {"ticker": "GS", "mentions": 7},
                ],
                "industries": [
                    {
                        "industry": "Banks",
                        "mentions": 18,
                        "unique_tickers": 2,
                        "top_tickers": [
                            {"ticker": "JPM", "mentions": 11},
                            {"ticker": "GS", "mentions": 7},
                        ],
                    },
                ],
            },
            {
                "sector": "Energy",
                "mentions": 9,
                "mention_score": 9,
                "unique_authors": 9,
                "unique_tickers": 1,
                "avg_sentiment_24h": -0.18,
                "sentiment_label_24h": "BEAR",
                "top_tickers": [{"ticker": "XOM", "mentions": 9}],
                "industries": [
                    {
                        "industry": "Other",
                        "mentions": 9,
                        "unique_tickers": 1,
                        "top_tickers": [{"ticker": "XOM", "mentions": 9}],
                    },
                ],
            },
        ],
        # Stocks route.
        "/api/stocks/fear-greed": _stock_fear_greed(),
        "/api/stocks/market-movers": _market_movers(),
        "/api/markets/movers": _markets_movers(),
        "/api/stocks/extended-hours": _extended_hours(),
        "/api/stocks/market-hours": _market_hours(),
        "/api/stock-halts": _stock_halts(),
        # Object-shaped: the catch-all's `[]` would leave EarningsCalendarWidget
        # reading `.days` off a list and throwing during render.
        "/api/earnings/calendar": _earnings_calendar(),
        "/api/stocktwits": _stocktwits(),
        # Crypto route.
        "/api/binance/gainers-losers": _binance_gainers_losers(),
        "/api/trending-crypto": _trending_crypto(),
        "/api/treemap": _treemap(),
        "/api/fear-greed": _crypto_fear_greed(),
        # Home / overview dashboard.
        "/api/overview/mention-heat": _mention_heat(),
        "/api/overview/sentiment-shift": _sentiment_shift(),
        "/api/overview/volume-baseline": _volume_baseline(),
        "/api/overview/hidden-gems": _hidden_gems(),
        "/api/overview/macro-strip": _macro_strip(),
        # Forex route.
        "/api/forex/macro": _forex_macro(),
        "/api/events/economic": _economic_events(),
        # Options route.
        "/api/options/overview": _options_overview(),
        "/api/options/chain": _options_chain(),
        # Company news (stocks route).
        "/api/news/company": _company_news(),
        # Signa route.
        "/api/signa/best-trades": _signa_best_trades(),
        "/api/signa/live-feed": _signa_live_feed(),
        # Traders route + tweet-card credibility badge.
        "/api/traders/leaderboard": _trader_leaderboard(),
        "/api/traders/credibility": _trader_credibility(),
        # Reddit (WSB) widget.
        "/api/reddit/wsb": _reddit_wsb(),
        # Timeline: without this every route's tweet feed (and the ticker /
        # user filter demo) sits on "No tweets in this filter yet."
        "/api/posts": _sample_tweets(),
    }


SCENARIOS = ("loaded", "empty", "broken")


# ---------------------------------------------------------------------------
# Browser + dev server
# ---------------------------------------------------------------------------


def _chromium_executable() -> str | None:
    """Prefer the environment's prebuilt Chromium over a managed download."""
    for pattern in (
        "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
        "/opt/pw-browsers/chromium/chrome-linux/chrome",
    ):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return None


def _port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port(port: int, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open(port):
            return
        time.sleep(0.3)
    raise RuntimeError(f"vite did not start on port {port} within {timeout:.0f}s")


def capture(
    route: str,
    out: Path,
    scenario: str,
    theme: str,
    port: int,
    width: int,
    height: int,
) -> Path:
    from playwright.sync_api import sync_playwright

    fixtures = fixtures_for(scenario)
    out.parent.mkdir(parents=True, exist_ok=True)

    def handle(route_obj, request):
        # SSE would hold the page open; the hook treats a failure as "no stream".
        if "/api/stream" in request.url:
            return route_obj.abort()

        for fragment, payload in fixtures.items():
            if fragment in request.url:
                return route_obj.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                )

        # Anything not fixtured still has to answer, or the UI sits on a skeleton.
        empty: object = [] if request.method == "GET" else {}
        return route_obj.fulfill(
            status=200, content_type="application/json", body=json.dumps(empty)
        )

    with sync_playwright() as pw:
        launch: dict = {}
        executable = _chromium_executable()
        if executable:
            launch["executable_path"] = executable

        browser = pw.chromium.launch(**launch)
        page = browser.new_page(
            viewport={"width": width, "height": height},
            color_scheme=theme,
            device_scale_factor=2,
        )
        page.route("**/api/**", handle)
        page.goto(f"http://127.0.0.1:{port}{route}", wait_until="networkidle")
        # Recharts animates in; let it settle before capturing.
        page.wait_for_timeout(900)
        page.screenshot(path=str(out), full_page=True)
        browser.close()

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", default="/portfolio", help="dashboard path")
    parser.add_argument("--out", type=Path, default=None, help="output PNG path")
    parser.add_argument("--scenario", choices=SCENARIOS, default="loaded")
    parser.add_argument("--theme", choices=("dark", "light"), default="dark")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()

    out = args.out or (
        ROOT
        / "artifacts"
        / f"{args.route.strip('/').replace('/', '-') or 'home'}-{args.scenario}-{args.theme}.png"
    )

    server = None
    if _port_open(args.port):
        print(f"[screenshot] reusing server already on :{args.port}")
    else:
        print(f"[screenshot] starting vite on :{args.port}")
        server = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(args.port), "--strictPort"],
            cwd=FRONTEND,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    try:
        _wait_for_port(args.port)
        path = capture(
            args.route,
            out,
            args.scenario,
            args.theme,
            args.port,
            args.width,
            args.height,
        )
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    print(f"[screenshot] wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
