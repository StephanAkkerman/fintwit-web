"""SPY dealer gamma exposure (GEX) estimate and gamma-regime detection (issue #85).

No free, no-key API publishes dealer gamma exposure directly — providers like
Unusual Whales and SpotGamma sell that data as a finished product. What *is*
free is the raw options chain (open interest, implied volatility, strike) via
`yfinance`, the same source `options_chain_service.py` already uses. That is
enough to estimate GEX ourselves: Black-Scholes gamma per contract, scaled by
open interest and dollarized against spot, using the standard dealer-
positioning convention (dealers assumed net long calls / net short puts) — see
https://perfiliev.co.uk/market-commentary/how-to-calculate-gamma-exposure-and-zero-gamma-level/
for the reference formula this follows.

This is an estimate, not the real dealer book (no free source publishes
actual market-maker positioning), but the sign of net GEX and the zero-gamma
"flip point" it produces track the same regime shifts paid GEX trackers plot.
Positive GEX means dealers hedge by trading against the market (dampening
moves); negative GEX means they hedge with the market (amplifying moves) —
that's the "negative gamma regime" the issue asks to surface.
"""

import asyncio
import logging
import math
import time
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

CONTRACT_MULTIPLIER = 100
DEFAULT_SYMBOL = "SPY"
#: SPY has expirations most weekdays; gamma from far-dated contracts barely
#: moves the near-term dealer book, so capping here keeps the yfinance calls
#: (one per expiration) bounded.
MAX_EXPIRATIONS = 8
#: Floors days-to-expiry so a same-day (0DTE) expiration doesn't blow up
#: Black-Scholes gamma's 1/sqrt(T) term.
_MIN_YEARS_TO_EXPIRY = 1.0 / (365.0 * 4)
_RISK_FREE_RATE = 0.0

_CACHE_TTL_SECONDS = 300
_CACHE: dict[str, tuple[float, dict]] = {}


def _get_cached(symbol: str) -> dict | None:
    cached = _CACHE.get(symbol)
    if cached is None:
        return None

    ts, data = cached
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(symbol, None)
        return None

    return data


def _set_cached(symbol: str, payload: dict) -> None:
    _CACHE[symbol] = (time.time(), payload)


def _reset_cache_for_tests() -> None:
    _CACHE.clear()


def _to_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes_gamma(
    spot: float,
    strike: float,
    years_to_expiry: float,
    iv: float,
    risk_free_rate: float = _RISK_FREE_RATE,
) -> float | None:
    """Black-Scholes gamma (identical formula for calls and puts).

    :return: ``None`` for inputs that leave gamma undefined (non-positive
        spot/strike/vol/time).
    """
    if spot <= 0 or strike <= 0 or years_to_expiry <= 0 or iv <= 0:
        return None

    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * iv * iv) * years_to_expiry
    ) / (iv * sqrt_t)
    return _norm_pdf(d1) / (spot * iv * sqrt_t)


def _years_to_expiry(expiration: str, today: date) -> float:
    expiry_date = datetime.strptime(expiration, "%Y-%m-%d").date()
    days = (expiry_date - today).days
    return max(days, 0) / 365.0


def _zero_gamma_level(strike_totals: dict[float, float]) -> float | None:
    """Linearly interpolate the strike where cumulative net gamma crosses zero.

    Scanning strikes low-to-high and accumulating dollar gamma reproduces the
    dealer's aggregate gamma position at each spot level; the crossing is
    where dealers flip from net short to net long gamma (or vice versa).
    Returns ``None`` when every strike sits on the same side of zero.
    """
    if not strike_totals:
        return None

    strikes = sorted(strike_totals)
    cumulative = 0.0
    prev_strike: float | None = None
    prev_cumulative: float | None = None

    for strike in strikes:
        cumulative += strike_totals[strike]
        if (
            prev_cumulative is not None
            and prev_strike is not None
            and cumulative != prev_cumulative
            and (
                prev_cumulative <= 0 <= cumulative or prev_cumulative >= 0 >= cumulative
            )
        ):
            fraction = -prev_cumulative / (cumulative - prev_cumulative)
            return prev_strike + fraction * (strike - prev_strike)
        prev_strike, prev_cumulative = strike, cumulative

    return None


def _fetch_chains_sync(symbol: str, max_expirations: int) -> dict | None:
    """Blocking yfinance calls — always run this via asyncio.to_thread.

    Fetches the nearest ``max_expirations`` expirations' full chains, one
    `option_chain()` call each (yfinance has no bulk endpoint for this).
    """
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    expirations = list(ticker.options)[:max_expirations]
    if not expirations:
        return None

    spot: float | None = None
    chains: list[tuple[str, object, object]] = []

    for expiration in expirations:
        try:
            calls, puts, underlying = ticker.option_chain(expiration)
        except Exception as exc:
            logger.debug(
                "[gamma-exposure] %s chain fetch failed for %s: %r",
                symbol,
                expiration,
                exc,
            )
            continue

        if spot is None and underlying:
            spot = _to_float(
                underlying.get("postMarketPrice")
                or underlying.get("regularMarketPrice")
            )

        chains.append((expiration, calls, puts))

    if spot is None or not chains:
        return None

    return {"spot": spot, "chains": chains}


async def get_gamma_exposure(
    symbol: str = DEFAULT_SYMBOL, max_expirations: int = MAX_EXPIRATIONS
) -> dict | None:
    """Estimate net dealer gamma exposure and the current regime for ``symbol``.

    Blocking yfinance calls run in a worker thread (``asyncio.to_thread``);
    results are cached per symbol for a short TTL to absorb repeated polling.

    :return: ``{symbol, spot_price, net_gex, call_gex, put_gex, flip_point,
        regime, expirations_used, by_strike, as_of, source}``, or ``None``
        when the chain couldn't be fetched. ``regime`` is ``"positive"`` or
        ``"negative"``, decided by spot vs. ``flip_point`` when a flip point
        exists in the observed strike range, else by the sign of ``net_gex``.
    """
    normalized_symbol = (symbol or DEFAULT_SYMBOL).strip().upper()
    if not normalized_symbol:
        return None

    cached = _get_cached(normalized_symbol)
    if cached is not None:
        return cached

    try:
        raw = await asyncio.to_thread(
            _fetch_chains_sync, normalized_symbol, max_expirations
        )
    except Exception as exc:
        logger.warning(
            "[gamma-exposure] fetch failed for %s: %r", normalized_symbol, exc
        )
        return None

    if raw is None:
        return None

    spot = raw["spot"]
    today = datetime.now(timezone.utc).date()

    strike_totals: dict[float, float] = {}
    total_call_gamma = 0.0
    total_put_gamma = 0.0
    expirations_used: list[str] = []

    for expiration, calls, puts in raw["chains"]:
        try:
            years = max(_years_to_expiry(expiration, today), _MIN_YEARS_TO_EXPIRY)
        except ValueError:
            continue
        expirations_used.append(expiration)

        for df, sign in ((calls, 1.0), (puts, -1.0)):
            if df is None:
                continue
            for _, row in df.iterrows():
                strike = _to_float(row.get("strike"))
                oi = _to_float(row.get("openInterest")) or 0.0
                iv = _to_float(row.get("impliedVolatility"))
                if strike is None or iv is None or oi <= 0:
                    continue

                gamma = black_scholes_gamma(spot, strike, years, iv)
                if gamma is None:
                    continue

                dollars = gamma * oi * CONTRACT_MULTIPLIER * spot * spot * 0.01
                strike_totals[strike] = strike_totals.get(strike, 0.0) + sign * dollars
                if sign > 0:
                    total_call_gamma += dollars
                else:
                    total_put_gamma += dollars

    if not expirations_used:
        return None

    net_gex = total_call_gamma - total_put_gamma
    flip_point = _zero_gamma_level(strike_totals)
    if flip_point is not None:
        regime = "positive" if spot >= flip_point else "negative"
    else:
        regime = "positive" if net_gex >= 0 else "negative"

    payload = {
        "symbol": normalized_symbol,
        "spot_price": spot,
        "net_gex": net_gex,
        "call_gex": total_call_gamma,
        "put_gex": -total_put_gamma,
        "flip_point": flip_point,
        "regime": regime,
        "expirations_used": expirations_used,
        "by_strike": [
            {"strike": strike, "net_gamma": strike_totals[strike]}
            for strike in sorted(strike_totals)
        ],
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "yfinance-bs-estimate",
    }
    _set_cached(normalized_symbol, payload)
    return payload
