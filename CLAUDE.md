# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**fintwit-web** is a full-stack financial Twitter aggregator — a FastAPI backend with a React/TypeScript frontend that streams tweets enriched with live asset data (stocks via Yahoo Finance, crypto via CoinGecko). It is an active migration from a Discord-based bot (`fintwit-bot`) to a modern web stack.

## Commands

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server
uvicorn app.api.main:app --reload

# Run tests
pytest --maxfail=1 --disable-warnings -q

# Run a single test file
pytest tests/test_api.py -v

# Lint / format
ruff check .
ruff format .
```

### Frontend

```bash
cd frontend

npm install          # install deps
npm run dev          # dev server at http://localhost:5173
npm run build        # production build
npm run preview      # preview production build
```

### Local Development

Run both concurrently — the Vite dev server proxies `/api/*` and `/healthz` to `http://127.0.0.1:8000`.

## Architecture

### Backend (`app/`)

Four-layer design, all async:

| Layer | Path | Responsibility |
|-------|------|---------------|
| API | `app/api/main.py` | FastAPI routers — REST (`/api/posts`) and SSE stream (`/api/stream`), API key auth via `X-API-Key` header |
| Runtime | `app/runtime/` | Background worker (`streamer.py`), in-memory ring buffer (`state.py`, cap 2000), fan-out SSE broadcaster (`broadcast.py`), tweet enrichment (`enricher.py`) |
| Infra | `app/infra/` | SQLAlchemy ORM models (`db.py`), `TweetRepo` CRUD (`repos.py`), schema evolution logic |
| Services | `app/services/` | External API clients — `yahoo.py` (stocks), `coingecko.py` (crypto) |

**Data flow on startup:**
1. Lifespan initialises DB (creates tables, runs schema evolution) and starts `run_stream()` background task.
2. `run_stream()` polls the X/Twitter timeline via `xtimeline` (reads `curl.txt` for auth), enriches tweets with `ticker-classifier` + live prices, upserts to SQLite, and broadcasts to all SSE subscribers.

**Database:** SQLite at `./data.db` by default; override with `DB_URL` env var (async SQLAlchemy supports PostgreSQL too). The `TweetRow` table stores tickers, hashtags, media, and assets as JSON columns.

**Authentication:** `API_KEY` env var; the FastAPI dependency is optional — missing key returns 401.

### Frontend (`frontend/src/`)

Minimal Vite/React 18/TailwindCSS SPA:

- `hooks/useTweets.ts` — dual-mode hook: initial REST fetch from `/api/posts`, then live SSE updates from `/api/stream` with deduplication (max 500 items in memory).
- `components/TweetCard.tsx` — renders a tweet with media, tickers, hashtags, and asset prices.
- `types.ts` — TypeScript interfaces mirroring the backend Pydantic schemas.

### Migration Context

This is a partial migration from `fintwit-bot` (Discord). The `AGENTS.md` file in the repo root contains the full migration blueprint, including directory conventions and the 7-step execution order (db model → service → repo → runtime worker → API endpoint → frontend hook → UI component).

## Code Style

- **Python:** Black + Ruff (line length 88), NumPy-style docstrings.
- **Imports:** isort with Black profile.
- **TypeScript:** strict mode, ESNext modules.
- CI enforces Ruff on every PR touching `.py` files and runs `pytest` on every push to `main`.
- Supported Python versions: 3.10 – 3.13.
