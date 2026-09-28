"""Background worker that grades trader calls once their horizon has passed.

Grading reuses ``AssetEnricher.classify`` — the same price-routing (crypto ->
CoinGecko, else -> Yahoo/TradingView) already used to price tweets live — so
a call's "price now" is fetched the same way its "price at call" was.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import async_sessionmaker

from ..infra.repos import TraderCallRepo
from ..services.trader_scoring import HORIZONS, find_due_calls, grade_call
from .enricher import AssetEnricher

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1800  # 30 minutes
_MIN_BACKOFF = 30
_MAX_BACKOFF = 900
_LIMIT_PER_HORIZON = 200


async def evaluate_due_calls(
    Session: async_sessionmaker,
    repo: TraderCallRepo,
    enricher: AssetEnricher,
) -> int:
    """Grade every call whose horizon is due at at least one horizon.

    :return: Number of (call, horizon) results written.
    """
    total_graded = 0

    for horizon in HORIZONS:
        due = await find_due_calls(Session, horizon, limit=_LIMIT_PER_HORIZON)
        if not due:
            continue

        tickers = sorted({call["ticker"] for call in due})
        try:
            assets = await enricher.classify(tickers)
        except Exception:
            logger.warning(
                "[trader-eval] price lookup failed for horizon=%dd",
                horizon,
                exc_info=True,
            )
            continue

        price_by_symbol: dict[str, float] = {}
        kind_by_symbol: dict[str, str] = {}
        for asset in assets:
            symbol = str(asset.get("symbol") or "").upper()
            price = (asset.get("financials") or {}).get("price")
            if symbol and isinstance(price, (int, float)):
                price_by_symbol[symbol] = float(price)
                if asset.get("kind"):
                    kind_by_symbol[symbol] = str(asset["kind"]).upper()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results = []
        for call in due:
            price_now = price_by_symbol.get(call["ticker"])
            if price_now is None:
                continue
            graded = grade_call(call["direction"], call["price_at_call"], price_now)
            # The ticker now classifies as a different kind of asset than it
            # did at call time (e.g. a stock symbol now resolving to a coin),
            # so the two prices aren't comparable.
            kind_now = kind_by_symbol.get(call["ticker"])
            kind_then = str(call.get("asset_kind") or "").upper()
            if kind_now and kind_then and kind_now != kind_then:
                graded["excluded"] = True
            results.append(
                {
                    "call_id": call["id"],
                    "horizon_days": horizon,
                    "price_at_horizon": price_now,
                    "return_pct": graded["return_pct"],
                    "correct": graded["correct"],
                    "excluded": graded["excluded"],
                    "evaluated_at": now,
                }
            )

        if results:
            await repo.insert_results(results)
            total_graded += len(results)

    return total_graded


async def run_trader_call_evaluation(
    Session: async_sessionmaker,
    repo: TraderCallRepo,
    interval: int = DEFAULT_INTERVAL,
) -> None:
    """Grade due calls every ``interval`` seconds, forever."""
    enricher = AssetEnricher()
    backoff = _MIN_BACKOFF

    while True:
        try:
            graded = await evaluate_due_calls(Session, repo, enricher)
            if graded:
                logger.info("[trader-eval] graded %d call-horizon result(s)", graded)

            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error("[trader-eval] error: %r — retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
