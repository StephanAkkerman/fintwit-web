#!/bin/bash
# Sets up a Claude Code on the web session so `make check` works out of the box.
#
# Python deps go into a project virtualenv rather than the system interpreter:
# the web image's Python is Debian-managed, and its patched setuptools can't
# build odfpy's legacy setup.py (pulled in via ticker-classifier ->
# financedatabase -> pandas[excel]). A venv gets a stock setuptools.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

VENV="$CLAUDE_PROJECT_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --quiet --upgrade pip setuptools wheel
# `test` is what `make check` needs; `dev` adds uvicorn + Playwright for
# `make screenshot` (Chromium is preinstalled, so no `playwright install`).
# ruff is not a project dependency (CI uses ruff-action), so install it here.
"$VENV/bin/python" -m pip install --quiet -e ".[test,dev]" ruff

# Put the venv first on PATH so `python`, `pytest`, `ruff` and the Makefile
# targets resolve to it for the rest of the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export VIRTUAL_ENV=\"$VENV\"" >> "$CLAUDE_ENV_FILE"
  echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# `npm install` rather than `npm ci`: it reuses an existing node_modules, which
# the cached container state keeps between sessions.
cd frontend
npm install --no-audit --no-fund
