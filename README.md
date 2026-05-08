# fintwit-web

<!-- Add a banner here like: https://github.com/StephanAkkerman/fintwit-bot/blob/main/img/logo/fintwit-banner.png -->

---
<!-- Adjust the link of the first and second badges to your own repo -->
<p align="center">
  <img alt="GitHub Actions Workflow Status" src="https://img.shields.io/github/actions/workflow/status/StephanAkkerman/template/pyversions.yml?label=python%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13&logo=python&style=flat-square">
  <img src="https://img.shields.io/github/license/StephanAkkerman/template.svg?color=brightgreen" alt="License">
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
</p>

## Introduction

In this section you can provide a brief introduction to the project. You can also include a brief description of the project and its features.

## Quick Start Guide 🚀
You can run both at the same time by using at the root of the repo:
```bash
npm run dev
```

## Deploy On Raspberry Pi + Cloudflare Tunnel

### 1) Prepare your Raspberry Pi

Install Docker and the Compose plugin:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 2) Clone and configure

```bash
git clone https://github.com/StephanAkkerman/fintwit-web.git
cd fintwit-web
```

Use your `.env` file at repo root.

Important: keep env formatting as `KEY=value` (no spaces around `=`) for max compatibility.

Minimum IBKR-related values for Pi deployments:

```bash
TRADING_MODE=live
IBKR_PORT=4003
VNC_SERVER_PASSWORD=change-me-to-a-strong-password
TWS_USERID=your-ibkr-username
TWS_PASSWORD=your-ibkr-password
```

If your backend crashes on Raspberry Pi with a PyTorch `Illegal instruction`
error in chart recognition, temporarily disable chart inference:

```bash
CHART_ENABLED=false
```

To pin/downgrade PyTorch used by the backend Docker image, set:

```bash
TORCH_VERSION=2.8.0
```

and rebuild:

```bash
docker compose up -d --build backend
```

To isolate the exact failing stage (PyTorch conv vs timm vs chart model), run
the chart stack probe inside the backend container:

```bash
docker exec -it fintwit-backend python -m app.runtime.probe_chart_stack
```

This prints the first failing probe and whether it crashed with `SIGILL`.

If you use paper trading instead of live:

```bash
TRADING_MODE=paper
IBKR_PORT=4004
```

### 3) Build and run locally on Pi

```bash
docker compose down # stop any existing containers first to avoid conflicts
docker compose up -d --build
```

Build speed tips on Raspberry Pi:

- For day-to-day restarts, use `docker compose up -d` (without `--build`).
- Rebuild only when dependencies or Dockerfile change: `docker compose build backend`.
- Keep BuildKit enabled for cached package downloads across rebuilds:

```bash
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
```

The backend Docker image installs CPU-only PyTorch wheels (`download.pytorch.org/whl/cpu`) to avoid pulling large CUDA runtime packages on Linux hosts.

This stack runs:

- Frontend (Nginx + React build) on `127.0.0.1:3000`
- Backend (FastAPI) on `127.0.0.1:7999`

The frontend container proxies `/api/*` and `/api/stream` to the backend container.

##### 3.2) IBKR on Raspberry Pi (headless + local VNC)

The compose file starts an `ibgateway` container and a backend sync worker. Most days this can run headless, but IBKR may still require occasional interactive login/2FA approval.

Start IBKR + backend:

```bash
docker compose up -d --build ibgateway backend
```

If you already use RealVNC to access your Pi desktop, keep using it. Then, inside the Pi desktop session, open a local VNC client connection to the IB Gateway container:

```bash
# install once on the Pi if needed
sudo apt update
sudo apt install -y remmina remmina-plugin-vnc
```

In Remmina:

- Protocol: VNC
- Server: `127.0.0.1:5901`
- Password: `VNC_SERVER_PASSWORD` from `.env`

Complete IB Gateway login and any 2FA prompt, then keep it running.

Verify sync health:

```bash
docker logs -f fintwit-ibgateway
docker logs -f fintwit-backend

curl -H "X-API-Key: YOUR_API_KEY" http://127.0.0.1:7999/api/ibkr/status
curl -H "X-API-Key: YOUR_API_KEY" "http://127.0.0.1:7999/api/ibkr/trades?limit=20"
```

Expected behavior:

- `ibkr/status` eventually reports `connected: true`
- `ibkr/trades` returns recent executions when available

Notes:

- Backend in Docker connects to host `ibgateway` (container network), not `localhost`.
- For `ghcr.io/gnzsnz/ib-gateway`, backend should use socat ports: live `4003`, paper `4004`.
- The IB Gateway settings are persisted in a Docker named volume (`ibgateway-settings`) to avoid host filesystem permission issues on Raspberry Pi.
- If you see `connection refused on ibgateway:4003`, IB Gateway is up but not fully logged in/authorized yet, or login/2FA is incomplete.

##### 3.1) Start all at once with Cloudflare tunnel
If you have your Cloudflare tunnel configured (see next section), start the stack with:

```bash
docker compose up -d --build
```

### 4) Cloudflare DNS delegation

Make sure your domain is delegated to Cloudflare nameservers from your registrar.
This nameserver switch is a registrar-level step and is not managed by Terraform in this repo.

### 5) Provision tunnel + DNS with Terraform

From `infra/`:

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your Cloudflare token/account values

terraform init
terraform plan
terraform apply
```

Then fetch the tunnel token:

```bash
terraform output -raw tunnel_token
```

### 6) Start cloudflared

From repo root:

```bash
export CLOUDFLARE_TUNNEL_TOKEN="<terraform tunnel_token output>"
docker compose up -d
```

Public hostname defaults to `fintwit.akkerman.ai` (configurable in `infra/terraform.tfvars`).

### 7) Verify

- `https://fintwit.akkerman.ai` serves the frontend
- API calls and stream work through frontend proxy paths (`/api/*`, `/api/stream`)

### Start separately
1. Run the backend using:
```bash
uvicorn app.api.main:app --port 7999 --reload
```
2. Run the frontend using:
```bash
cd frontend
npm install
npm run dev
```

### Backfill Sentiment For Existing Tweets
Sentiment is computed for newly ingested tweets in the stream worker. To classify
older tweets already stored in the database (main post and quoted post sentiment), run:

```bash
python -m app.runtime.backfill_sentiment
```

Useful options:

```bash
# Preview without writing changes
python -m app.runtime.backfill_sentiment --dry-run

# Process at most 200 tweets in batches of 50
python -m app.runtime.backfill_sentiment --limit 200 --batch-size 50

# Recompute sentiment even when tweets already have values
python -m app.runtime.backfill_sentiment --include-existing
```

### Optional: Reddit API Credentials
The `/api/reddit/wsb` service uses an `asyncpraw` client first (legacy-style)
to avoid Reddit anti-bot blocks, with HTTP fallback when credentials are missing.

Set one of these credential sets in your environment for more reliable Reddit access:

```bash
# Modern names
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=fintwit-web

# Legacy fintwit-bot compatible names
REDDIT_PERSONAL_USE=...
REDDIT_SECRET=...
REDDIT_APP_NAME=fintwit-web

# Optional (only if your Reddit app config needs user auth)
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
```

## Table of Contents 🗂

- [Key Features](#key-features)
- [Documentation](#documentation)
- [Installation](#installation)
- [Usage](#usage)
- [Citation](#citation)
- [Contributing](#contributing)
- [License](#license)

## Key Features 🔑

This section is optional. If your project has a lot of features, consider adding a list of key features here.

## Documentation

- [Documentation Index](docs/README.md)
- [Migration Status](docs/migration-status.md)
- [API and Frontend Coverage Matrix](docs/api-frontend-coverage.md)
- [Frontend Integration Map](docs/frontend-integration-map.md)
- [Cloudflare Terraform Notes](infra/README.md)

## Installation ⚙️
<!-- Adjust the link of the second command to your own repo -->

The required packages to run this code can be found in the requirements.txt file. To run this file, execute the following code block after cloning the repository:

```bash
pip install -r requirements.txt
```

or

```bash
pip install git+https://github.com/StephanAkkerman/template.git
```

## Usage ⌨️

## Citation ✍️
<!-- Be sure to adjust everything here so it matches your name and repo -->
If you use this project in your research, please cite as follows:

```bibtex
@misc{project_name,
  author  = {Stephan Akkerman},
  title   = {Project Name},
  year    = {2024},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/StephanAkkerman/template}}
}
```

## Contributing 🛠
<!-- Be sure to adjust the repo name here for both the URL and GitHub link -->
Contributions are welcome! If you have a feature request, bug report, or proposal for code refactoring, please feel free to open an issue on GitHub. We appreciate your help in improving this project.\
![https://github.com/StephanAkkerman/template/graphs/contributors](https://contributors-img.firebaseapp.com/image?repo=StephanAkkerman/template)

## License 📜

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
