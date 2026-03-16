# app/runtime/enricher.py
import asyncio
from collections import OrderedDict
from typing import Dict, List

from ticker_classifier.classifier import TickerClassifier


class AssetEnricher:
    """Classifies tickers to asset kinds with caching and batched misses."""

    def __init__(self):
        self._cls = TickerClassifier()
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
                # Adapt the mapping below to your classifier's return shape if needed
                for r in results:
                    # Expecting something like: r.symbol, r.kind (e.g. "EQUITY", "CRYPTO", "FX", "INDEX")
                    # If it's a dict, adjust accordingly.
                    symbol = getattr(r, "symbol", None) or r.get("symbol")
                    kind = getattr(r, "kind", None) or r.get("kind")
                    meta = getattr(r, "meta", None) or r.get("meta")
                    self._cache[symbol] = {"symbol": symbol, "kind": kind, "meta": meta}

            # preserve input order, unique by first occurrence
            uniq = list(OrderedDict.fromkeys(symbols))
            return [self._cache[s] for s in uniq if s in self._cache]
