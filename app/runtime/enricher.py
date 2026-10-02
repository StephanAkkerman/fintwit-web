import asyncio
import logging
import time
from collections import OrderedDict
from typing import Dict, List

from ticker_classifier.classifier import TickerClassifier
from ticker_price_data import get_price_history, price_from_classification

from ..services.fundamentals_service import get_fundamentals
from ..services.signa import get_signa_signal
from ..services.stocktwits_service import get_stocktwits_sentiment
from ..services.tradingview_ta_service import get_tradingview_ta_summary

logger = logging.getLogger(__name__)

_YAHOO_PRICED_KINDS = {"EQUITY", "ETF", "INDEX", "FUTURE", "FOREX", "COMMODITY"}
# Signa's signal universe is stock-focused; only fetch for equity-like kinds.
_SIGNA_KINDS = {"EQUITY", "ETF", "INDEX", "FUTURE"}
# Valuation fundamentals (P/E, EPS, NAV, avg volume) only exist for
# individual companies and funds — indices, futures, forex and commodities
# have no such quote fields on Yahoo.
_FUNDAMENTALS_KINDS = {"EQUITY", "ETF"}
_FOREX_CODES = {
    "USD",
    "EUR",
    "JPY",
    "GBP",
    "AUD",
    "CAD",
    "CHF",
    "NZD",
    "CNY",
    "HKD",
    "SGD",
    "SEK",
    "NOK",
    "DKK",
    "TRY",
    "RUB",
    "PLN",
    "CZK",
    "HUF",
    "ZAR",
    "MXN",
    "BRL",
    "INR",
    "KRW",
}
# A classification is only trusted this long. The classifier decides between a
# stock/ETF and a crypto sharing a symbol by comparing market caps, and one bad
# call (e.g. CoinGecko rate-limited) must not stick until the next restart.
CLASSIFICATION_TTL_SECONDS = 6 * 3600
_LOCAL_SYMBOL_OVERRIDES = {
    # Crypto whose symbol is also a real Yahoo ETF/stock (Grayscale trusts for
    # BTC/ETH, iShares NEAR, ...). Pinned so they are never priced as the ETF.
    "ETH": {
        "category": "CRYPTO",
        "name": "Ethereum",
    },
    "BTC": {
        "category": "CRYPTO",
        "name": "Bitcoin",
    },
    "NEAR": {
        "category": "CRYPTO",
        "name": "NEAR Protocol",
    },
    "SOL": {
        "category": "CRYPTO",
        "name": "Solana",
    },
    "DXY": {
        "category": "INDEX",
        "name": "US Dollar Index",
        "yahoo_lookup": "DX-Y.NYB",
    },
    "SPY": {
        "category": "ETF",
        "name": "SPDR S&P 500 ETF Trust",
        "yahoo_lookup": "SPY",
    },
    "YM": {
        "category": "FUTURE",
        "name": "E-mini Dow Futures",
        "yahoo_lookup": "YM=F",
    },
    "NQ": {
        "category": "FUTURE",
        "name": "E-mini Nasdaq-100 Futures",
        "yahoo_lookup": "NQ=F",
    },
    "ES": {
        "category": "FUTURE",
        "name": "E-mini S&P 500 Futures",
        "yahoo_lookup": "ES=F",
    },
    "USOIL": {
        "category": "COMMODITY",
        "name": "Crude Oil",
        "yahoo_lookup": "CL=F",
    },
}


def _normalize_kind(kind: object) -> str:
    return str(kind or "").strip().upper()


def _is_crypto_kind(kind: object) -> bool:
    return _normalize_kind(kind) == "CRYPTO"


def _should_use_yahoo(kind: object) -> bool:
    return _normalize_kind(kind) in _YAHOO_PRICED_KINDS


def _should_use_signa(kind: object) -> bool:
    return _normalize_kind(kind) in _SIGNA_KINDS


def _is_supported_kind(kind: object) -> bool:
    return _is_crypto_kind(kind) or _should_use_yahoo(kind)


def _local_classification_override(symbol: str) -> dict | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None

    shortcut = _LOCAL_SYMBOL_OVERRIDES.get(normalized)
    if shortcut:
        return {
            "ticker": normalized,
            "category": shortcut["category"],
            "name": shortcut["name"],
            "yahoo_lookup": shortcut.get("yahoo_lookup"),
            "source": "local-shortcut",
        }

    if len(normalized) == 6 and normalized.isalpha():
        base, quote = normalized[:3], normalized[3:]
        if base in _FOREX_CODES and quote in _FOREX_CODES and base != quote:
            return {
                "ticker": normalized,
                "category": "FOREX",
                "name": f"{base}/{quote}",
                "yahoo_lookup": f"{normalized}=X",
                "source": "local-shortcut",
            }

    return None


def is_pinned_crypto(symbol: str) -> bool:
    """Return True when ``symbol`` is locally pinned as crypto (not a lookalike ETF)."""
    override = _local_classification_override(symbol)
    return bool(override) and _is_crypto_kind(override["category"])


def _build_local_cache_entry(symbol: str, override: dict) -> dict:
    yahoo_lookup_value = override.get("yahoo_lookup")
    if isinstance(yahoo_lookup_value, str) and yahoo_lookup_value.strip():
        yahoo_lookup: str | None = yahoo_lookup_value.upper()
    else:
        yahoo_lookup = None

    return {
        "symbol": symbol,
        "kind": override["category"],
        "name": override["name"],
        "market_cap": None,
        "sector": None,
        "industry": None,
        "company_profile": None,
        "fundamentals": None,
        "meta": None,
        "yahoo_lookup": yahoo_lookup,
    }


class AssetEnricher:
    """Classifies tickers to asset kinds with caching and batched misses, and enriches them with financial data."""

    def __init__(self):
        self._cls = TickerClassifier()
        # Cache static classification info only
        self._cache: Dict[str, dict] = {}
        # monotonic timestamp per classifier-sourced cache entry (for the TTL)
        self._cached_at: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def classify(self, symbols: List[str]) -> List[dict]:
        # normalize input
        symbols = [s.upper() for s in symbols if s]
        if not symbols:
            return []

        async with self._lock:
            now = time.monotonic()
            for sym in [
                s
                for s, at in self._cached_at.items()
                if now - at > CLASSIFICATION_TTL_SECONDS
            ]:
                self._cache.pop(sym, None)
                del self._cached_at[sym]

            # Force local overrides first so ambiguous symbols always classify
            # predictably, even when an older cache entry exists.
            for sym in symbols:
                local_override = _local_classification_override(sym)
                if local_override is None:
                    continue
                self._cache[sym] = _build_local_cache_entry(sym, local_override)

            misses = [s for s in symbols if s not in self._cache]
            if misses:
                classifier_misses = []
                for sym in misses:
                    local_override = _local_classification_override(sym)
                    if local_override is None:
                        classifier_misses.append(sym)
                        continue

                    self._cache[sym] = _build_local_cache_entry(sym, local_override)

                results = []
                if classifier_misses:
                    results = await self._cls.classify_async(classifier_misses)

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

                    # ticker-classifier>=0.1.5 reads this off the same Yahoo
                    # quote it fetches for classification, so it's free —
                    # but it's a snapshot from whenever this symbol was first
                    # classified in this process (this cache never expires),
                    # so it's only used as a fallback for the fresh per-call
                    # fetch in get_fundamentals() below.
                    classifier_fundamentals = getattr(r, "fundamentals", None)
                    if not isinstance(classifier_fundamentals, dict):
                        try:
                            classifier_fundamentals = r.get("fundamentals")
                        except Exception:
                            classifier_fundamentals = None
                    if not isinstance(classifier_fundamentals, dict):
                        classifier_fundamentals = None

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

                    self._cached_at[symbol] = now
                    self._cache[symbol] = {
                        "symbol": symbol,
                        "kind": kind,
                        "name": name,
                        "market_cap": market_cap,
                        "sector": sector,
                        "industry": industry,
                        "company_profile": company_profile,
                        "fundamentals": classifier_fundamentals,
                        "meta": meta,
                        "yahoo_lookup": yahoo_lookup,
                    }

        # preserve input order, unique by first occurrence
        uniq = list(OrderedDict.fromkeys(symbols))
        classified = [self._cache[s].copy() for s in uniq if s in self._cache]
        classified = [
            entry for entry in classified if _is_supported_kind(entry.get("kind"))
        ]
        logger.debug(
            "[enricher] classified: %s", [(e["symbol"], e["kind"]) for e in classified]
        )

        # Fetch volatile financial data concurrently. Price routing (crypto ->
        # CoinGecko, else -> Yahoo via yahoo_lookup) is delegated to
        # ticker-price-data so it stays a single source of truth.
        tasks = [price_from_classification(entry) for entry in classified]
        financials = await asyncio.gather(*tasks, return_exceptions=True)

        ta_tasks = []
        for entry in classified:
            kind = entry["kind"]
            lookup_symbol = (entry.get("yahoo_lookup") or entry["symbol"] or "").upper()
            if _is_crypto_kind(kind):
                ta_tasks.append(get_tradingview_ta_summary(lookup_symbol, "crypto"))
            elif _should_use_yahoo(kind):
                ta_tasks.append(
                    get_tradingview_ta_summary(lookup_symbol, str(kind).lower())
                )
            else:
                ta_tasks.append(self._dummy_info())

        technical_analysis = await asyncio.gather(*ta_tasks, return_exceptions=True)

        # Fetch Signa signals concurrently for equity-like assets only.
        signa_tasks = []
        for entry in classified:
            if _should_use_signa(entry["kind"]):
                signa_tasks.append(get_signa_signal(entry["symbol"]))
            else:
                signa_tasks.append(self._dummy_info())

        signa_signals = await asyncio.gather(*signa_tasks, return_exceptions=True)

        # Fetch StockTwits community sentiment concurrently. StockTwits covers
        # both stocks and crypto, so fetch for every supported kind.
        stocktwits_tasks = [
            get_stocktwits_sentiment(entry["symbol"]) for entry in classified
        ]
        stocktwits_sentiments = await asyncio.gather(
            *stocktwits_tasks, return_exceptions=True
        )

        # Fetch valuation fundamentals (P/E, EPS, NAV, avg volume) concurrently,
        # for equities and ETFs only.
        fundamentals_tasks = []
        for entry in classified:
            if entry["kind"] in _FUNDAMENTALS_KINDS:
                lookup_symbol = (
                    entry.get("yahoo_lookup") or entry["symbol"] or ""
                ).upper()
                fundamentals_tasks.append(get_fundamentals(lookup_symbol))
            else:
                fundamentals_tasks.append(self._dummy_info())

        fundamentals_results = await asyncio.gather(
            *fundamentals_tasks, return_exceptions=True
        )

        # Fetch a short intraday price series concurrently, for the small
        # sparkline shown next to the price in a post's asset card. Yahoo
        # lookup, same routing as the technical-analysis fetch above.
        sparkline_tasks = []
        for entry in classified:
            kind = entry["kind"]
            if _is_crypto_kind(kind):
                sparkline_tasks.append(self._fetch_sparkline(f"{entry['symbol']}-USD"))
            elif _should_use_yahoo(kind):
                lookup_symbol = (
                    entry.get("yahoo_lookup") or entry["symbol"] or ""
                ).upper()
                sparkline_tasks.append(self._fetch_sparkline(lookup_symbol))
            else:
                sparkline_tasks.append(self._dummy_info())

        sparklines = await asyncio.gather(*sparkline_tasks, return_exceptions=True)

        # Attach fresh financials to the result
        for entry, fin, ta, signa, stocktwits, fundamentals, sparkline in zip(
            classified,
            financials,
            technical_analysis,
            signa_signals,
            stocktwits_sentiments,
            fundamentals_results,
            sparklines,
        ):
            if isinstance(fin, BaseException):
                logger.debug("[enricher] %s financials error: %r", entry["symbol"], fin)
                entry["financials"] = None
            else:
                financial_payload = dict(fin) if isinstance(fin, dict) else fin
                if isinstance(financial_payload, dict) and isinstance(ta, dict):
                    financial_payload["technical_analysis"] = ta
                if isinstance(financial_payload, dict) and isinstance(signa, dict):
                    financial_payload["signa"] = signa
                if isinstance(financial_payload, dict) and isinstance(stocktwits, dict):
                    financial_payload["stocktwits_sentiment"] = stocktwits
                if (
                    isinstance(financial_payload, dict)
                    and isinstance(sparkline, list)
                    and sparkline
                ):
                    financial_payload["sparkline"] = sparkline
                entry["financials"] = financial_payload
                logger.debug(
                    "[enricher] %s (%s) financials: %s",
                    entry["symbol"],
                    entry["kind"],
                    financial_payload,
                )

            # entry["fundamentals"] currently holds whatever ticker-classifier
            # captured at classification time (or None) — a fine fallback,
            # but a stale one, since this process's classification cache
            # never expires. Prefer the fresh, hourly-refreshed fetch and
            # only fall back to that snapshot when the fresh fetch comes up
            # empty (e.g. yfinance is rate-limited or briefly unavailable).
            classifier_fundamentals = entry.get("fundamentals")
            if isinstance(fundamentals, BaseException):
                logger.debug(
                    "[enricher] %s fundamentals error: %r",
                    entry["symbol"],
                    fundamentals,
                )
                fresh_fundamentals = None
            else:
                fresh_fundamentals = (
                    fundamentals if isinstance(fundamentals, dict) else None
                )

            entry["fundamentals"] = fresh_fundamentals or (
                classifier_fundamentals
                if isinstance(classifier_fundamentals, dict)
                else None
            )

        return classified

    async def _dummy_info(self):
        return None

    async def _fetch_sparkline(self, yahoo_symbol: str) -> list[float]:
        try:
            history = await get_price_history(yahoo_symbol, range_="1d", interval="5m")
        except Exception as exc:
            logger.debug("[enricher] sparkline for %s failed: %r", yahoo_symbol, exc)
            return []
        if not history:
            return []
        return [point["close"] for point in history]
