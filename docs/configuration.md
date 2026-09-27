# Configuration reference

Every setting is an environment variable, read from `.env` at the repo root (in Docker, compose
passes the whole file to the backend). [`.env.example`](../.env.example) lists only the ones a
typical install touches; this page lists all of them. Everything is optional, and anything unset
falls back to the default shown.

On startup the backend logs one line showing which integrations are active, e.g.

```
[startup] integrations: X timeline: cookies | Reddit: unauthenticated fallback | IBKR: off | ...
```

## X/Twitter timeline

| Variable | Default | Purpose |
|---|---|---|
| `X_AUTH_TOKEN` | — | `auth_token` cookie of your logged-in x.com session. |
| `X_CT0` | — | `ct0` cookie of the same session. With both unset (and no curl file), the stream is skipped and the timeline shows how to connect. |
| `X_TIMELINE_QUERY_ID` | built into `xtimeline` | GraphQL query id of `HomeLatestTimeline`. Set it only if X rotated the id before an `xtimeline` update shipped. |
| `X_CURL_PATH` | `curl.txt` (Docker: `state/curl.txt`) | Legacy auth: a captured `HomeLatestTimeline` cURL, used when the two cookies are unset. |
| `XTIMELINE_LAST_ID_PATH` | `state/last_id.txt` | Where the newest seen tweet id is kept between restarts. |
| `XCLIENT_DEBUG_HTTP` | off | `1` logs every timeline request, with secrets masked. |

## Core

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | — | When set, `/api` requires an `X-API-Key` header. The frontend's proxy (nginx in Docker, Vite in dev) attaches it, so the dashboard keeps working. |
| `DB_URL` | `sqlite+aiosqlite:///./data.db` (Docker: `./state/data.db`) | SQLAlchemy URL; a PostgreSQL DSN works too. Docker pins this, so `.env` doesn't override it there. |
| `COMPOSE_PROFILES` | — | Docker only: extra services to start, `ibkr` and/or `tunnel`. |

## Machine learning

| Variable | Default | Purpose |
|---|---|---|
| `CHART_ENABLED` | `true` | Chart recognition on tweet images. Disable it if PyTorch crashes with `Illegal instruction` (Raspberry Pi and older CPUs). |
| `CHART_EXTRACTION_ENABLED` | `true` | OCR of symbol/price from chart images whose tweet names no ticker. |
| `TORCH_VERSION` | `2.8.0` | Docker build argument: the CPU PyTorch version installed into the backend image. |

## Reddit

| Variable | Default | Purpose |
|---|---|---|
| `REDDIT_CLIENT_ID` | — | Reddit "script" app id. Without an id and secret, an unauthenticated HTTP fallback is used. |
| `REDDIT_CLIENT_SECRET` | — | Secret of that app. |
| `REDDIT_USER_AGENT` | built-in | User-Agent sent to Reddit. |
| `REDDIT_USERNAME`, `REDDIT_PASSWORD` | — | Only if your Reddit app requires user auth. |
| `REDDIT_TRENDS_ENABLED` | `1` | Background worker that aggregates subreddit ticker trends. |
| `REDDIT_TREND_INTERVAL` | `900` | Seconds between trend runs. |
| `REDDIT_TREND_WINDOW_HOURS` | `24` | Look-back window for trends. |
| `REDDIT_SUBREDDITS` | `reddit-stock-analyzer` defaults | Comma-separated subreddits to scan. |

`REDDIT_PERSONAL_USE`, `REDDIT_SECRET` and `REDDIT_APP_NAME` (fintwit-bot's names) are still
accepted in place of the client id, secret and user agent.

## Interactive Brokers

| Variable | Default | Purpose |
|---|---|---|
| `IBKR_ENABLED` | `false` | Starts the portfolio sync worker. With Docker, also add `ibkr` to `COMPOSE_PROFILES`. |
| `TRADING_MODE` | `live` | `live` or `paper`; also picks the gateway login and the default port. |
| `TWS_USERID`, `TWS_PASSWORD` | — | IB Gateway login (the `ibgateway` container). |
| `VNC_SERVER_PASSWORD` | `changeme` | Protects VNC access to the gateway for 2FA. Change it. |
| `IBKR_HOST` | `ibgateway` | Gateway host. Set to `127.0.0.1` when running the backend outside Docker. |
| `IBKR_PORT` | derived | Defaults to 4003/4004 (live/paper) for the `ibgateway` container, and 4001/4002 for any other host. |
| `IBKR_CLIENT_ID` | `1` | TWS API client id. |
| `IBKR_CONNECT_TIMEOUT` | `30` | Seconds to wait for a gateway connection. |
| `IBKR_SYNC_INTERVAL` | `60` | Seconds between position/trade syncs. |

The `ibgateway` container also honours `TWS_ACCEPT_INCOMING`, `TWS_SETTINGS_PATH`,
`TWOFA_TIMEOUT_ACTION`, `RELOGIN_AFTER_TWOFA_TIMEOUT` and `AUTO_RESTART_TIME`; see
[docker-compose.yml](../docker-compose.yml) for their defaults.

## Background workers

| Variable | Default | Purpose |
|---|---|---|
| `PORTFOLIO_SNAPSHOT_INTERVAL` | `1800` | Seconds between portfolio value snapshots. |
| `TRADER_EVAL_INTERVAL` | `1800` | Seconds between trader call credibility scoring runs. |

## Integrations

| Variable | Default | Purpose |
|---|---|---|
| `SIGNA_KEY` | — | Signa signal API key; adds signal verdicts to equity cards and the Signa route. |
| `CLOUDFLARE_TUNNEL_TOKEN` | — | Token for the `tunnel` profile's `cloudflared` container. |
| `CLOUDFLARE_ACCESS_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_ACCESS_APP_ID`, `CLOUDFLARE_ACCESS_POLICY_ID` | — | All four enable the Admin page's invite panel; see [infra/README.md](../infra/README.md#admin-page-invites). |
