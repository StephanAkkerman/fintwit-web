# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Why This Project Exists

`fintwit-bot` is a Discord bot that aggregates financial markets data from Twitter/X, Reddit, Binance, Yahoo Finance, TradingView, and many other sources — enriched with ML-based sentiment analysis and chart recognition. It posts enriched tweets, market movers, liquidations, earnings, portfolio trades, and more into categorised Discord channels.

The problem: Discord is a closed platform with rate limits, poor data density, and no custom UI. **`fintwit-web` is a migration of that bot into a self-hosted full-stack web application** — same data pipelines, same ML models, but surfaced through a proper React dashboard instead of Discord channels.

The migration is ongoing and incremental. Many features still only exist in fintwit-bot.

## What fintwit-bot Does (Scope of Migration)

- **Twitter/X:** Stream tweets, classify tickers, run sentiment (FinTwitBERT), detect chart images (chart-recognizer), post enriched embeds
- **Crypto:** Price index, trending, gainers/losers, funding rates, liquidations, exchange listings, TradingView ideas
- **Stocks:** Price index, earnings calendar, halts, StockTwits, TradingView ideas, gainers/losers
- **Options:** Overview, volume, SPACs, short interest
- **Forex:** Index, economic events, yield curve
- **NFTs:** Top, trending, upcoming, P2E
- **Reddit:** WallStreetBets scraping
- **Users/Portfolio:** Live trade tracking from Twitter traders

The legacy source is at `e:/GitHub/fintwit-bot/`. Key directories:
- `src/api/` — external API scrapers (→ migrate to `app/services/`)
- `src/cogs/loops/` — periodic background tasks (→ migrate to `app/runtime/`)
- `src/cogs/commands/` — Discord slash commands (→ migrate to `app/api/`)
- `src/models/` — ML model wrappers (→ migrate to `app/ml/`)

## Paradigm Shifts (Old → New)

| Concern | Legacy (Discord Bot) | Target (FastAPI + React) |
|---|---|---|
| UI | Discord channels & embeds | React dashboard routes (`/crypto`, `/stocks`, etc.) |
| User input | Slash commands (`/stock add`) | REST endpoints (`POST /api/portfolio`) |
| Storage | Pandas `.to_sql()` / pickles | SQLAlchemy ORM + Pydantic schemas |
| Background tasks | `discord.ext.tasks.loop` | `asyncio` loops in `app/runtime/` via FastAPI lifespan |
| Real-time updates | Sending Discord messages | Server-Sent Events (SSE) |
| Data passing | Passing DataFrames | Pydantic models / JSON |

**Never use:** `discord.py`, Pandas DataFrames for routing/data passing, or `@loop` decorators.

## Architecture

### Backend (`app/`)

| Layer | Path | Responsibility |
|---|---|---|
| API | `app/api/` | FastAPI routers — REST and SSE streams, API key auth via `X-API-Key` |
| Runtime | `app/runtime/` | Background workers, in-memory ring buffer (`state.py`, cap 2000), SSE broadcaster (`broadcast.py`), tweet enricher |
| Infra | `app/infra/` | SQLAlchemy ORM models (`db.py`), `TweetRepo` CRUD (`repos.py`), schema evolution |
| Services | `app/services/` | External API clients (Yahoo Finance, CoinGecko, etc.) |
| ML | `app/ml/` | Model wrappers — load once at lifespan startup |

**Data flow:** Lifespan starts DB + `run_stream()` → polls X/Twitter via `xtimeline` (auth from `curl.txt`) → enriches with `ticker-classifier` + live prices → upserts to SQLite → broadcasts to SSE subscribers.

**Database:** SQLite at `./data.db`; override with `DB_URL` env var. PostgreSQL also supported.

**ML Models (custom-trained):**
- [`FinTwitBERT-sentiment`](https://huggingface.co/StephanAkkerman/FinTwitBERT-sentiment) — classifies financial tweet sentiment
- [`chart-recognizer`](https://huggingface.co/StephanAkkerman/chart-recognizer) — detects if a tweet image is a financial chart

### Frontend (`frontend/src/`)

- `hooks/useTweets.ts` — REST fetch on load + SSE updates with deduplication (max 500 items)
- `components/TweetCard.tsx` — tweet with media, tickers, hashtags, asset prices
- `types.ts` — TypeScript interfaces mirroring backend Pydantic schemas

**Design intent:** Dark-mode dashboard (`dark:bg-black`, `dark:text-zinc-100`). Discord channels become dashboard routes. Matplotlib images become interactive charts (Recharts, Chart.js, or TradingView Lightweight Charts where possible).

## Development

```bash
# Backend
uvicorn app.api.main:app --reload
pytest --maxfail=1 --disable-warnings -q
ruff check . && ruff format .

# Frontend (from /frontend)
npm run dev      # proxies /api/* to http://127.0.0.1:8000
npm run build
```

## Migration Workflow

When building a new feature, follow the 7-step order in `AGENTS.md`:
1. DB model + Pydantic schema
2. Service (port from `fintwit-bot/src/api/`)
3. Repository (CRUD)
4. Runtime worker (if periodic)
5. API endpoint
6. Frontend hook
7. Frontend UI component

## Code Style

- **Python:** Ruff + Black (line length 88), NumPy-style docstrings, isort with Black profile
- **TypeScript:** strict mode, ESNext modules
- Supported Python: 3.10–3.13
