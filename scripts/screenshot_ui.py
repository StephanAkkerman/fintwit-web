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
from datetime import date, timedelta
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
        # Object-shaped: the catch-all's `[]` would leave SectorOverviewWidget
        # on its empty state instead of showing the sector/subsector rows.
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
