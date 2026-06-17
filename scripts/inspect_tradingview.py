#!/usr/bin/env python3
"""Debug helper: inspect TradingView raw rows and the selected quote.

Usage:
  .venv\Scripts\python.exe scripts\inspect_tradingview.py CRYPTOCAP:TOTAL NDX SPY DXY

This prints the `get_tradingview_quote` result and a sampling of raw rows
scraped via `tradingview_scraper` so you can verify which row is being chosen.
"""

import asyncio
import json
import sys

from app.services import tradingview_quote

try:
    from tradingview_scraper.symbols.symbol_markets import SymbolMarkets
except Exception:
    SymbolMarkets = None

try:
    from ticker_price_data import RealTimePool
except Exception:
    RealTimePool = None


def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


async def inspect_symbol(symbol: str):
    print("\n=== Inspecting:", symbol)
    quote = await tradingview_quote.get_tradingview_quote(symbol, None)
    print("Selected quote (get_tradingview_quote):")
    _print(quote)

    # Prefer a pooled RealTimeData websocket (single connection) if available.
    if RealTimePool is not None:
        pool = None
        try:
            pool = RealTimePool()
        except Exception:
            pool = None

        if pool is not None:
            try:
                pkt = await pool.get_quote(symbol, timeout=6.0)
                print("Selected realtime quote (via pooled websocket):")
                _print(pkt)
            except Exception as exc:
                print("No realtime packet received within timeout:", exc)
            finally:
                try:
                    pool.close()
                except Exception:
                    pass
            return

    # Fallback to SymbolMarkets HTTP scrape if websocket pool not available
    if SymbolMarkets is None:
        print("tradingview_scraper not available: cannot show raw rows.")
        return

    def fetch_raw(sym: str):
        try:
            markets = SymbolMarkets()
            rows = []
            scanners = ["america", "global", "forex", "crypto"]
            for scanner in scanners:
                try:
                    result = markets.scrape(symbol=sym, scanner=scanner, limit=50)
                except TypeError:
                    result = markets.scrape(symbol=sym, limit=50)
                data = result.get("data") if isinstance(result, dict) else result
                if isinstance(data, list):
                    rows.extend([r for r in data if isinstance(r, dict)])
            return rows
        except Exception as e:
            return {"error": str(e)}

    normalized = tradingview_quote._normalize_symbol(symbol)
    raw = await asyncio.to_thread(fetch_raw, normalized)
    if isinstance(raw, dict) and raw.get("error"):
        print("Error fetching raw rows:", raw.get("error"))
        return

    print(f"Raw rows: {len(raw)} (showing up to 20)")
    for i, r in enumerate(raw[:20]):
        print("--- row", i)
        print(
            {
                "symbol": r.get("symbol"),
                "close": r.get("close"),
                "change": r.get("change"),
                "change_percent": r.get("pctChange") or r.get("changePercent"),
                "volume": r.get("volume"),
                "type": r.get("type"),
                "exchange": r.get("exchange"),
            }
        )


async def main(argv):
    if len(argv) < 2:
        print("Usage: scripts/inspect_tradingview.py SYMBOL [SYMBOL ...]")
        return

    tasks = [inspect_symbol(sym) for sym in argv[1:]]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
