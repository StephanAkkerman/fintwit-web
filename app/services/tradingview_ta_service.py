import asyncio
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from tradingview_ta import Interval, TA_Handler
except Exception as exc:  # pragma: no cover - optional dependency safety net
    Interval = None
    TA_Handler = None
    logger.warning("[tradingview-ta] package import failed: %r", exc)

try:
    from tradingview_scraper.symbols.symbol_markets import SymbolMarkets
except Exception as exc:  # pragma: no cover - optional dependency safety net
    SymbolMarkets = None
    logger.warning("[tradingview-ta] symbol_markets import failed: %r", exc)

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 900
_REQUEST_SEMAPHORE = asyncio.Semaphore(4)
_cache: dict[tuple[str, str], tuple[float, Optional[dict[str, Any]]]] = {}
_cache_lock = asyncio.Lock()

# TradingView's scanner API throttles aggressively (HTTP 429). Retry a few
# times with exponential backoff before giving up on a symbol.
_RATE_LIMIT_MAX_ATTEMPTS = 3
_RATE_LIMIT_BASE_DELAY_SECONDS = 2.0


class _RateLimitedError(Exception):
    """Raised when TradingView keeps returning 429 after exhausting retries."""


def _is_rate_limited(exc: Exception) -> bool:
    return "429" in str(exc)


def _get_analysis_with_backoff(
    handler: Any,
    ticker: str,
    *,
    sleep=time.sleep,
) -> Any:
    """Call ``handler.get_analysis()``, retrying on HTTP 429 with backoff.

    Non-rate-limit errors propagate immediately. If the rate limit persists
    past ``_RATE_LIMIT_MAX_ATTEMPTS``, raises :class:`_RateLimitedError`.
    """
    delay = _RATE_LIMIT_BASE_DELAY_SECONDS
    for attempt in range(1, _RATE_LIMIT_MAX_ATTEMPTS + 1):
        try:
            return handler.get_analysis()
        except Exception as exc:
            if not _is_rate_limited(exc):
                raise
            if attempt >= _RATE_LIMIT_MAX_ATTEMPTS:
                logger.warning(
                    "[tradingview-ta] rate limit hit on %s — giving up after %d attempts",
                    ticker,
                    attempt,
                )
                raise _RateLimitedError(str(exc)) from exc
            logger.warning(
                "[tradingview-ta] rate limit hit on %s — backing off for %.1fs "
                "(attempt %d/%d)",
                ticker,
                delay,
                attempt,
                _RATE_LIMIT_MAX_ATTEMPTS,
            )
            sleep(delay)
            delay *= 2


def _normalize_symbol(symbol: str) -> str:
    value = (symbol or "").strip().upper()
    if not value:
        return ""

    if ":" in value:
        _, _, value = value.partition(":")

    if value.endswith("=X"):
        value = value[:-2]

    if value.startswith("^"):
        value = value[1:]

    if value.endswith("-USD"):
        value = value.replace("-", "")

    return value


def _scanner_priority(asset_hint: str | None) -> list[str]:
    hint = str(asset_hint or "").strip().lower()
    if hint == "crypto":
        return ["crypto", "global"]
    if hint == "forex":
        return ["forex", "global"]
    if hint in {"index", "future"}:
        return ["global"]
    return ["america", "global"]


def _pick_best_row(rows: list[dict], asset_hint: str | None) -> Optional[dict]:
    hint = str(asset_hint or "").strip().lower()
    best: tuple[float, dict] | None = None

    for row in rows:
        score = 0.0
        row_type = str(row.get("type") or "").lower()
        row_symbol = str(row.get("symbol") or "").upper()
        volume = row.get("volume")

        try:
            if volume is not None and float(volume) > 0:
                score += 1.0
        except (TypeError, ValueError):
            pass

        if hint == "crypto" and "crypto" in row_type:
            score += 5.0
            if row_symbol.endswith("USD") or row_symbol.endswith("USDT"):
                score += 1.0
        elif hint == "forex" and "forex" in row_type:
            score += 5.0
        elif hint in {"stock", "equity", "index", "future", ""}:
            if "stock" in row_type:
                score += 4.0
            elif "index" in row_type:
                score += 3.0

        if best is None or score > best[0]:
            best = (score, row)

    return best[1] if best else None


def _normalize_ta_screener(
    scanner: str | None, row_type: str | None, asset_hint: str | None
) -> str:
    candidate = str(scanner or "").strip().lower()
    if candidate in {"america", "crypto", "forex", "cfd"}:
        return candidate

    row_kind = str(row_type or "").strip().lower()
    if row_kind == "crypto":
        return "crypto"
    if row_kind == "forex":
        return "forex"
    if row_kind in {"stock", "index", "fund", "dr", "etf", "future"}:
        return "america"

    hint = str(asset_hint or "").strip().lower()
    if hint == "crypto":
        return "crypto"
    if hint == "forex":
        return "forex"

    return "america"


def _build_symbol_context(
    row: dict, scanner: str, fallback_symbol: str, asset_hint: str | None
) -> dict:
    raw_symbol = str(row.get("symbol") or fallback_symbol).upper()
    exchange = str(row.get("exchange") or "").upper()
    if not exchange and ":" in raw_symbol:
        exchange = raw_symbol.split(":", 1)[0]

    screener = _normalize_ta_screener(scanner, row.get("type"), asset_hint)
    symbol = raw_symbol.split(":", 1)[-1]

    return {
        "symbol": symbol,
        "exchange": exchange,
        "screener": screener,
        "website": f"https://www.tradingview.com/symbols/{raw_symbol.replace(':', '-')}/",
    }


def _resolve_symbol_context(symbol: str, asset_hint: str | None) -> Optional[dict]:
    normalized = _normalize_symbol(symbol)
    if not normalized or SymbolMarkets is None:
        return None

    try:
        markets = SymbolMarkets()
    except Exception as exc:
        logger.debug("[tradingview-ta] symbol_markets init failed: %r", exc)
        return None

    rows: list[dict] = []
    for scanner in _scanner_priority(asset_hint):
        try:
            result = markets.scrape(symbol=normalized, scanner=scanner, limit=25)
        except TypeError:
            result = markets.scrape(symbol=normalized, limit=25)
        except Exception as exc:
            logger.debug(
                "[tradingview-ta] symbol_markets scrape failed for %s/%s: %r",
                normalized,
                scanner,
                exc,
            )
            continue

        data = result.get("data") if isinstance(result, dict) else result
        if isinstance(data, list):
            rows.extend([row for row in data if isinstance(row, dict)])

        best = _pick_best_row(rows, asset_hint)
        if best is not None:
            return _build_symbol_context(best, scanner, normalized, asset_hint)

    best = _pick_best_row(rows, asset_hint)
    if best is not None:
        return _build_symbol_context(
            best, _scanner_priority(asset_hint)[0], normalized, asset_hint
        )

    return {
        "symbol": normalized,
        "exchange": "",
        "screener": _scanner_priority(asset_hint)[0],
        "website": f"https://www.tradingview.com/symbols/{normalized}/",
    }


def _format_summary(summary: dict[str, Any], interval: str) -> dict[str, Any]:
    recommendation = str(summary.get("RECOMMENDATION") or "NEUTRAL").strip()
    formatted_recommendation = recommendation.replace("_", " ").title() or "Neutral"

    def _coerce_count(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    buy = _coerce_count(summary.get("BUY"))
    neutral = _coerce_count(summary.get("NEUTRAL"))
    sell = _coerce_count(summary.get("SELL"))

    return {
        "interval": interval,
        "recommendation": formatted_recommendation,
        "buy": buy,
        "neutral": neutral,
        "sell": sell,
        "summary": f"{formatted_recommendation}\n{buy}\U0001f4c8 {neutral}\u231b\ufe0f {sell}\U0001f4c9",
    }


def _fetch_analysis_sync(
    symbol: str, asset_hint: str | None
) -> Optional[dict[str, Any]]:
    if TA_Handler is None or Interval is None:
        logger.warning(
            "[tradingview-ta] TA_Handler or Interval not available, cannot fetch analysis for %s",
            symbol,
        )
        return None

    context = _resolve_symbol_context(symbol, asset_hint)
    if context is None:
        return None

    interval_map = {
        "four_h": Interval.INTERVAL_4_HOURS,
        "one_d": Interval.INTERVAL_1_DAY,
    }
    analyses: dict[str, Any] = {}

    for key, interval in interval_map.items():
        try:
            handler = TA_Handler(
                symbol=context["symbol"],
                screener=context["screener"],
                exchange=context["exchange"],
                interval=interval,
                timeout=5,
            )
            analysis = _get_analysis_with_backoff(handler, context["symbol"])
            if analysis and getattr(analysis, "summary", None):
                analyses[key] = _format_summary(analysis.summary, key)
        except _RateLimitedError:
            # Still throttled after retries — don't hammer the remaining
            # intervals for this symbol; return whatever we already have.
            break
        except Exception as exc:
            logger.debug(
                "[tradingview-ta] analysis failed for %s/%s: %r",
                context["symbol"],
                key,
                exc,
            )

    if not analyses:
        return None

    return {
        "source": "tradingview_ta",
        "website": context["website"],
        "symbol": context["symbol"],
        "exchange": context["exchange"],
        "screener": context["screener"],
        **analyses,
    }


async def _get_cached(
    cache_key: tuple[str, str],
) -> tuple[bool, Optional[dict[str, Any]]]:
    async with _cache_lock:
        item = _cache.get(cache_key)
        if item is None:
            return False, None

        ts, payload = item
        if time.time() - ts > _CACHE_TTL_SECONDS:
            _cache.pop(cache_key, None)
            return False, None

        return True, payload.copy() if payload is not None else None


async def _set_cached(
    cache_key: tuple[str, str], payload: Optional[dict[str, Any]]
) -> None:
    async with _cache_lock:
        _cache[cache_key] = (
            time.time(),
            payload.copy() if payload is not None else None,
        )


async def get_tradingview_ta_summary(
    symbol: str, asset_hint: str | None = None
) -> Optional[dict[str, Any]]:
    normalized = _normalize_symbol(symbol)
    if not normalized:
        logger.warning(
            "[tradingview-ta] normalized symbol is empty for input: %r", symbol
        )
        return None

    hint = str(asset_hint or "").strip().lower()
    cache_key = (normalized, hint)

    found, cached = await _get_cached(cache_key)
    if found:
        return cached

    async with _REQUEST_SEMAPHORE:
        found, cached = await _get_cached(cache_key)
        if found:
            return cached

        payload = await asyncio.to_thread(_fetch_analysis_sync, normalized, hint)
        await _set_cached(cache_key, payload)
        return payload


def _reset_cache_for_tests() -> None:
    _cache.clear()


if __name__ == "__main__":
    import asyncio as _asyncio
    import json

    # Set logger to debug
    logging.basicConfig(level=logging.DEBUG)

    async def main() -> None:
        result = await get_tradingview_ta_summary("AAPL", "stock")
        print(json.dumps(result, indent=2))

    _asyncio.run(main())
