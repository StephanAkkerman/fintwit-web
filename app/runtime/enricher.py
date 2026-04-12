import asyncio
import logging
from collections import OrderedDict
from typing import Dict, List

from ticker_classifier.classifier import TickerClassifier

from ..services.coingecko import get_crypto_info
from ..services.yahoo import get_stock_info

logger = logging.getLogger(__name__)

_YAHOO_PRICED_KINDS = {"EQUITY", "ETF", "INDEX", "FUTURE", "FOREX", "COMMODITY"}


def _normalize_kind(kind: object) -> str:
    return str(kind or "").strip().upper()


def _is_crypto_kind(kind: object) -> bool:
    return _normalize_kind(kind) == "CRYPTO"


def _should_use_yahoo(kind: object) -> bool:
    return _normalize_kind(kind) in _YAHOO_PRICED_KINDS


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
                    symbol = (
                        getattr(r, "symbol", None) or r.get("symbol") or r.get("ticker")
                    )
                    symbol = (symbol or "").upper()
                    if not symbol:
                        continue

                    kind = (
                        getattr(r, "kind", None) or r.get("kind") or r.get("category")
                    )
                    meta = getattr(r, "meta", None) or r.get("meta")
                    name = getattr(r, "name", None) or r.get("name")
                    market_cap = getattr(r, "market_cap", None) or r.get("market_cap")
                    sector = getattr(r, "sector", None) or r.get("sector")
                    industry = getattr(r, "industry", None) or r.get("industry")
                    company_profile = getattr(r, "company_profile", None)
                    if not isinstance(company_profile, dict):
                        try:
                            company_profile = r.get("company_profile")
                        except Exception:
                            company_profile = None
                    if not isinstance(company_profile, dict):
                        company_profile = None

                    yahoo_lookup_value = getattr(r, "yahoo_lookup", None)
                    if not isinstance(yahoo_lookup_value, str):
                        try:
                            yahoo_lookup_value = r.get("yahoo_lookup")
                        except Exception:
                            yahoo_lookup_value = None

                    yahoo_lookup = None
                    if (
                        isinstance(yahoo_lookup_value, str)
                        and yahoo_lookup_value.strip()
                    ):
                        yahoo_lookup = yahoo_lookup_value.upper()

                    self._cache[symbol] = {
                        "symbol": symbol,
                        "kind": kind,
                        "name": name,
                        "market_cap": market_cap,
                        "sector": sector,
                        "industry": industry,
                        "company_profile": company_profile,
                        "meta": meta,
                        "yahoo_lookup": yahoo_lookup,
                    }

        # preserve input order, unique by first occurrence
        uniq = list(OrderedDict.fromkeys(symbols))
        classified = [self._cache[s].copy() for s in uniq if s in self._cache]
        logger.debug(
            "[enricher] classified: %s", [(e["symbol"], e["kind"]) for e in classified]
        )

        # Fetch volatile financial data concurrently for all classified symbols
        tasks = []
        for entry in classified:
            kind = entry["kind"]
            symbol = entry["symbol"]
            lookup_symbol = (entry.get("yahoo_lookup") or symbol or "").upper()

            if _is_crypto_kind(kind):
                tasks.append(get_crypto_info(symbol))
            elif _should_use_yahoo(kind):
                tasks.append(get_stock_info(lookup_symbol))
            else:
                logger.debug(
                    "[enricher] %s has unhandled kind %r — skipping financials",
                    symbol,
                    kind,
                )
                tasks.append(self._dummy_info())

        financials = await asyncio.gather(*tasks, return_exceptions=True)

        # Attach fresh financials to the result
        for entry, fin in zip(classified, financials):
            if isinstance(fin, BaseException):
                logger.debug("[enricher] %s financials error: %r", entry["symbol"], fin)
                entry["financials"] = None
            else:
                entry["financials"] = fin
                logger.debug(
                    "[enricher] %s (%s) financials: %s",
                    entry["symbol"],
                    entry["kind"],
                    fin,
                )

        return classified

    async def _dummy_info(self):
        return None
