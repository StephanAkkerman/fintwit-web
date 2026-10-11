"""Background worker that grades Claude's market-check calls at each horizon.

Same shape as ``trader_evaluator``: find calls whose horizon has passed,
re-price them through ``AssetEnricher.classify`` (the pricing used when the
call was logged) and store the result.
"""

import asyncio
import logging
from datetime import datetime, timezone

from ..infra.repos import AdvisorRepo
from ..services.advisor import GRADED_ACTIONS, HORIZONS, grade, price_from_assets
from .enricher import AssetEnricher

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 3600
_MIN_BACKOFF = 30
_MAX_BACKOFF = 900


async def evaluate_due_advisor_calls(repo: AdvisorRepo, enricher: AssetEnricher) -> int:
    """Grade every call that is due at a horizon. Returns results written."""
    written = 0
    for horizon in HORIZONS:
        due = await repo.due_calls(horizon, GRADED_ACTIONS)
        if not due:
            continue
        try:
            assets = await enricher.classify(sorted({c["symbol"] for c in due}))
        except Exception:
            logger.warning(
                "[advisor-eval] price lookup failed for horizon=%dd",
                horizon,
                exc_info=True,
            )
            continue

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        results = []
        for call in due:
            price_now, kind_now = price_from_assets(assets, call["symbol"])
            if price_now is None:
                continue
            graded = grade(call["action"], call["price_at_call"], price_now)
            kind_then = call.get("asset_kind")
            if kind_now and kind_then and kind_now != kind_then:
                graded["excluded"] = True
            results.append(
                {
                    "call_id": call["id"],
                    "horizon_days": horizon,
                    "price_at_horizon": price_now,
                    "evaluated_at": now,
                    **graded,
                }
            )
        written += await repo.insert_results(results)
    return written


async def run_advisor_evaluation(
    repo: AdvisorRepo, interval: int = DEFAULT_INTERVAL
) -> None:
    """Grade due calls every ``interval`` seconds, forever."""
    enricher = AssetEnricher()
    backoff = _MIN_BACKOFF
    while True:
        try:
            graded = await evaluate_due_advisor_calls(repo, enricher)
            if graded:
                logger.info("[advisor-eval] graded %d call-horizon result(s)", graded)
            backoff = _MIN_BACKOFF
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[advisor-eval] error: %r — retrying in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
