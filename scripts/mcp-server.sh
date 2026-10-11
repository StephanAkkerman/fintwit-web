#!/bin/bash
# Launches the fintwit MCP server (app/mcp_server.py) over stdio for Claude
# Code; .mcp.json points here. Prefers the project virtualenv the cloud session
# hook creates, so it works whether or not that venv is on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON=python3
if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
fi
exec "$PYTHON" -m app.mcp_server
