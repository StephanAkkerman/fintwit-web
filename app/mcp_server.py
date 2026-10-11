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
the few POST routes that only look data up (``READ_ONLY_POSTS``). Three more
tools bundle the calls a common question needs: ``portfolio`` (every
portfolio view), ``holdings_check`` (what is happening around each holding)
and ``ticker`` (everything about one symbol).

Configured through environment variables, read when a tool is called:

- ``FINTWIT_URL``: base URL of the deployment, e.g. ``https://fintwit.example.com``.
  Defaults to a local backend on ``http://127.0.0.1:7999``.
- ``CF_ACCESS_CLIENT_ID`` / ``CF_ACCESS_CLIENT_SECRET``: a Cloudflare Access
  service token (``terraform output -json access_service_tokens`` in ``infra/``).
  Needed only when ``FINTWIT_URL`` is behind Access.
- ``FINTWIT_API_KEY``: sent as ``X-API-Key``, for a backend reached directly
  with ``API_KEY`` set. Not needed through the tunnel, whose nginx adds it.
"""

import asyncio
import json
import os
import re
import time
from typing import Any
from urllib.parse import quote

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


# Bundles fan out to several endpoints per symbol; cap how many run at once so
# a large portfolio doesn't flood a Raspberry Pi backend.
_BUNDLE_CONCURRENCY = 6
# Beyond this the per-holding fan-out gets slow and the answer too long to use.
MAX_HOLDINGS = 30


async def _safe(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
    limiter: asyncio.Semaphore | None = None,
) -> Any:
    """One view of a bundle: its payload, or ``{"error": ...}`` so a failing
    upstream (IBKR not set up, Yahoo down) doesn't sink the whole bundle."""
    try:
        if limiter is None:
            return await _request(client, path, params)
        async with limiter:
            return await _request(client, path, params)
    except FintwitApiError as exc:
        return {"error": str(exc)}


def _earnings_by_symbol(calendar: Any, symbols: set[str]) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    if not isinstance(calendar, dict):
        return found
    for day in calendar.get("days") or []:
        for row in day.get("rows") or []:
            symbol = str(row.get("symbol") or "").upper()
            if symbol in symbols:
                found.setdefault(symbol, []).append({"date": day.get("date"), **row})
    return found


def _latest_point(history: Any) -> Any:
    if isinstance(history, dict) and "points" in history:
        points = history["points"] or []
        return points[-1] if points else None
    return history


async def collect_portfolio(client: httpx.AsyncClient) -> str:
    """Every portfolio view in one payload."""
    views = await asyncio.gather(*(_safe(client, path) for path in PORTFOLIO_PATHS))
    result = {
        path.removeprefix("/api/").replace("/", "_").replace("-", "_"): view
        for path, view in zip(PORTFOLIO_PATHS, views)
    }
    return truncate(result)


async def collect_holdings_check(
    client: httpx.AsyncClient, window_hours: int = 168, earnings_days: int = 14
) -> str:
    """Per holding: the position, tweet mentions/sentiment, Reddit buzz, recent
    news with its sentiment, and earnings inside ``earnings_days``."""
    insights = await _request(client, "/api/portfolio/insights", None)
    positions = [p for p in insights.get("positions") or [] if p.get("symbol")]
    positions.sort(key=lambda p: p.get("market_value") or 0, reverse=True)
    skipped = [p["symbol"] for p in positions[MAX_HOLDINGS:]]
    positions = positions[:MAX_HOLDINGS]
    symbols = [str(p["symbol"]).upper() for p in positions]

    limiter = asyncio.Semaphore(_BUNDLE_CONCURRENCY)

    async def per_symbol(symbol: str) -> dict:
        mentions, reddit, news = await asyncio.gather(
            _safe(
                client,
                "/api/overview/ticker-timeseries",
                {"ticker": symbol, "window_hours": window_hours},
                limiter,
            ),
            _safe(
                client,
                f"/api/reddit/trends/{quote(symbol, safe='')}/history",
                {"days": 7},
                limiter,
            ),
            _safe(
                client, "/api/news/company", {"symbols": symbol, "limit": 3}, limiter
            ),
        )
        if isinstance(mentions, dict) and "summary" in mentions:
            mentions = mentions["summary"]
        return {
            "tweets": mentions,
            "reddit_latest": _latest_point(reddit),
            "news": news,
        }

    calendar, *details = await asyncio.gather(
        _safe(
            client,
            "/api/earnings/calendar",
            {"days": min(max(earnings_days, 1), 14), "limit_per_day": 50},
        ),
        *(per_symbol(symbol) for symbol in symbols),
    )
    earnings = _earnings_by_symbol(calendar, set(symbols))
    earnings_error = calendar.get("error") if isinstance(calendar, dict) else None

    holdings = []
    for position, symbol, detail in zip(positions, symbols, details):
        holdings.append(
            {
                "symbol": symbol,
                "position": position,
                **detail,
                "earnings": (
                    {"error": earnings_error}
                    if earnings_error
                    else earnings.get(symbol, [])
                ),
            }
        )

    result: dict[str, Any] = {
        "source": insights.get("source"),
        "totals": insights.get("totals"),
        "diversification": insights.get("diversification"),
        "window_hours": window_hours,
        "holdings": holdings,
    }
    if skipped:
        result["not_checked"] = skipped
    return truncate(result)


async def collect_ticker(
    client: httpx.AsyncClient, symbol: str, window_hours: int = 168
) -> str:
    """Everything the dashboard knows about one symbol."""
    symbol = symbol.strip().upper().lstrip("$")
    if not symbol or "/" in symbol:
        raise FintwitApiError("Pass a ticker symbol such as NVDA or BTC.")

    views = {
        "mentions": (
            "/api/overview/ticker-timeseries",
            {"ticker": symbol, "window_hours": window_hours},
        ),
        "price_today": ("/api/overview/ticker-price-history", {"ticker": symbol}),
        "news": ("/api/news/company", {"symbols": symbol, "limit": 10}),
        "reddit_history": (
            f"/api/reddit/trends/{quote(symbol, safe='')}/history",
            {"days": 30},
        ),
        "options": ("/api/options/overview", {"symbols": symbol}),
        "gamma_exposure": ("/api/options/gamma-exposure", {"symbol": symbol}),
        "earnings_calendar": (
            "/api/earnings/calendar",
            {"days": 14, "limit_per_day": 50},
        ),
        "portfolio_positions": ("/api/portfolio/positions", {"active_only": True}),
    }
    limiter = asyncio.Semaphore(_BUNDLE_CONCURRENCY)
    payloads = await asyncio.gather(
        *(_safe(client, path, params, limiter) for path, params in views.values())
    )
    result: dict[str, Any] = {"symbol": symbol, **dict(zip(views, payloads))}

    calendar = result.pop("earnings_calendar")
    result["earnings"] = (
        calendar
        if isinstance(calendar, dict) and "error" in calendar
        else _earnings_by_symbol(calendar, {symbol}).get(symbol, [])
    )
    positions = result.pop("portfolio_positions")
    if isinstance(positions, list):
        result["your_position"] = [
            p for p in positions if str(p.get("symbol") or "").upper() == symbol
        ]
    return truncate(result)


mcp = MCPServer(
    name="fintwit",
    instructions=(
        "Read-only access to a fintwit-web dashboard: tweets from tracked X "
        "accounts with tickers and sentiment, market data (stocks, crypto, "
        "options, forex), Reddit trends, trader leaderboards and the owner's "
        "portfolio (manual positions and IBKR). Start with the bundles: "
        "portfolio for holdings and P&L, holdings_check for what is happening "
        "around each holding (news, chatter, earnings), ticker for one symbol. "
        "For anything else call list_endpoints, then get with one of its paths."
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


@mcp.tool()
async def holdings_check(window_hours: int = 168, earnings_days: int = 14) -> str:
    """What is happening around each holding, largest first: the position, tweet
    mentions and sentiment over ``window_hours`` (default 7 days), the latest
    Reddit trend reading, the three newest headlines with their sentiment, and
    any earnings in the next ``earnings_days`` (at most 14). Use it for
    questions like "anything I should worry about in my portfolio?"."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await collect_holdings_check(client, window_hours, earnings_days)


@mcp.tool()
async def ticker(symbol: str, window_hours: int = 168) -> str:
    """Everything about one symbol (e.g. ``NVDA``, ``BTC``): tweet mentions and
    sentiment over time, today's intraday price, news with sentiment, Reddit
    trend history, options overview and gamma exposure, upcoming earnings, and
    your own position in it if you hold it. Parts that don't apply (no options
    on a coin) come back as an ``error`` entry."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        return await collect_ticker(client, symbol, window_hours)


if __name__ == "__main__":
    mcp.run()
