# Jules Core Directives
1. **Source Repository:** Your primary task is to migrate code from the legacy repository `StephanAkkerman/fintwit-bot`. Always fetch the legacy logic from there when asked to build a new feature here.
2. **Target Repository:** You are currently operating in `StephanAkkerman/fintwit-web`. All generated code and Pull Requests must be applied here.
3. **Architecture:** Strictly follow the FastAPI and React paradigm mapped out below. Do not use Discord.py or Pandas DataFrames for routing or data passing.

# Architectural & Migration Guide
## 1. Project Overview

**Goal:** Migrate `fintwit-bot` (a Discord-based financial scraper and aggregator) to `fintwit-web` (a full-stack web application).
The application aggregates, analyzes, and streams financial data (Crypto, Stocks, Forex, NFTs, and Financial Twitter) into a unified dashboard.

**Tech Stack:**

* **Backend:** Python, FastAPI, SQLAlchemy (async, SQLite/PostgreSQL), Pydantic, asyncio (for background tasks/SSE).
* **Frontend:** React, TypeScript, TailwindCSS, Vite.
* **Machine Learning:** PyTorch/HuggingFace (FinTwitBERT for sentiment analysis, timm for chart image classification).

---

## 2. Paradigm Shifts (Old vs. New)

AI agents must adhere to these architectural shifts when porting code:

| Feature | Legacy (Discord Bot) | Target (FastAPI + React) |
| --- | --- | --- |
| **User Interface** | Discord Channels & Embeds | React Dashboards & Widgets |
| **User Inputs** | Slash Commands (`/stock add`) | RESTful API Endpoints (`POST /api/portfolio`) |
| **Data Storage** | Pandas `.to_sql()` / Pickles | SQLAlchemy ORM Models + Alembic Migrations |
| **Background Tasks** | `discord.ext.tasks.loop` | `asyncio` tasks (via FastAPI `lifespan`) or Celery/ARQ |
| **Real-time Updates** | Sending Discord messages | Server-Sent Events (SSE) / WebSockets |
| **Data Passing** | Passing DataFrames around | Pydantic Schemas / JSON |

---

## 3. Backend Architecture (FastAPI)

### 3.1 Directory Structure

Agents should organize the backend strictly as follows:

```text
app/
├── api/                # FastAPI routers (REST endpoints & SSE streams)
├── core/               # App config, lifespan events, security/auth
├── infra/              # Database connection, SQLAlchemy setup
├── models/             # SQLAlchemy ORM models (db rows)
├── schemas/            # Pydantic models (request/response validation)
├── repos/              # Database abstraction layer (CRUD operations)
├── services/           # External API scrapers (Binance, Yahoo, CMC, etc.)
├── ml/                 # PyTorch/Huggingface model wrappers (Chart, Sentiment)
└── runtime/            # Background workers, SSE broadcasters, state managers

```

### 3.2 Migration Mapping: External APIs (`src/api/` -> `app/services/`)

The legacy bot relies heavily on third-party scraping.

* **Action:** Port the scripts in `fintwit-bot/src/api/` to `app/services/`.
* **Refactor:** Strip out any Discord-specific logic (`discord.Embed`). Return pure Python dictionaries, lists, or Pydantic models instead of raw Pandas DataFrames wherever possible. Maintain the `aiohttp` async patterns.

### 3.3 Migration Mapping: Background Loops (`src/cogs/loops/` -> `app/runtime/`)

The legacy bot polls data continuously.

* **Action:** Convert `@loop(hours=X)` decorators into infinite `asyncio` loops with `await asyncio.sleep(X)` inside `app/runtime/workers/`.
* **Flow:** 1. Worker wakes up.
2. Fetches data via `app/services/`.
3. Saves state to DB via `app/repos/`.
4. (Optional) Pushes new data to `app/runtime/broadcast.py` for real-time frontend updates via SSE.

### 3.4 Migration Mapping: Commands (`src/cogs/commands/` -> `app/api/`)

* **Action:** Convert Discord slash commands to FastAPI routes.
* `/analyze AAPL` -> `GET /api/stocks/{ticker}/analysis`
* `/earnings AAPL` -> `GET /api/stocks/{ticker}/earnings`
* `/sentiment AAPL` -> `GET /api/stocks/{ticker}/sentiment`
* `/portfolio add` -> `POST /api/portfolio`

### 3.5 Machine Learning (`src/models/` -> `app/ml/`)

* **Action:** Port `chart.py` and `sentiment.py`.
* **Constraint:** Ensure model loading happens *once* during the FastAPI `lifespan` startup to prevent memory leaks and blocking the event loop.

---

## 4. Frontend Architecture (React/TS)

### 4.1 Directory Structure

```text
frontend/src/
├── components/         # Reusable UI components (Cards, Tables, Charts)
├── features/           # Domain-specific components (e.g., /portfolio, /tweets)
├── hooks/              # Custom React hooks (e.g., useSSE, useFetch)
├── services/           # API client (Axios or native fetch wrappers)
├── types/              # TypeScript interfaces mirroring Backend Pydantic schemas
└── App.tsx             # Main routing and layout

```

### 4.2 State Management & Data Fetching

* **Live Data (Twitter, Liquidations, Trades):** Use Server-Sent Events (SSE). Extend the pattern currently implemented in `useTweets.ts`.
* **Static/Polled Data (Earnings, Heatmaps, Portfolios):** Use standard REST fetching. (Consider introducing `@tanstack/react-query` for caching and auto-refetching).
* **Types:** Always type the payloads in `frontend/src/types.ts` based on the FastAPI Pydantic schemas.

### 4.3 UI/UX Design Guidelines (TailwindCSS)

* **Theme:** Maintain a sleek, dark-mode friendly aesthetic (`dark:bg-black`, `dark:text-zinc-100`).
* **Dashboards:** Replace Discord channels with categorized dashboard routes (e.g., `/crypto`, `/stocks`, `/nfts`, `/portfolio`).
* **Visualizing Data:** * Replace matplotlib-generated images (e.g., `rainbow_chart.png`, `liquidations.png`) with interactive frontend charting libraries where possible (e.g., `Recharts`, `Chart.js`, or `TradingView Lightweight Charts`).
* If server-side rendering of charts is still preferred for complex plots (like the SPY heatmap or Yield curve), serve them as static images or base64 strings from FastAPI endpoints.

---

## 5. Execution Plan for AI Agents

When prompted to build a feature, agents should follow this step-by-step workflow:

1. **Database Layer:** Define the SQLAlchemy model (`app/models/`) and the corresponding Pydantic schemas (`app/schemas/`).
2. **Service Layer:** Migrate the specific data-fetching logic from `fintwit-bot/src/api/` into `app/services/`. Return Pydantic models.
3. **Repository Layer:** Write the CRUD operations in `app/repos/`.
4. **Runtime/Worker (If applicable):** If the data needs periodic fetching, create a background worker in `app/runtime/` and register it in the FastAPI `lifespan`.
5. **API Layer:** Create the FastAPI router endpoint in `app/api/` to serve the data or stream.
6. **Frontend Hook:** Create a React hook in `frontend/src/hooks/` to consume the new endpoint.
7. **Frontend UI:** Build the React component using TailwindCSS to display the data beautifully.

## 6. Code Formatting & Style
This project adheres to strict code formatting and style guidelines to maintain readability and consistency across the codebase.

### Backend Formatting
* Use `black` with default settings for consistent code formatting.
* Use `numpy-style docstrings` for all functions and classes. Example:

```python
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together.

    Args:
        a (int): The first number.
        b (int): The second number.
        
    Returns:
        int: The sum of the two numbers.
    """
    return a + b
```

### Frontend Formatting
* Use `prettier` for consistent code formatting in JavaScript/TypeScript files.
* Use `eslint` with the Airbnb style guide for linting and code quality.

## 7. Testing
* Backend: Use `pytest` and `pytest-asyncio` for testing FastAPI endpoints and background workers. Aim for high test coverage, especially for critical data-fetching logic and API routes.
* Frontend: Use `Jest` and `React Testing Library` for unit and integration tests of React components and hooks.