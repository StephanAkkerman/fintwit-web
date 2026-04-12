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

### 3) Build and run locally on Pi

```bash
docker compose up -d --build
```

The backend Docker image installs CPU-only PyTorch wheels (`download.pytorch.org/whl/cpu`) to avoid pulling large CUDA runtime packages on Linux hosts.

This stack runs:

- Frontend (Nginx + React build) on `127.0.0.1:3000`
- Backend (FastAPI) on `127.0.0.1:8000`

The frontend container proxies `/api/*` and `/api/stream` to the backend container.

##### 3.1) Start all at once with Cloudflare tunnel
If you have your Cloudflare tunnel configured (see next section), you can start the tunnel and app together with:

```bash
docker compose --profile tunnel up -d --build
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

### 6) Start cloudflared (as Compose profile)

From repo root:

```bash
export CLOUDFLARE_TUNNEL_TOKEN="<terraform tunnel_token output>"
docker compose --profile tunnel up -d
```

Public hostname defaults to `fintwit.akkerman.ai` (configurable in `infra/terraform.tfvars`).

### 7) Verify

- `https://fintwit.akkerman.ai` serves the frontend
- API calls and stream work through frontend proxy paths (`/api/*`, `/api/stream`)

### Start separately
1. Run the backend using:
```bash
uvicorn app.api.main:app --reload
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
