"""Shared portfolio valuation logic.

The API endpoints, the snapshot worker and the overview widgets all need the
same three things: which symbols are held, what they are worth right now, and
what they were worth over time. Keeping that here avoids the three consumers
drifting apart.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ticker_price_data import get_stock_info

from ..infra.repos import IbkrRepo, PortfolioRepo
from ..services.price_history_service import (
    DEFAULT_RANGE,
    get_price_series,
    get_symbol_stats,
    normalize_range,
)

logger = logging.getLogger(__name__)

#: Holdings sources the API accepts. ``auto`` prefers live IBKR positions and
#: falls back to manually tracked ones.
HOLDINGS_SOURCES = ("auto", "manual", "ibkr")


def normalize_source(value: str | None) -> str:
    """Return a supported holdings source, defaulting to ``auto``."""
    key = (value or "").strip().lower()
    return key if key in HOLDINGS_SOURCES else "auto"


def aggregate_holdings(positions: list[dict]) -> list[dict]:
    """Collapse positions onto one row per symbol with a weighted average cost.

    :param positions: Rows carrying ``symbol``, ``quantity`` and ``avg_cost``.
    :return: One holding per symbol, largest cost basis first.
    """
    merged: dict[str, dict] = {}

    for position in positions:
        symbol = str(position.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        try:
            quantity = float(position.get("quantity") or 0.0)
            avg_cost = float(position.get("avg_cost") or 0.0)
        except (TypeError, ValueError):
            continue

        if quantity == 0:
            continue

        entry = merged.setdefault(
            symbol,
            {
                "symbol": symbol,
                "quantity": 0.0,
                "cost_basis": 0.0,
                "currency": position.get("currency") or "USD",
            },
        )
        entry["quantity"] += quantity
        entry["cost_basis"] += quantity * avg_cost

    holdings = []
    for entry in merged.values():
        quantity = entry["quantity"]
        if quantity == 0:
            continue
        holdings.append(
            {
                "symbol": entry["symbol"],
                "quantity": quantity,
                "avg_cost": entry["cost_basis"] / quantity,
                "cost_basis": entry["cost_basis"],
                "currency": entry["currency"],
            }
        )

    holdings.sort(key=lambda h: abs(h["cost_basis"]), reverse=True)
    return holdings


async def resolve_holdings(
    portfolio_repo: PortfolioRepo,
    ibkr_repo: IbkrRepo,
    source: str = "auto",
) -> tuple[str, list[dict]]:
    """Resolve the holdings to value, following the requested source.

    :param portfolio_repo: Repo for manually tracked positions.
    :param ibkr_repo: Repo for IBKR-synced positions.
    :param source: ``auto``, ``manual`` or ``ibkr``.
    :return: ``(resolved_source, holdings)``. ``resolved_source`` reports which
        source actually supplied the rows so the UI can label the chart.
    """
    source = normalize_source(source)

    async def _ibkr() -> list[dict]:
        rows = await ibkr_repo.list_positions()
        return aggregate_holdings([r for r in rows if r.get("sec_type") == "STK"])

    async def _manual() -> list[dict]:
        rows = await portfolio_repo.list_positions(active_only=True)
        return aggregate_holdings(rows)

    if source == "ibkr":
        return "ibkr", await _ibkr()
    if source == "manual":
        return "manual", await _manual()

    ibkr_holdings = await _ibkr()
    if ibkr_holdings:
        return "ibkr", ibkr_holdings
    return "manual", await _manual()


async def value_holdings(holdings: list[dict]) -> dict:
    """Attach live prices to holdings and total them up.

    Falls back to average cost when a quote is unavailable so a single failing
    symbol cannot blank out the whole portfolio value.

    :param holdings: Rows from :func:`aggregate_holdings`.
    :return: ``{"totals": {...}, "positions": [...]}``.
    """
    if not holdings:
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

    quotes = await asyncio.gather(
        *(get_stock_info(h["symbol"]) for h in holdings),
        return_exceptions=True,
    )

    valued: list[dict] = []
    total_market_value = 0.0
    total_cost_basis = 0.0

    for holding, quote in zip(holdings, quotes):
        quote_data = quote if isinstance(quote, dict) else None
        raw_price = quote_data.get("price") if quote_data else None
        market_price = float(raw_price) if raw_price is not None else None

        quantity = holding["quantity"]
        cost_basis = holding["cost_basis"]
        market_value = quantity * (
            market_price if market_price is not None else holding["avg_cost"]
        )
        unrealized_pnl = market_value - cost_basis

        total_market_value += market_value
        total_cost_basis += cost_basis

        valued.append(
            {
                **holding,
                "market_price": market_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": (
                    unrealized_pnl / cost_basis * 100 if cost_basis else 0.0
                ),
                "change_percent": (
                    quote_data.get("change_percent") if quote_data else None
                ),
                "website": quote_data.get("website") if quote_data else None,
            }
        )

    total_pnl = total_market_value - total_cost_basis
    for position in valued:
        position["weight_percent"] = (
            position["market_value"] / total_market_value * 100
            if total_market_value
            else 0.0
        )

    return {
        "totals": {
            "positions": len(valued),
            "market_value": total_market_value,
            "cost_basis": total_cost_basis,
            "unrealized_pnl": total_pnl,
            "unrealized_pnl_percent": (
                total_pnl / total_cost_basis * 100 if total_cost_basis else 0.0
            ),
        },
        "positions": valued,
    }


def _forward_filled(series: list[dict], timeline: list[str]) -> dict[str, float]:
    """Map every timeline stamp onto the most recent close at or before it.

    Stamps that precede the symbol's first data point reuse that first close, so
    a recently listed holding does not punch a hole in the portfolio total.
    """
    if not series:
        return {}

    by_stamp = {point["t"]: point["close"] for point in series}
    filled: dict[str, float] = {}
    last = series[0]["close"]

    for stamp in timeline:
        if stamp in by_stamp:
            last = by_stamp[stamp]
        filled[stamp] = last

    return filled


def _snapshot_overrides(snapshots: list[dict]) -> dict[str, dict]:
    """Index snapshots by calendar day, keeping the last one of each day."""
    by_day: dict[str, dict] = {}
    for snapshot in snapshots:
        captured = snapshot.get("captured_at")
        if not captured:
            continue
        by_day[str(captured)[:10]] = snapshot
    return by_day


async def build_value_history(
    holdings: list[dict],
    range_key: str = DEFAULT_RANGE,
    snapshots: list[dict] | None = None,
    live_totals: dict | None = None,
) -> dict:
    """Build the portfolio value series for a range.

    Value is reconstructed from each holding's historical closes at today's
    quantities, then overridden by any stored snapshot from the same day — the
    snapshot reflects the portfolio as it actually stood, the reconstruction
    only covers the period before snapshots existed.

    :param holdings: Rows from :func:`aggregate_holdings`.
    :param range_key: Key from ``price_history_service.RANGE_PRESETS``.
    :param snapshots: Stored snapshots overlapping the range.
    :param live_totals: Current totals, appended as the final point.
    :return: Series payload with points and start/end change metrics.
    """
    range_key = normalize_range(range_key)
    cost_basis = sum(h["cost_basis"] for h in holdings)

    empty = {
        "range": range_key,
        "points": [],
        "cost_basis": cost_basis,
        "start_value": None,
        "end_value": None,
        "change": None,
        "change_percent": None,
        "missing_symbols": [],
    }

    if not holdings:
        return empty

    series_list = await asyncio.gather(
        *(get_price_series(h["symbol"], range_key) for h in holdings),
        return_exceptions=True,
    )

    priced: list[tuple[dict, list[dict]]] = []
    missing: list[str] = []
    stamps: set[str] = set()

    for holding, series in zip(holdings, series_list):
        if isinstance(series, Exception) or not series:
            missing.append(holding["symbol"])
            continue
        priced.append((holding, series))
        stamps.update(point["t"] for point in series)

    if not priced:
        return {**empty, "missing_symbols": missing}

    timeline = sorted(stamps)
    filled = [
        (holding, _forward_filled(series, timeline)) for holding, series in priced
    ]

    # Snapshots are indexed by day, so they can only stand in for daily bars.
    # On an intraday timeline every bar of a day would collapse onto the same
    # snapshot value and flatten the curve, so the reconstruction is kept.
    is_daily = len(timeline[0]) == 10
    overrides = _snapshot_overrides(snapshots or []) if is_daily else {}
    points: list[dict] = []

    for stamp in timeline:
        value = sum(holding["quantity"] * closes[stamp] for holding, closes in filled)
        snapshot = overrides.get(stamp[:10])
        if snapshot is not None:
            value = snapshot["market_value"]
            point_cost = snapshot["cost_basis"]
            origin = "snapshot"
        else:
            point_cost = cost_basis
            origin = "reconstructed"

        points.append(
            {
                "t": stamp,
                "value": value,
                "cost_basis": point_cost,
                "pnl": value - point_cost,
                "pnl_percent": (
                    (value - point_cost) / point_cost * 100 if point_cost else 0.0
                ),
                "source": origin,
            }
        )

    if live_totals and points:
        now = datetime.now(timezone.utc)
        live_point = {
            "t": now.date().isoformat()
            if len(points[-1]["t"]) == 10
            else now.isoformat(),
            "value": live_totals["market_value"],
            "cost_basis": live_totals["cost_basis"],
            "pnl": live_totals["unrealized_pnl"],
            "pnl_percent": live_totals["unrealized_pnl_percent"],
            "source": "live",
        }
        if points[-1]["t"][:10] == live_point["t"][:10]:
            points[-1] = live_point
        else:
            points.append(live_point)

    start_value = points[0]["value"]
    end_value = points[-1]["value"]
    change = end_value - start_value

    return {
        "range": range_key,
        "points": points,
        "cost_basis": cost_basis,
        "start_value": start_value,
        "end_value": end_value,
        "change": change,
        "change_percent": (change / start_value * 100 if start_value else 0.0),
        "missing_symbols": missing,
    }


async def build_asset_insights(valued_positions: list[dict]) -> list[dict]:
    """Attach ATH/ATL and 52-week context to each valued position.

    :param valued_positions: Positions from :func:`value_holdings`.
    :return: Positions enriched with a ``stats`` block (``None`` when history
        could not be fetched), sorted by market value.
    """
    if not valued_positions:
        return []

    stats_list = await asyncio.gather(
        *(
            get_symbol_stats(position["symbol"], position.get("market_price"))
            for position in valued_positions
        ),
        return_exceptions=True,
    )

    enriched: list[dict] = []
    for position, stats in zip(valued_positions, stats_list):
        if isinstance(stats, Exception):
            logger.debug(
                "[portfolio] stats failed for %s: %r", position["symbol"], stats
            )
            stats = None
        enriched.append({**position, "stats": stats})

    enriched.sort(key=lambda p: p.get("market_value") or 0.0, reverse=True)
    return enriched
