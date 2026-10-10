"""Read-only MCP server over a fintwit-web deployment's REST API.

Lets an MCP client (Claude Code, Claude Desktop) pull the same data the
dashboard shows, from either a local backend or the public deployment behind
Cloudflare Access. Run it over stdio::

    python -m app.mcp_server

Rather than one hand-written tool per endpoint, the server reads the backend's
OpenAPI schema and exposes two tools: ``list_endpoints`` (the catalogue) and
``get`` (call one of them). New endpoints become available without touching
this file. Only GET routes are reachable, minus the SSE stream (it never
returns) and ``/api/admin/*`` (the Access allowlist is not market data).

Configured through environment variables, read when a tool is called:

- ``FINTWIT_URL``: base URL of the deployment, e.g. ``https://fintwit.example.com``.
  Defaults to a local backend on ``http://127.0.0.1:7999``.
- ``CF_ACCESS_CLIENT_ID`` / ``CF_ACCESS_CLIENT_SECRET``: a Cloudflare Access
  service token (``terraform output -json access_service_tokens`` in ``infra/``).
  Needed only when ``FINTWIT_URL`` is behind Access.
- ``FINTWIT_API_KEY``: sent as ``X-API-Key``, for a backend reached directly
  with ``API_KEY`` set. Not needed through the tunnel, whose nginx adds it.
"""

import json
import os
import re
import time
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_URL = "http://127.0.0.1:7999"
OPENAPI_PATH = "/api/openapi.json"
# Excluded from the catalogue: the SSE stream never completes, and the admin
# routes expose the Access allowlist rather than market data.
_EXCLUDED = (re.compile(r"^/api/stream$"), re.compile(r"^/api/admin(/|$)"))
# Large enough for a full posts page, small enough not to flood the context.
MAX_RESPONSE_CHARS = 60_000
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
# `get` validates every path against the catalogue; caching it saves fetching
# the schema on each call while still picking up a redeploy within minutes.
_CATALOGUE_TTL = 300.0
_catalogue: dict[str, tuple[float, list[dict]]] = {}


class FintwitApiError(ToolError):
    """Raised when the deployment can't be reached or rejects the request.

    A ToolError, so the MCP client sees the message rather than a generic
    failure.
    """


def base_url() -> str:
    return (os.getenv("FINTWIT_URL") or DEFAULT_URL).rstrip("/")


def request_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    client_id = os.getenv("CF_ACCESS_CLIENT_ID")
    client_secret = os.getenv("CF_ACCESS_CLIENT_SECRET")
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret
    api_key = os.getenv("FINTWIT_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _is_access_challenge(response: httpx.Response) -> bool:
    """Cloudflare Access answers an unauthenticated request with a redirect to
    its login page (or a 403 with HTML), never with the API's JSON."""
    if response.is_redirect:
        return "cloudflareaccess.com" in response.headers.get("location", "")
    content_type = response.headers.get("content-type", "")
    return response.status_code in (401, 403) and "text/html" in content_type


async def _request(client: httpx.AsyncClient, path: str, params: dict | None) -> Any:
    url = base_url() + path
    try:
        response = await client.get(
            url, params=params, headers=request_headers(), follow_redirects=False
        )
    except httpx.RequestError as exc:
        raise FintwitApiError(f"Could not reach {url}: {exc!r}") from exc

    if _is_access_challenge(response):
        raise FintwitApiError(
            f"Cloudflare Access blocked the request to {base_url()}. Set "
            "CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET to a service token "
            "the Access application's service-token policy allows (see "
            "infra/README.md)."
        )
    if response.status_code == 401:
        raise FintwitApiError(
            "The backend rejected the API key; set FINTWIT_API_KEY to its API_KEY."
        )
    if response.is_error:
        raise FintwitApiError(
            f"GET {path} returned {response.status_code}: {response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise FintwitApiError(
            f"GET {path} did not return JSON (is FINTWIT_URL pointing at the "
            "dashboard?)"
        ) from exc


def list_get_endpoints(spec: dict) -> list[dict]:
    """Summarise the GET routes in an OpenAPI schema, minus the excluded ones."""
    endpoints = []
    for path, operations in sorted(spec.get("paths", {}).items()):
        operation = operations.get("get")
        if operation is None or any(p.match(path) for p in _EXCLUDED):
            continue
        params = []
        for param in operation.get("parameters", []):
            if param.get("in") not in ("query", "path"):
                continue
            schema = param.get("schema", {})
            entry = {"name": param["name"], "in": param["in"]}
            if param.get("required"):
                entry["required"] = True
            if "default" in schema:
                entry["default"] = schema["default"]
            kind = schema.get("type") or [
                s.get("type") for s in schema.get("anyOf", []) if s.get("type")
            ]
            if kind:
                entry["type"] = kind
            params.append(entry)
        endpoint = {"path": path, "summary": operation.get("summary", "")}
        if operation.get("description"):
            endpoint["description"] = operation["description"].strip()
        if params:
            endpoint["params"] = params
        endpoints.append(endpoint)
    return endpoints


def _template_regex(path: str) -> re.Pattern:
    pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(path))
    return re.compile(f"^{pattern}$")


def match_endpoint(endpoints: list[dict], path: str) -> dict | None:
    """The catalogue entry a concrete path (``/api/reddit/trends/GME/history``)
    belongs to, or None if it isn't an allowed GET route."""
    for endpoint in endpoints:
        if _template_regex(endpoint["path"]).match(path):
            return endpoint
    return None


def truncate(payload: Any, limit: int = MAX_RESPONSE_CHARS) -> str:
    text = json.dumps(payload, default=str, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return (
        text[:limit] + f"\n... [truncated {len(text) - limit} of {len(text)} "
        "characters; narrow the request with a limit or filter parameter]"
    )


async def fetch_endpoints(
    client: httpx.AsyncClient, *, refresh: bool = False
) -> list[dict]:
    url = base_url()
    cached = _catalogue.get(url)
    if cached and not refresh and time.monotonic() - cached[0] < _CATALOGUE_TTL:
        return cached[1]
    endpoints = list_get_endpoints(await _request(client, OPENAPI_PATH, None))
    _catalogue[url] = (time.monotonic(), endpoints)
    return endpoints


async def call_endpoint(
    client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None
) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if ".." in path or "?" in path:
        raise FintwitApiError("Pass query parameters in `params`, not in the path.")
    endpoints = await fetch_endpoints(client)
    if match_endpoint(endpoints, path) is None:
        raise FintwitApiError(
            f"{path} is not a readable endpoint; call list_endpoints for the "
            "available ones."
        )
    return truncate(await _request(client, path, params or None))


mcp = MCPServer(
    name="fintwit",
    instructions=(
        "Read-only access to a fintwit-web dashboard: tweets from tracked X "
        "accounts with tickers and sentiment, market data (stocks, crypto, "
        "options, forex), Reddit trends, trader leaderboards and the owner's "
        "portfolio. Call list_endpoints first, then get with one of its paths."
    ),
)


@mcp.tool()
async def list_endpoints() -> str:
    """List every data endpoint the dashboard exposes, with its parameters.

    Paths containing ``{name}`` take a value in that segment, e.g.
    ``/api/reddit/trends/{symbol}/history`` becomes
    ``/api/reddit/trends/GME/history``.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        endpoints = await fetch_endpoints(client, refresh=True)
    return json.dumps({"base_url": base_url(), "endpoints": endpoints})


@mcp.tool()
async def get(path: str, params: dict[str, Any] | None = None) -> str:
    """Fetch one endpoint from list_endpoints and return its JSON.

    Parameters
    ----------
    path
        A path from list_endpoints, with any ``{name}`` segment filled in.
    params
        Query parameters, e.g. ``{"limit": 50, "since_hours": 24}``.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await call_endpoint(client, path, params)


if __name__ == "__main__":
    mcp.run()
