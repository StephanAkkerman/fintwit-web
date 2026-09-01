"""Contract tests tying real API responses to `frontend/src/types.ts`.

The endpoints return plain dicts rather than Pydantic response models, so their
OpenAPI response schema is empty and cannot be diffed against anything. Nothing
else connects the two sides: rename a key in `app/` and the TypeScript keeps
compiling against a field the API no longer sends, and the UI renders `undefined`.

So this drives the real endpoints with only the network mocked, and checks the
JSON that actually comes back against the hand-written types:

* every key in the response is declared in the type (nothing undocumented), and
* every required field of the type is present in the response (nothing missing).

Only the portfolio endpoints are covered so far. Extending this to another
endpoint means driving it through `_get` and adding `_assert_matches` calls;
the parser already handles the subset of TypeScript that `types.ts` uses.
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import main
from app.api.main import app
from app.services import price_history_service

pytestmark = pytest.mark.asyncio

TYPES_FILE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "types.ts"

_FIELD = re.compile(r"^\s*(?P<name>\w+)(?P<optional>\?)?\s*:", re.MULTILINE)
_TYPE_HEAD = re.compile(r"export type (\w+)\s*=\s*")


def _type_bodies(source: str) -> dict[str, str]:
    """Return ``{TypeName: raw body}``, brace-matched to the terminating `;`.

    A regex cannot do this: the body spans nested braces and its fields end in
    semicolons, so any non-greedy match stops at the first field.
    """
    bodies: dict[str, str] = {}

    for head in _TYPE_HEAD.finditer(source):
        index = head.end()
        depth = 0
        while index < len(source):
            char = source[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            elif char == ";" and depth == 0:
                break
            index += 1
        bodies[head.group(1)] = source[head.end() : index]

    return bodies


def _brace_blocks(body: str) -> list[str]:
    """Return the contents of each top-level `{ ... }` in a type body."""
    blocks: list[str] = []
    depth = 0
    start = 0

    for index, char in enumerate(body):
        if char == "{":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                blocks.append(body[start:index])

    return blocks


def _intersected_names(body: str) -> list[str]:
    """Return the bare type names an intersection body refers to.

    `PortfolioAssetFlag & { symbol: string }` -> ["PortfolioAssetFlag"].
    """
    without_blocks = re.sub(r"\{[^{}]*\}", " ", body, flags=re.DOTALL)
    while re.search(r"\{[^{}]*\}", without_blocks, flags=re.DOTALL):
        without_blocks = re.sub(r"\{[^{}]*\}", " ", without_blocks, flags=re.DOTALL)

    return [
        chunk.strip()
        for chunk in without_blocks.split("&")
        if re.fullmatch(r"\w+", chunk.strip())
    ]


def _fields_of(block: str) -> dict[str, bool]:
    """Return ``{field: is_optional}`` for the top level of one brace block.

    Nested object literals are blanked out so their keys are not mistaken for
    fields of the enclosing type.
    """
    depth = 0
    flattened = []

    for char in block:
        if char == "{":
            depth += 1
            flattened.append(" ")
        elif char == "}":
            depth -= 1
            flattened.append(" ")
        else:
            flattened.append(char if depth == 0 else " ")

    return {
        match["name"]: bool(match["optional"])
        for match in _FIELD.finditer("".join(flattened))
    }


def _parse_types() -> dict[str, dict[str, bool]]:
    """Parse `types.ts` into ``{TypeName: {field: is_optional}}``."""
    bodies = _type_bodies(TYPES_FILE.read_text(encoding="utf-8"))
    parsed: dict[str, dict[str, bool]] = {}

    def resolve(name: str, seen: frozenset[str] = frozenset()) -> dict[str, bool]:
        if name in parsed:
            return parsed[name]
        if name in seen or name not in bodies:
            return {}

        fields: dict[str, bool] = {}
        for reference in _intersected_names(bodies[name]):
            fields.update(resolve(reference, seen | {name}))
        for block in _brace_blocks(bodies[name]):
            fields.update(_fields_of(block))

        parsed[name] = fields
        return fields

    for name in bodies:
        resolve(name)

    return parsed


TS_TYPES = _parse_types()


def _assert_matches(payload: dict, type_name: str, *, where: str) -> None:
    declared = TS_TYPES.get(type_name)
    assert declared, f"{type_name} not found in types.ts"

    actual = set(payload)
    undeclared = actual - set(declared)
    required = {name for name, optional in declared.items() if not optional}
    missing = required - actual

    assert not undeclared, (
        f"{where}: API sends {sorted(undeclared)}, absent from {type_name} in "
        "types.ts — add the field there or stop sending it"
    )
    assert not missing, (
        f"{where}: {type_name} requires {sorted(missing)}, which the API did not "
        "send — mark those fields optional in types.ts or start sending them"
    )


# --------------------------------------------------------------------------
# Driving the real endpoints with only the network stubbed
# --------------------------------------------------------------------------

_HOLDINGS = [
    {
        "symbol": "AAPL",
        "quantity": 10.0,
        "avg_cost": 100.0,
        "cost_basis": 1000.0,
        "currency": "USD",
    }
]

_BARS = [
    ("2024-01-02", 100.0, 105.0, 95.0),
    ("2025-06-02", 150.0, 155.0, 148.0),
    ("2026-08-28", 198.0, 200.0, 196.0),
]


def _chart_payload() -> dict:
    from datetime import datetime

    timestamps = [
        int(datetime.fromisoformat(f"{d}T00:00:00+00:00").timestamp())
        for d, *_ in _BARS
    ]
    return {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "close": [b[1] for b in _BARS],
                                "high": [b[2] for b in _BARS],
                                "low": [b[3] for b in _BARS],
                            }
                        ]
                    },
                }
            ]
        }
    }


async def _get(path: str) -> dict:
    """Call a portfolio endpoint for real, with upstream calls stubbed."""
    price_history_service._reset_cache_for_tests()
    app.state.API_KEY = ""

    async def fake_chart(symbol, range_, interval):
        return price_history_service._parse_chart(
            _chart_payload(), intraday=price_history_service._is_intraday(interval)
        )

    async def fake_quote(symbol):
        return {
            "price": 198.0,
            "change_percent": 1.0,
            "website": "https://finance.yahoo.com/quote/AAPL",
        }

    with (
        patch(
            "app.api.main.resolve_holdings",
            new_callable=AsyncMock,
            return_value=("manual", _HOLDINGS),
        ),
        patch.object(price_history_service, "_fetch_chart", fake_chart),
        patch("app.runtime.portfolio_valuation.get_stock_info", fake_quote),
        patch.object(
            main.PORTFOLIO_REPO,
            "list_snapshots",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(path)

    assert response.status_code == 200, response.text
    return response.json()


async def test_types_file_parsed():
    """Guard the parser itself: a silent parse failure would pass everything."""
    assert "PortfolioHistory" in TS_TYPES
    assert TS_TYPES["PortfolioHistoryPoint"]["value"] is False
    assert TS_TYPES["PortfolioHistory"]["totals"] is True
    # PortfolioHighlight intersects PortfolioAssetFlag, so it inherits its fields.
    assert {"symbol", "label", "tone", "code"} <= set(TS_TYPES["PortfolioHighlight"])


async def test_portfolio_history_matches_types():
    body = await _get("/api/portfolio/history?range=1Y")

    _assert_matches(body, "PortfolioHistory", where="GET /api/portfolio/history")
    assert body["points"], "expected at least one point to check"
    _assert_matches(
        body["points"][0],
        "PortfolioHistoryPoint",
        where="GET /api/portfolio/history .points[0]",
    )
    _assert_matches(
        body["totals"],
        "PortfolioTotals",
        where="GET /api/portfolio/history .totals",
    )


async def test_portfolio_insights_matches_types():
    body = await _get("/api/portfolio/insights")

    _assert_matches(body, "PortfolioInsights", where="GET /api/portfolio/insights")
    _assert_matches(
        body["totals"], "PortfolioTotals", where="GET /api/portfolio/insights .totals"
    )

    assert body["positions"], "expected at least one position to check"
    position = body["positions"][0]
    _assert_matches(
        position,
        "PortfolioInsightPosition",
        where="GET /api/portfolio/insights .positions[0]",
    )

    _assert_matches(
        position["stats"],
        "PortfolioAssetStats",
        where="GET /api/portfolio/insights .positions[0].stats",
    )

    assert body["highlights"], "expected at least one highlight to check"
    _assert_matches(
        body["highlights"][0],
        "PortfolioHighlight",
        where="GET /api/portfolio/insights .highlights[0]",
    )
