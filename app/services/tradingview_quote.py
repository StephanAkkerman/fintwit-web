import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return ""

    if ":" in s:
        _, _, s = s.partition(":")

    if s.endswith("=X"):
        s = s[:-2]

    if s.startswith("^"):
        s = s[1:]

    if s.endswith("-USD"):
        s = s.replace("-", "")

    return s


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
        price = _to_float(row.get("close"))
        if price is None or price <= 0:
            continue

        score = 0.0
        row_type = str(row.get("type") or "").lower()
        row_symbol = str(row.get("symbol") or "").upper()
        volume = _to_float(row.get("volume"))

        if volume is not None and volume > 0:
            score += 1.0

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


def _fetch_symbol_market_row_sync(
    symbol: str, asset_hint: str | None
) -> Optional[dict]:
    try:
        from tradingview_scraper.symbols.symbol_markets import SymbolMarkets
    except Exception as exc:
        logger.debug("[tradingview] package import failed: %r", exc)
        return None

    markets = SymbolMarkets()
    rows: list[dict] = []

    for scanner in _scanner_priority(asset_hint):
        try:
            result = markets.scrape(symbol=symbol, scanner=scanner, limit=25)
        except TypeError:
            result = markets.scrape(symbol=symbol, limit=25)
        except Exception as exc:
            logger.debug(
                "[tradingview] symbol_markets scrape failed for %s/%s: %r",
                symbol,
                scanner,
                exc,
            )
            continue

        data = result.get("data") if isinstance(result, dict) else result
        if isinstance(data, list):
            rows.extend([r for r in data if isinstance(r, dict)])

        best = _pick_best_row(rows, asset_hint)
        if best is not None:
            return best

    return _pick_best_row(rows, asset_hint)


async def get_tradingview_quote(
    symbol: str, asset_hint: str | None = None
) -> Optional[dict]:
    """Best-effort TradingView quote fallback.

    Returns data in the same shape as yahoo/coingecko quote helpers:
    ``{price, change_percent, volume, website}``.
    """

    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    row = await asyncio.to_thread(_fetch_symbol_market_row_sync, normalized, asset_hint)
    if row is None:
        return None

    price = _to_float(row.get("close"))
    if price is None:
        return None

    change = _to_float(row.get("change"))
    volume = _to_float(row.get("volume"))
    tv_symbol = str(row.get("symbol") or normalized).upper()

    return {
        "price": price,
        "change_percent": change if change is not None else 0.0,
        "volume": volume if volume is not None else 0.0,
        "website": f"https://www.tradingview.com/symbols/{tv_symbol.replace(':', '-')}/",
        "source": "tradingview",
    }
