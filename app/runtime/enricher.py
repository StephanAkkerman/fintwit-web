import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List

from ticker_classifier.classifier import TickerClassifier
from ..services.yahoo import get_stock_info
from ..services.coingecko import get_crypto_info

logger = logging.getLogger(__name__)


class AssetEnricher:
    """Classifies tickers to asset kinds with caching and batched misses, and enriches them with financial data."""

    def __init__(self):
        self._cls = TickerClassifier()
        # Cache static classification info only
        self._cache: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def classify(self, symbols: List[str]) -> List[dict]:
        # normalize input
        symbols = [s.upper() for s in symbols if s]
        if not symbols:
            return []

        async with self._lock:
            misses = [s for s in symbols if s not in self._cache]
            if misses:
                results = await self._cls.classify_async(misses)
                for r in results:
                    symbol = getattr(r, "symbol", None) or r.get("symbol") or r.get("ticker")
                    kind = getattr(r, "kind", None) or r.get("kind") or r.get("category")
                    meta = getattr(r, "meta", None) or r.get("meta")
                    name = getattr(r, "name", None) or r.get("name")
                    market_cap = getattr(r, "market_cap", None) or r.get("market_cap")

                    self._cache[symbol] = {
                        "symbol": symbol,
                        "kind": kind,
                        "name": name,
                        "market_cap": market_cap,
                        "meta": meta,
                    }

        # preserve input order, unique by first occurrence
        uniq = list(OrderedDict.fromkeys(symbols))
        classified = [self._cache[s].copy() for s in uniq if s in self._cache]
        logger.debug("[enricher] classified: %s", [(e["symbol"], e["kind"]) for e in classified])

        # Fetch volatile financial data concurrently for all classified symbols
        tasks = []
        for entry in classified:
            kind = entry["kind"]
            symbol = entry["symbol"]

            if kind == "EQUITY":
                tasks.append(get_stock_info(symbol))
            elif kind == "CRYPTO" or kind == "crypto":
                tasks.append(get_crypto_info(symbol))
            else:
                logger.debug("[enricher] %s has unhandled kind %r — skipping financials", symbol, kind)
                tasks.append(self._dummy_info())

        financials = await asyncio.gather(*tasks, return_exceptions=True)

        # Attach fresh financials to the result
        for entry, fin in zip(classified, financials):
            if isinstance(fin, BaseException):
                logger.debug("[enricher] %s financials error: %r", entry["symbol"], fin)
                entry["financials"] = None
            else:
                entry["financials"] = fin
                logger.debug("[enricher] %s (%s) financials: %s", entry["symbol"], entry["kind"], fin)

        return classified

    async def _dummy_info(self):
        return None
