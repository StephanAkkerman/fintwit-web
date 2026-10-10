"""Read-only MCP server over a fintwit-web deployment's REST API.

Lets an MCP client (Claude Code, Claude Desktop) pull the same data the
dashboard shows, from either a local backend or the public deployment behind
Cloudflare Access. Run it over stdio::

    python -m app.mcp_server

Rather than one hand-written tool per endpoint, the server reads the backend's
OpenAPI schema and exposes two tools: ``list_endpoints`` (the catalogue) and
``get`` (call one of them). New endpoints become available without touching
this file. GET routes are reachable, minus the SSE stream (it never
returns) and ``/api/admin/*`` (the Access allowlist is not market data), plus
the few POST routes that only look data up (``READ_ONLY_POSTS``). A third
tool, ``portfolio``, gathers every portfolio view in one call.

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
# POST only because the frontend sends a batch in the body; they read and
# compute, never write. Every other POST/PATCH/DELETE stays unreachable.
READ_ONLY_POSTS = frozenset(
    {"/api/overview/mention-frequency", "/api/traders/credibility"}
)
# What the `portfolio` tool fetches: the dashboard's /portfolio page.
PORTFOLIO_PATHS = (
    "/api/portfolio/summary",
    "/api/portfolio/positions",
    "/api/portfolio/insights",
    "/api/ibkr/status",
    "/api/ibkr/account",
    "/api/ibkr/positions",
    "/api/ibkr/trades",
)
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


async def _request(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None,
    body: Any = None,
    *,
    method: str = "GET",
) -> Any:
    url = base_url() + path
    try:
        response = await client.request(
            method,
            url,
            params=params,
            json=body,
            headers=request_headers(),
            follow_redirects=False,
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
            f"{method} {path} returned {response.status_code}: {response.text[:500]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise FintwitApiError(
            f"{method} {path} did not return JSON (is FINTWIT_URL pointing at the "
            "dashboard?)"
        ) from exc


def _resolve(schema: dict, spec: dict, depth: int = 3) -> dict:
    """Inline ``$ref``s so a request body's shape is readable on its own."""
    if "$ref" in schema and depth > 0:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = spec.get("components", {}).get("schemas", {}).get(name, {})
    if depth <= 0:
        return schema
    out = {}
    for key, value in schema.items():
        if key == "title":
            continue
        if key == "properties":
            value = {k: _resolve(v, spec, depth - 1) for k, v in value.items()}
        elif key == "items" and isinstance(value, dict):
            value = _resolve(value, spec, depth - 1)
        out[key] = value
    return out


def list_readable_endpoints(spec: dict) -> list[dict]:
    """Summarise the readable routes in an OpenAPI schema: every GET minus the
    excluded ones, plus the READ_ONLY_POSTS lookups with their body shape."""
    endpoints = []
    for path, operations in sorted(spec.get("paths", {}).items()):
        method = "get"
        if path in READ_ONLY_POSTS and "post" in operations:
            method = "post"
        operation = operations.get(method)
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
        if method == "post":
            endpoint["method"] = "POST"
            content = operation.get("requestBody", {}).get("content", {})
            schema = content.get("application/json", {}).get("schema")
            if schema:
                endpoint["body"] = _resolve(schema, spec)
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
    endpoints = list_readable_endpoints(await _request(client, OPENAPI_PATH, None))
    _catalogue[url] = (time.monotonic(), endpoints)
    return endpoints


async def call_endpoint(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> str:
    if not path.startswith("/"):
        path = "/" + path
    if ".." in path or "?" in path:
        raise FintwitApiError("Pass query parameters in `params`, not in the path.")
    endpoints = await fetch_endpoints(client)
    endpoint = match_endpoint(endpoints, path)
    if endpoint is None:
        raise FintwitApiError(
            f"{path} is not a readable endpoint; call list_endpoints for the "
            "available ones."
        )
    method = endpoint.get("method", "GET")
    if method == "GET" and body is not None:
        raise FintwitApiError(f"{path} is a GET endpoint; it takes no body.")
    payload = await _request(
        client, path, params or None, body if method == "POST" else None, method=method
    )
    return truncate(payload)


async def collect_portfolio(client: httpx.AsyncClient) -> str:
    """Every portfolio view in one payload; a view that fails (IBKR not set up,
    a price feed down) carries its error instead of failing the whole call."""
    result: dict[str, Any] = {}
    for path in PORTFOLIO_PATHS:
        key = path.removeprefix("/api/").replace("/", "_").replace("-", "_")
        try:
            result[key] = await _request(client, path, None)
        except FintwitApiError as exc:
            result[key] = {"error": str(exc)}
    return truncate(result)


mcp = MCPServer(
    name="fintwit",
    instructions=(
        "Read-only access to a fintwit-web dashboard: tweets from tracked X "
        "accounts with tickers and sentiment, market data (stocks, crypto, "
        "options, forex), Reddit trends, trader leaderboards and the owner's "
        "portfolio (manual positions and IBKR). For portfolio questions call "
        "portfolio; otherwise call list_endpoints first, then get with one of "
        "its paths."
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
async def get(
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> str:
    """Fetch one endpoint from list_endpoints and return its JSON.

    Parameters
    ----------
    path
        A path from list_endpoints, with any ``{name}`` segment filled in.
    params
        Query parameters, e.g. ``{"limit": 50, "since_hours": 24}``.
    body
        Only for endpoints list_endpoints marks ``"method": "POST"``: the JSON
        body, shaped like their ``body`` schema.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await call_endpoint(client, path, params, body)


@mcp.tool()
async def portfolio() -> str:
    """The owner's whole portfolio in one call: totals and P&L
    (``portfolio_summary``), each position (``portfolio_positions``),
    diversification and per-asset insights (``portfolio_insights``), and the
    Interactive Brokers account, positions and trades when IBKR sync is on.
    Value history over time is at ``/api/portfolio/history`` via get."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await collect_portfolio(client)


if __name__ == "__main__":
    mcp.run()
