# fintwit-web

**Self-hosted dashboard for crypto, stocks, forex and options — enriched Twitter/X streams,
sentiment analysis, and market signals.**

![banner](docs/imgs/banner.png)

---

<p align="center">
  <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/StephanAkkerman/fintwit-web/pyversions.yml?label=python%203.11%20%7C%203.12%20%7C%203.13&logo=python&style=flat-square">
  <img src="https://img.shields.io/github/license/StephanAkkerman/fintwit-web.svg?color=brightgreen" alt="License">
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

`fintwit-web` aggregates financial markets data from Twitter/X, Reddit, Binance, Yahoo Finance,
TradingView, and more — enriched with ML-based sentiment analysis and chart recognition — and
surfaces it through a self-hosted React dashboard.

It's a full-stack migration of the [`fintwit-bot`](https://github.com/StephanAkkerman/fintwit-bot)
Discord bot: same data pipelines and ML models, but without Discord's rate limits, low data
density, and lack of a custom UI. The dashboard covers crypto, stocks, forex, options, NFTs,
enriched tweets, and live portfolio tracking. The migration is ongoing and incremental — see
[Documentation](#documentation) for current coverage.

## Key Features 🔑

- **Enriched tweet timeline** — streamed live from X/Twitter, classified by ticker, scored for
  sentiment (FinTwitBERT), and flagged for chart images (chart-recognizer)
- **Crypto markets** — price index, trending coins, gainers/losers, funding rates, liquidations,
  exchange listings, TradingView ideas
- **Stock markets** — price index, earnings calendar, halts, StockTwits, TradingView ideas,
  gainers/losers
- **Options, forex & NFTs** — options overview/volume/SPACs/short interest, forex index with
  economic events and yield curve, NFT top/trending/upcoming/P2E collections
- **Reddit** — WallStreetBets scraping for cross-subreddit ticker trends
- **Portfolio tracking** — live trade tracking, with optional Interactive Brokers sync
- **Self-hosted** — SQLite or PostgreSQL storage, runs via Docker Compose, no Discord required

### Machine Learning Models 🤖

Multiple custom-trained models power the enrichment pipeline. All are lightweight and load
automatically when the backend starts:

- [FinTwitBERT-sentiment](https://huggingface.co/StephanAkkerman/FinTwitBERT-sentiment) —
  classifies the sentiment of financial tweets
- [FinTwitBERT-wsb-sentiment](https://huggingface.co/StephanAkkerman/FinTwitBERT-wsb-sentiment) —
  classifies the sentiment of WallStreetBets posts
- [chart-recognizer](https://huggingface.co/StephanAkkerman/chart-recognizer) — 
  recognizes if an image is a financial chart
- [chart-info-detector](https://huggingface.co/StephanAkkerman/chart-info-detector) — 
  extracts the ticker and price from a chart image if the post text doesn't contain it
- [stock-recognizer-model](https://huggingface.co/StephanAkkerman/stock-recognizer-model) — 
  recognizes the mentioned stocks in reddit posts

## Screenshots 📸

<p align="center">
  <img src="docs/imgs/screenshots/home.png" width="860" alt="fintwit-web home — enriched tweet timeline">
</p>

The enriched tweet timeline (above) is the flagship view — each tweet is ticker-classified,
sentiment-scored, and matched with a live price card, alongside cross-market overview panels
(mention heat, sentiment shift, sector rotation) built from Twitter, Reddit, and StockTwits data.

<table>
  <tr>
    <td width="50%"><img src="docs/imgs/screenshots/crypto.png" alt="Crypto dashboard"><br><sub>Crypto — trending coins, Binance movers, market cap</sub></td>
    <td width="50%"><img src="docs/imgs/screenshots/stocks.png" alt="Stocks dashboard"><br><sub>Stocks — fear/greed index, halts, StockTwits signals</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/imgs/screenshots/portfolio.png" alt="Portfolio dashboard"><br><sub>Portfolio — value over time, asset context, IBKR sync</sub></td>
    <td width="50%"><img src="docs/imgs/screenshots/options.png" alt="Options dashboard"><br><sub>Options — overview, put/call ratio, live options chain</sub></td>
  </tr>
</table>

## Table of Contents 🗂

- [Key Features](#key-features-)
- [Screenshots](#screenshots-)
- [Quick Start](#quick-start-)
- [Connect your X account](#connect-your-x-account)
- [Configuration](#configuration)
- [Optional add-ons](#optional-add-ons)
- [Updating](#updating)
- [Local development](#local-development-)
- [Documentation](#documentation)
- [Contributing](#contributing-)
- [License](#license-)

## Quick Start 🚀

Runs on a Raspberry Pi, a home server, or any Linux/macOS/Windows host with
[Docker](https://docs.docker.com/get-docker/) (on Linux: `curl -fsSL https://get.docker.com | sh`).

```bash
git clone https://github.com/StephanAkkerman/fintwit-web.git
cd fintwit-web
cp .env.example .env        # then set X_AUTH_TOKEN and X_CT0, see below
docker compose up -d
```

Open **http://127.0.0.1:3000**. `docker compose up` pulls prebuilt images (amd64 and arm64)
and falls back to building from source if it can't.

Only the X cookies are needed for the tweet timeline ([how to get them](#connect-your-x-account)).
Skip them and everything else still works; the timeline explains how to connect. The stack is
**localhost-only by default**: the frontend is on `127.0.0.1:3000` and the backend API on
`127.0.0.1:7999`, and nothing is exposed beyond your machine until you opt into the
[Cloudflare Tunnel](#public-access-via-cloudflare-tunnel).

## Connect your X account

The tweet timeline streams your X **Following** feed as your own logged-in session, not through
an official API key. It needs two cookies from that session:

1. Log into [x.com](https://x.com) in your browser.
2. Open DevTools (F12) → **Application** tab (Firefox: **Storage**) → **Cookies** →
   `https://x.com`.
3. Copy the values of `auth_token` and `ct0` into `.env`, then restart the backend
   (`docker compose up -d`):

```bash
X_AUTH_TOKEN=...
X_CT0=...
```

These cookies grant full access to your X account: `.env` is gitignored, never commit it, and
treat the values like a password. They stay valid until that browser session is logged out.
When X starts rejecting them, the timeline shows an "X session expired" notice; recapture both
values and restart.

<details>
<summary>Already have a <code>curl.txt</code>?</summary>

A captured `HomeLatestTimeline` request (DevTools → Network → right-click → Copy as cURL) still
works when `X_AUTH_TOKEN`/`X_CT0` are unset: put it at the repo root for local runs, or at
`state/curl.txt` for Docker. `X_CURL_PATH` overrides the location.

</details>

## Configuration

Everything lives in `.env`. [`.env.example`](.env.example) lists what a typical install touches:
the X cookies, an optional API key, and commented-out blocks for each optional integration.
[docs/configuration.md](docs/configuration.md) documents every variable, including tuning knobs.
In Docker, every `.env` value is passed to the backend. Keep the `KEY=value` format, with no
spaces around `=`.

The backend logs which integrations are active when it starts:

```
[startup] integrations: X timeline: cookies | Reddit: unauthenticated fallback | IBKR: off | ...
```

Setting `API_KEY` protects the backend's `/api` with an `X-API-Key` header. The dashboard keeps
working because the frontend's proxy (nginx in Docker, Vite in dev) attaches the key
server-side, so it never reaches the browser.

## Optional add-ons

Each of these is opt-in; skip the ones you don't need.

### Interactive Brokers portfolio sync

Adds the `ibgateway` container and a backend sync worker. In `.env`, set:

```bash
IBKR_ENABLED=true
TRADING_MODE=live
TWS_USERID=your-ibkr-username
TWS_PASSWORD=your-ibkr-password
VNC_SERVER_PASSWORD=change-me-to-a-strong-password
COMPOSE_PROFILES=ibkr
```

`TRADING_MODE` is `live` or `paper`; the backend picks the matching gateway port. Then run
`docker compose up -d`.

IB Gateway runs headless most days, but still asks for an occasional interactive login/2FA
approval. Connect a VNC client (e.g. Remmina: `sudo apt install -y remmina remmina-plugin-vnc`)
to `127.0.0.1:5901` with `VNC_SERVER_PASSWORD`, complete the login and any 2FA prompt, and leave
it running.

Check sync health:

```bash
docker logs -f fintwit-ibgateway
docker logs -f fintwit-backend
curl -H "X-API-Key: YOUR_API_KEY" http://127.0.0.1:7999/api/ibkr/status   # connected: true
```

Notes:

- In Docker the backend reaches the gateway at `ibgateway:4003` (live) or `:4004` (paper).
  `connection refused` there means IB Gateway is up but the login/2FA isn't complete yet.
- Running the backend outside Docker? Set `IBKR_HOST=127.0.0.1`; it then uses 4001/4002.
- Gateway settings persist in `./ibgateway-settings`.

### Public access via Cloudflare Tunnel

Adds the `cloudflared` container and an Access login gate, so only people on your allowlist can
reach the dashboard. One-time Cloudflare setup:

1. Create a free [Cloudflare](https://dash.cloudflare.com/sign-up) account and add your domain.
2. At your domain registrar, switch its nameservers to the ones Cloudflare assigns.
3. Create an API token at
   [dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) with:
   Account → Access: Apps and Policies → Edit; Account → Cloudflare Tunnel → Edit;
   Zone → DNS → Edit; Zone → Zone → Read.

Then provision the tunnel, DNS record and Access policy with Terraform, from `infra/`:

```bash
cp terraform.tfvars.example terraform.tfvars
# set your Cloudflare token/account values and access_allowed_emails
terraform init
terraform apply
terraform output -raw tunnel_token
```

Back in the repo root, add to `.env` and run `docker compose up -d`:

```bash
CLOUDFLARE_TUNNEL_TOKEN=<terraform tunnel_token output>
COMPOSE_PROFILES=tunnel
```

(`COMPOSE_PROFILES=ibkr,tunnel` if you also use IBKR.) The dashboard is then served at
`https://<subdomain>.<zone_name>` from `terraform.tfvars`. Visitors first see Cloudflare's login
page and verify with a one-time code emailed to them; anyone not on the allowlist is blocked at
Cloudflare's edge. `access_allowed_emails` only seeds the list; after that, manage it from the
dashboard's **Admin** page, which needs a few more `.env` values (see
[infra/README.md](infra/README.md#admin-page-invites)).

### Reddit API credentials

Without credentials, the r/wallstreetbets service uses an unauthenticated HTTP fallback, which
Reddit blocks more often. For more reliable access, create a "script" app at
[reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) and set `REDDIT_CLIENT_ID` and
`REDDIT_CLIENT_SECRET` in `.env`.

### Raspberry Pi and older CPUs

If the backend crashes with a PyTorch `Illegal instruction` error in chart recognition (common
on ARM and older CPUs), disable chart inference and/or chart OCR in `.env`:

```bash
CHART_ENABLED=false
CHART_EXTRACTION_ENABLED=false
```

To find the failing stage (PyTorch conv vs timm vs chart model), run
`docker exec -it fintwit-backend python -m app.runtime.probe_chart_stack`. To use a different
PyTorch version, set `TORCH_VERSION` in `.env` and build locally with
`docker compose up -d --build backend`. The image uses CPU-only PyTorch wheels, so no CUDA
runtime is downloaded.

## Updating

```bash
make update
```

This runs `git pull`, pulls the latest prebuilt images, and restarts the stack, picking up any
`COMPOSE_PROFILES` (e.g. `ibkr`, `tunnel`) set in `.env`. If the images can't be pulled, it
builds them from source instead (`docker compose up -d --build`). No `make` on your host? Run
the same steps directly:

```bash
git pull
docker compose pull
docker compose down
docker compose up -d
```

## Local development ⚙️

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
cp .env.example .env
npm run dev
```

`npm run dev` starts `uvicorn` on `127.0.0.1:7999` and the Vite dev server on
**http://127.0.0.1:5173**, which proxies `/api/*` to the backend. To run them separately:

```bash
uvicorn app.api.main:app --port 7999 --reload
cd frontend && npm run dev
```

`make check` runs the same tests, linting and build checks as CI.

## Documentation

- [Configuration Reference](docs/configuration.md)
- [Documentation Index](docs/README.md)
- [Migration Status](docs/migration-status.md)
- [API and Frontend Coverage Matrix](docs/api-frontend-coverage.md)
- [Frontend Integration Map](docs/frontend-integration-map.md)
- [Cloudflare Terraform Notes](infra/README.md)

## Contributing 🛠

Contributions are welcome! If you have a feature request, bug report, or proposal for code
refactoring, please feel free to open an issue on GitHub. See [CONTRIBUTING.md](CONTRIBUTING.md)
for code style and PR guidelines. We appreciate your help in improving this project.

![https://github.com/StephanAkkerman/fintwit-web/graphs/contributors](https://contributors-img.firebaseapp.com/image?repo=StephanAkkerman/fintwit-web)

## License 📜

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
