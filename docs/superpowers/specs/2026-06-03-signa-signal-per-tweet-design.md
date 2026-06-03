# Signa signal per tweet — design

**Date:** 2026-06-03
**Status:** Approved

## Goal

Surface the Signa `get_signal` verdict on each tweet's asset card, alongside the
existing TradingView technical analysis (TA). At the same time, convert the Signa
service client from blocking `requests` calls to non-blocking `aiohttp` so it does
not stall the async enrichment pipeline. Both the new Signa signal and the existing
TradingView TA recommendation are color-coded by direction (green = bullish/buy,
red = bearish/sell, grey = neutral) so direction is readable at a glance.

## Background

The TradingView TA already flows through the pipeline like this:

1. `app/runtime/enricher.py` classifies cashtags to asset kinds, fetches financials,
   then fetches `get_tradingview_ta_summary(symbol, hint)` and merges the result into
   each asset's `financials["technical_analysis"]` dict.
2. The asset list (with `financials`) is stored as JSON on the tweet and served over
   both REST and SSE — no Pydantic schema change is needed for nested financial data.
3. `frontend/src/components/TweetCard.tsx` and `AssetBadge.tsx` render
   `financials.technical_analysis` via `TradingViewAnalysis.tsx`.

Signa will reuse this exact path. `app/services/signa.py` already implements a
`SignaClient` with TTL caching and a 60/min·1000/day local quota guard, but it uses
synchronous `requests`, which blocks the event loop when called from the async
enricher.

## Scope (confirmed)

- **Endpoint:** `get_signal` (`/api/v1/signal?sym=...`).
- **Asset kinds:** equity-like only — `EQUITY`, `ETF`, `INDEX`, `FUTURE`. Crypto,
  forex, and commodity are skipped (Signa's universe is stock-focused, and this
  conserves the API quota).
- **Display:** color-coded signal label (Bullish / Bearish / Neutral) + numeric
  score + confidence.
- **Lookup symbol:** the cashtag symbol (`entry["symbol"]`, e.g. `AAPL`), not the
  Yahoo lookup (`DX-Y.NYB`), since Signa expects plain tickers.

## Design

### 1. Async rewrite of `app/services/signa.py`

- `SignaClient._request`, `get_signal`, `get_quote`, `get_history`,
  `get_enhanced_signal`, `get_signal_index`, `scan`, `get_me`, `get_analysis`
  become `async def`.
- Replace `requests` with `aiohttp`: open an `aiohttp.ClientSession` with an
  `aiohttp.ClientTimeout(total=timeout_seconds)` per request, mirroring the pattern
  already used in `app/services/yahoo.py`.
- Replace `threading.Lock` with `asyncio.Lock`. Cache read/write and the rate-budget
  consumption run inside `async with self._lock`.
- TTL cache semantics and the per-minute/per-day quota logic are preserved
  unchanged, including the injectable `time_fn` for tests.
- Module-level helper functions (`signal_request`, `quote_request`, …) become async
  thin wrappers over the default client.
- **New module-level helper** `async def get_signa_signal(ticker)` — analogous to
  `get_tradingview_ta_summary`. Calls `_default_client.get_signal(ticker)`,
  normalizes, and returns `None` on failure or empty payload:

  ```python
  {
      "source": "signa",
      "symbol": "AAPL",
      "signal": "Bullish",      # from payload["signa"]
      "score": 74,               # from payload["data"]["score"]
      "trend": "up",             # from payload["data"]["trend"]
      "confidence": 0.81,        # from payload["data"]["confidence"]
      "timeframe": "1D",         # from payload["timeframe"]
      "website": "https://app.getsigna.ai/?sym=AAPL",
  }
  ```

  Normalization tolerates missing keys (any of score/trend/confidence/timeframe may
  be absent). If `signa`/signal label is missing, return `None`.

### 2. Enricher integration (`app/runtime/enricher.py`)

- Add `_SIGNA_KINDS = {"EQUITY", "ETF", "INDEX", "FUTURE"}`.
- After the existing `ta_tasks` gather, build a parallel `signa_tasks` list: for each
  classified entry whose kind is in `_SIGNA_KINDS`, append
  `get_signa_signal(entry["symbol"])`; otherwise append `self._dummy_info()` (→ None).
- `await asyncio.gather(*signa_tasks, return_exceptions=True)`.
- In the existing attach loop, when both `financial_payload` and the signa result are
  dicts, set `financial_payload["signa"] = signa_result`. Exceptions are logged at
  debug and ignored (same handling as financials/TA).

No DB migration or Pydantic schema change — `financials` is stored as a JSON blob.

### 3. Frontend

- `frontend/src/types.ts`:
  ```ts
  export type AssetSignaSignal = {
    source?: string | null;
    symbol?: string | null;
    signal: string;
    score?: number | null;
    trend?: string | null;
    confidence?: number | null;
    timeframe?: string | null;
    website?: string | null;
  };
  ```
  Add `signa?: AssetSignaSignal | null;` to `AssetFinancials`.
- **Shared direction colors:** add a small helper (e.g.
  `frontend/src/utils/directionColor.ts`) mapping a direction to Tailwind classes:
  green for bullish/buy, red for bearish/sell, grey for neutral. Both the Signa and
  TradingView components use it so the color language is identical.
  - Bullish: `text-emerald-600 dark:text-emerald-400`
  - Bearish: `text-rose-600 dark:text-rose-400`
  - Neutral: `text-zinc-500 dark:text-zinc-400`
- New `frontend/src/components/SignaSignal.tsx`: renders a single compact row
  (returns `null` when no signal). Label is color-coded via the shared helper —
  green / red / grey — followed by score (e.g. `74`) and confidence (e.g. `81%`).
  Styling matches the `TradingViewAnalysis` rows so the two stack cleanly.
- **Color-code the existing TradingView TA** (`TradingViewAnalysis.tsx`): the
  recommendation text is currently plain. Map it to a direction via the shared
  helper so direction is readable at a glance — `Strong Buy`/`Buy` → green,
  `Strong Sell`/`Sell` → red, `Neutral` (and anything else) → grey. Apply the color
  to the recommendation label per timeframe row.
- Render `<SignaSignal signal={financials?.signa} />` directly after
  `<TradingViewAnalysis>` in both `TweetCard.tsx` and `AssetBadge.tsx`.

### 4. Tests

- Rewrite `tests/test_signa_service.py` to mock `aiohttp` (fake session/response with
  async context managers) and drive the now-async client with `pytest.mark.asyncio`.
  Preserve coverage: endpoint coverage, empty-ticker, request error, cache hit, cache
  TTL expiry, per-minute limit, per-day limit. Add a test for `get_signa_signal`
  normalization (happy path + missing-label → None).
- Extend `tests/test_enricher.py` to assert `financials["signa"]` is attached for an
  equity-kind asset and absent for a crypto asset (with `get_signa_signal` patched).
- Frontend: add `SignaSignal` render test, and assert `TweetCard` shows the signal
  label when an asset carries `financials.signa`. Add an assertion that the
  `TradingViewAnalysis` recommendation carries the expected direction color class
  (green for Buy, red for Sell, grey for Neutral).

## Error handling

- Network/JSON errors in the client are caught and logged at warning/debug, returning
  `None` (existing behavior retained).
- Quota exhaustion returns `None` without a network call (existing behavior).
- `get_signa_signal` returns `None` on any failure; the enricher treats `None` /
  exceptions as "no signa" and simply omits the key — the UI renders nothing.

## Out of scope

- `get_enhanced_signal` (trade levels, news) — not used here.
- Signa for crypto/forex/commodity assets.
- A standalone Signa REST endpoint or dashboard widget.
