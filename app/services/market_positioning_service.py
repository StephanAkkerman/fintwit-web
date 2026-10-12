"""Market "plumbing": who is positioned where, and what forces them to trade (issue #82).

The issue's video argues that positioning and rules-based flows move the index
more than headlines do, and names four things to watch. Gamma regimes already
have their own widget (issue #85, `gamma_exposure_service.py`); this module
covers the other three with free, no-key data:

* **Hedge fund short exposure** -- prime-brokerage books are private, but the
  CFTC's weekly *Traders in Financial Futures* report breaks E-mini S&P 500 and
  Nasdaq-100 open interest down by trader type. "Leveraged funds" is the hedge
  fund / CTA bucket, so its net position as a share of open interest, ranked
  against the last three years, shows when the street is crowded short (the
  squeeze setup the video describes).
* **CTA trigger levels** -- real CTA models are proprietary, but most are
  time-series momentum: long when price is above where it was N days ago.
  Each lookback's trigger is therefore just that reference close, and the
  share of lookbacks that are long is a rough proxy for CTA exposure.
* **Passive flows / concentration** -- fund-flow data is paid, but the effect
  the video describes (cap-weighted money piling into the largest names)
  shows up as the equal-weight S&P 500 (RSP) lagging the cap-weighted one
  (SPY). The RSP/SPY spread is the standard free proxy for that.

Every figure here is an estimate from public data, not anyone's actual book.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiohttp

from .price_history_service import get_price_series

logger = logging.getLogger(__name__)

_CFTC_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
_TIMEOUT_SECONDS = 15
_CACHE_TTL_SECONDS = 3600  # COT is weekly; the daily price inputs barely move intraday

#: CFTC contract market codes for the index futures the TFF report covers.
FUTURES_CONTRACTS: dict[str, str] = {
    "13874A": "E-mini S&P 500",
    "209742": "E-mini Nasdaq-100",
}
#: Weeks of COT history the percentile ranks against (~3 years).
_HISTORY_WEEKS = 156
#: Weeks of history returned for the sparkline.
_SPARKLINE_WEEKS = 52
#: Leveraged-fund net % of OI at or below this percentile is "crowded short".
CROWDED_SHORT_PERCENTILE = 20.0
CROWDED_LONG_PERCENTILE = 80.0

CTA_SYMBOL = "SPY"
#: Momentum lookbacks in trading days, labelled the way CTA desks quote them.
CTA_LOOKBACKS: list[tuple[str, int]] = [
    ("1M", 21),
    ("3M", 63),
    ("6M", 126),
    ("12M", 250),
]

CAP_WEIGHTED = "SPY"
EQUAL_WEIGHTED = "RSP"
#: Equal-weight minus cap-weighted return (percentage points) beyond which
#: breadth is called narrowing/broadening rather than stable.
CONCENTRATION_THRESHOLD_PP = 2.0
_CONCENTRATION_WINDOWS: list[tuple[str, int]] = [("1M", 21), ("3M", 63), ("1Y", 250)]

_cache: tuple[float, dict] | None = None
_cache_lock = asyncio.Lock()


def _reset_cache_for_tests() -> None:
    global _cache
    _cache = None


def _to_int(value: object) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _percentile_rank(values: list[float], value: float) -> float:
    """Share of ``values`` at or below ``value``, on a 0-100 scale."""
    if not values:
        return 50.0
    return round(100.0 * sum(1 for v in values if v <= value) / len(values), 1)


def _crowding(percentile: float) -> str:
    if percentile <= CROWDED_SHORT_PERCENTILE:
        return "crowded_short"
    if percentile >= CROWDED_LONG_PERCENTILE:
        return "crowded_long"
    return "neutral"


async def _fetch_cot_rows() -> Optional[list[dict]]:
    since = (datetime.now(timezone.utc) - timedelta(weeks=_HISTORY_WEEKS + 2)).date()
    codes = ",".join(f"'{code}'" for code in FUTURES_CONTRACTS)
    params = {
        "$select": (
            "report_date_as_yyyy_mm_dd,cftc_contract_market_code,open_interest_all,"
            "lev_money_positions_long,lev_money_positions_short,"
            "asset_mgr_positions_long,asset_mgr_positions_short"
        ),
        "$where": (
            f"cftc_contract_market_code in({codes}) "
            f"AND report_date_as_yyyy_mm_dd >= '{since.isoformat()}T00:00:00.000'"
        ),
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": "2000",
    }
    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_CFTC_URL, params=params) as resp:
                if resp.status != 200:
                    logger.info("[positioning] CFTC returned HTTP %s", resp.status)
                    return None
                payload = await resp.json(content_type=None)
    except Exception as exc:
        logger.debug("[positioning] CFTC fetch failed: %r", exc)
        return None
    return payload if isinstance(payload, list) else None


def summarize_futures_positioning(rows: list[dict]) -> list[dict]:
    """Per-contract leveraged-fund and asset-manager positioning from COT rows.

    :param rows: Raw TFF rows (any order, any of :data:`FUTURES_CONTRACTS`).
    :return: One entry per contract that has data, with a chronological
        ``history`` of the last year's leveraged-fund net % of open interest.
    """
    by_code: dict[str, list[dict]] = {}
    for row in rows:
        code = str(row.get("cftc_contract_market_code") or "").strip()
        if code not in FUTURES_CONTRACTS:
            continue
        oi = _to_int(row.get("open_interest_all"))
        lev_long = _to_int(row.get("lev_money_positions_long"))
        lev_short = _to_int(row.get("lev_money_positions_short"))
        am_long = _to_int(row.get("asset_mgr_positions_long"))
        am_short = _to_int(row.get("asset_mgr_positions_short"))
        report_date = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
        if (
            not oi
            or None in (lev_long, lev_short, am_long, am_short)
            or not report_date
        ):
            continue
        by_code.setdefault(code, []).append(
            {
                "date": report_date,
                "open_interest": oi,
                "lev_net": lev_long - lev_short,
                "lev_net_pct_oi": round(100.0 * (lev_long - lev_short) / oi, 2),
                "asset_mgr_net": am_long - am_short,
                "asset_mgr_net_pct_oi": round(100.0 * (am_long - am_short) / oi, 2),
            }
        )

    contracts: list[dict] = []
    for code, name in FUTURES_CONTRACTS.items():
        weeks = sorted(by_code.get(code, []), key=lambda w: w["date"])
        if not weeks:
            continue
        latest = weeks[-1]
        previous = weeks[-2] if len(weeks) > 1 else None
        percentile = _percentile_rank(
            [w["lev_net_pct_oi"] for w in weeks], latest["lev_net_pct_oi"]
        )
        contracts.append(
            {
                "code": code,
                "name": name,
                "report_date": latest["date"],
                "open_interest": latest["open_interest"],
                "lev_net": latest["lev_net"],
                "lev_net_pct_oi": latest["lev_net_pct_oi"],
                "lev_net_change": (
                    latest["lev_net"] - previous["lev_net"] if previous else None
                ),
                "lev_percentile": percentile,
                "asset_mgr_net": latest["asset_mgr_net"],
                "asset_mgr_net_pct_oi": latest["asset_mgr_net_pct_oi"],
                "crowding": _crowding(percentile),
                "weeks_ranked": len(weeks),
                "history": [
                    {"date": w["date"], "lev_net_pct_oi": w["lev_net_pct_oi"]}
                    for w in weeks[-_SPARKLINE_WEEKS:]
                ],
            }
        )
    return contracts


def compute_cta_triggers(symbol: str, closes: list[float]) -> Optional[dict]:
    """Time-series-momentum signals and trigger levels from daily closes.

    A lookback is long when the latest close is above the close ``N`` trading
    days earlier; that earlier close is the trigger the price has to cross to
    flip it. Lookbacks longer than the available history are left out.
    """
    if len(closes) < 2:
        return None

    spot = closes[-1]
    signals: list[dict] = []
    for label, days in CTA_LOOKBACKS:
        if len(closes) <= days:
            continue
        trigger = closes[-1 - days]
        if trigger <= 0:
            continue
        signals.append(
            {
                "lookback": label,
                "days": days,
                "trigger": round(trigger, 2),
                "distance_pct": round(100.0 * (spot - trigger) / trigger, 2),
                "signal": "long" if spot > trigger else "short",
            }
        )
    if not signals:
        return None

    score = sum(1 if s["signal"] == "long" else -1 for s in signals) / len(signals)
    nearest = min(signals, key=lambda s: abs(s["distance_pct"]))
    return {
        "symbol": symbol,
        "spot": round(spot, 2),
        "score": round(score, 2),
        "exposure": _cta_exposure(score),
        "signals": signals,
        "nearest_trigger": nearest["lookback"],
    }


def _cta_exposure(score: float) -> str:
    if score >= 1:
        return "max_long"
    if score > 0:
        return "long"
    if score <= -1:
        return "max_short"
    if score < 0:
        return "short"
    return "flat"


def _return_pct(closes: list[float], days: int) -> Optional[float]:
    if len(closes) <= days or closes[-1 - days] <= 0:
        return None
    return 100.0 * (closes[-1] / closes[-1 - days] - 1.0)


def compute_concentration(
    cap_points: list[dict], equal_points: list[dict]
) -> Optional[dict]:
    """Equal-weight vs cap-weighted S&P 500 relative performance.

    :param cap_points: Daily ``{t, close}`` points for :data:`CAP_WEIGHTED`.
    :param equal_points: Same for :data:`EQUAL_WEIGHTED`.
    """
    cap = {p["t"]: p["close"] for p in cap_points if p.get("close")}
    equal = {p["t"]: p["close"] for p in equal_points if p.get("close")}
    dates = sorted(d for d in cap if d in equal)
    if len(dates) < 2:
        return None

    cap_closes = [cap[d] for d in dates]
    equal_closes = [equal[d] for d in dates]

    windows: list[dict] = []
    for label, days in _CONCENTRATION_WINDOWS:
        cap_ret = _return_pct(cap_closes, days)
        equal_ret = _return_pct(equal_closes, days)
        if cap_ret is None or equal_ret is None:
            continue
        windows.append(
            {
                "window": label,
                "cap_weighted_pct": round(cap_ret, 2),
                "equal_weighted_pct": round(equal_ret, 2),
                "spread_pp": round(equal_ret - cap_ret, 2),
            }
        )
    if not windows:
        return None

    # The 3M window is the headline; fall back to the longest one available.
    headline = next((w for w in windows if w["window"] == "3M"), windows[-1])
    if headline["spread_pp"] <= -CONCENTRATION_THRESHOLD_PP:
        trend = "narrowing"
    elif headline["spread_pp"] >= CONCENTRATION_THRESHOLD_PP:
        trend = "broadening"
    else:
        trend = "stable"

    base = equal_closes[0] / cap_closes[0]
    step = max(1, len(dates) // 60)
    ratio_history = [
        {"date": d, "ratio": round(100.0 * (equal[d] / cap[d]) / base, 2)}
        for d in dates[::step]
    ]
    if ratio_history[-1]["date"] != dates[-1]:
        ratio_history.append(
            {
                "date": dates[-1],
                "ratio": round(100.0 * (equal_closes[-1] / cap_closes[-1]) / base, 2),
            }
        )

    return {
        "cap_weighted": CAP_WEIGHTED,
        "equal_weighted": EQUAL_WEIGHTED,
        "trend": trend,
        "headline_window": headline["window"],
        "windows": windows,
        "ratio_history": ratio_history,
    }


async def get_market_positioning() -> Optional[dict]:
    """Futures positioning, CTA triggers and breadth concentration in one payload.

    Each section is ``None`` when its upstream failed, so one dead source does
    not blank the others.

    :return: ``{futures, cta, concentration, as_of}``, or ``None`` when every
        section failed.
    """
    global _cache
    async with _cache_lock:
        if _cache and time.time() - _cache[0] <= _CACHE_TTL_SECONDS:
            return _cache[1]

    cot_rows, cap_points, equal_points = await asyncio.gather(
        _fetch_cot_rows(),
        get_price_series(CAP_WEIGHTED, "1Y"),
        get_price_series(EQUAL_WEIGHTED, "1Y"),
        return_exceptions=True,
    )
    if isinstance(cot_rows, BaseException):
        logger.debug("[positioning] COT failed: %r", cot_rows)
        cot_rows = None
    if isinstance(cap_points, BaseException):
        cap_points = []
    if isinstance(equal_points, BaseException):
        equal_points = []

    futures = summarize_futures_positioning(cot_rows) if cot_rows else []
    cta = compute_cta_triggers(
        CTA_SYMBOL, [p["close"] for p in cap_points if p.get("close")]
    )
    concentration = compute_concentration(cap_points, equal_points)

    if not futures and cta is None and concentration is None:
        return None

    payload = {
        "futures": futures or None,
        "cta": cta,
        "concentration": concentration,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    async with _cache_lock:
        _cache = (time.time(), payload)
    return payload
