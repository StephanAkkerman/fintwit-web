# One definition of "done". `make check` runs exactly the gates CI runs, so a
# green run here means a green run there.
.PHONY: help install check screenshot check-backend check-frontend format test test-backend test-frontend update

help:
	@echo "make install         install backend test deps + frontend deps"
	@echo "make check           run every gate CI runs (lint, format, types, tests, build)"
	@echo "make check-backend   ruff check + ruff format --check + pytest with coverage floor"
	@echo "make check-frontend  tsc --noEmit + vitest + vite build"
	@echo "make test            tests only, no lint or build"
	@echo "make format          apply ruff formatting"
	@echo "make screenshot      capture /portfolio to artifacts/ (ROUTE=/x SCENARIO=empty)"
	@echo "make update          git pull, then rebuild and restart the Docker Compose stack"

install:
	python -m pip install -e ".[test]"
	cd frontend && npm install --no-audit --no-fund

check: check-backend check-frontend

check-backend:
	ruff check .
	ruff format --check .
	python -m pytest --disable-warnings -q --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=71

# `cd` per line: make runs each recipe line in its own shell, and npx needs the
# frontend as its working directory to find tsconfig.json.
check-frontend:
	cd frontend && npx tsc --noEmit
	cd frontend && npm test
	cd frontend && npm run build

format:
	ruff format .

# Renders a route with the API stubbed, so captures do not depend on live market
# data or a running backend. Needs `pip install -e ".[dev]"`.
ROUTE ?= /portfolio
SCENARIO ?= loaded
THEME ?= dark
screenshot:
	python scripts/screenshot_ui.py --route $(ROUTE) --scenario $(SCENARIO) --theme $(THEME)

test: test-backend test-frontend

test-backend:
	python -m pytest --disable-warnings -q

test-frontend:
	cd frontend && npm test

# For a deployed stack (see README's "Deploy with Docker"), not local dev.
# `down` before `up --build` forces a clean restart even when compose.yml,
# .env, or COMPOSE_PROFILES changed; Make already stops at the first failing
# line, so a conflicted `git pull` won't tear down a working deployment.
update:
	git pull
	docker compose down
	docker compose up -d --build
