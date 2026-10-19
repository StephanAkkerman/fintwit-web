from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import congress_trades_service as svc


@pytest.fixture(autouse=True)
def _reset_cache():
    svc._reset_cache_for_tests()
    yield
    svc._reset_cache_for_tests()


def _row(ticker, transaction, politician, filed, traded, **kw):
    return [
        ticker,
        kw.get("asset", f"{ticker} INC - COMMON STOCK"),
        kw.get("asset_type", "ST"),
        transaction,
        kw.get("amount", "$1,001 - $15,000"),
        politician,
        kw.get("chamber", "House"),
        kw.get("party", "R"),
        f"{filed} 00:00:00",
        f"{traded} 00:00:00",
        kw.get("description", "-"),
        kw.get("id", f"House-X-{ticker}-{filed}"),
        kw.get("excess", 1.2345),
        politician,
        "https://www.congress.gov/img/member/x_200.jpg",
        kw.get("bioguide", "X000001"),
    ]


ROWS = [
    _row("FITB", "Purchase", "David Taylor", "2026-10-15", "2026-10-09"),
    _row("PG", "Sale", "David Taylor", "2026-10-15", "2026-10-12", excess=5.9),
    _row("HD", "Sale (Partial)", "Kevin Hern", "2026-10-01", "2026-09-20"),
    _row("HD", "Sale", "Rick Larsen", "2026-10-02", "2026-09-21", party="D"),
    _row(
        "-",
        "Purchase",
        "Nancy Pelosi",
        "2026-10-02",
        "2026-09-08",
        asset="REOF XXX, LLC",
        asset_type="AB",
        amount="$500,001 - $1,000,000",
        party="D",
        excess="-",
        bioguide="P000197",
        description="INVESTMENT IN LLC [OFFICE] AT 225 BUSH STREET",
    ),
]


def _page(rows=ROWS):
    return (
        "<html><script>let userIsAuthenticated = false;\n"
        f"let recentTradesData = {rows!r};\n"
        "let watchlistEligible = [];</script></html>"
    )


def _response(status_code=200, text=""):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    return response


def test_extract_rows_skips_brackets_inside_strings():
    rows = svc.extract_rows(_page())
    assert len(rows) == 5
    assert rows[4][10] == "INVESTMENT IN LLC [OFFICE] AT 225 BUSH STREET"


@pytest.mark.parametrize(
    "html",
    [
        "<html>no data</html>",
        "let recentTradesData = [['A', 'B'",
        "let recentTradesData = {}",
    ],
)
def test_extract_rows_missing_or_broken_is_none(html):
    assert svc.extract_rows(html) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$1,001 - $15,000", (1001, 15000)),
        ("$50,000,001 +", (50_000_001, None)),
        ("Over $50,000,000", (50_000_000, None)),
        (None, (None, None)),
        ("Unknown", (None, None)),
    ],
)
def test_parse_amount(text, expected):
    assert svc.parse_amount(text) == expected


def test_parse_trade_maps_positional_fields():
    trade = svc.parse_trade(ROWS[1])
    assert trade == {
        "id": "House-X-PG-2026-10-15",
        "ticker": "PG",
        "asset": "PG INC - COMMON STOCK",
        "asset_type": "ST",
        "transaction": "sell",
        "transaction_label": "Sale",
        "amount_range": "$1,001 - $15,000",
        "amount_min": 1001,
        "amount_max": 15000,
        "politician": "David Taylor",
        "chamber": "House",
        "party": "R",
        "party_name": "Republican",
        "filed": "2026-10-15",
        "traded": "2026-10-12",
        "description": None,
        "excess_return_pct": 5.9,
        "photo_url": "https://www.congress.gov/img/member/x_200.jpg",
        "bioguide_id": "X000001",
        "website": "https://www.quiverquant.com/congresstrading/politician/David%20Taylor-X000001",
    }


def test_parse_trade_non_stock_and_malformed():
    trade = svc.parse_trade(ROWS[4])
    assert trade["ticker"] is None
    assert trade["excess_return_pct"] is None
    assert trade["transaction"] == "buy"
    assert svc.parse_trade(["too", "short"]) is None


def test_summarize_ranks_by_breadth_then_count():
    trades = [svc.parse_trade(r) for r in ROWS]
    summary = svc.summarize(trades)

    assert summary["trades"] == 5
    assert summary["buys"] == 2
    assert summary["sells"] == 3
    assert summary["most_sold"][0] == {
        "ticker": "HD",
        "trades": 2,
        "politicians": ["Kevin Hern", "Rick Larsen"],
    }
    # Pelosi's LLC stake has no ticker, so it never ranks.
    assert [t["ticker"] for t in summary["most_bought"]] == ["FITB"]
    taylor = summary["politicians"][0]
    assert taylor["name"] == "David Taylor"
    assert (taylor["trades"], taylor["buys"], taylor["sells"]) == (2, 1, 1)
    assert taylor["last_filed"] == "2026-10-15"


@pytest.mark.asyncio
async def test_get_congress_trades_filters_and_caches():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = _response(text=_page())

    result = await svc.get_congress_trades(client)

    # Stocks only by default; newest filing first.
    assert [t["ticker"] for t in result["trades"]] == ["PG", "FITB", "HD", "HD"]
    assert result["as_of"] == "2026-10-15"
    assert result["filter"] == {"politician": None, "stocks_only": True}
    assert result["source"] == "quiver"

    pelosi = await svc.get_congress_trades(
        client, politician="pelosi", stocks_only=False
    )
    assert [t["asset"] for t in pelosi["trades"]] == ["REOF XXX, LLC"]
    assert pelosi["summary"]["politicians"][0]["name"] == "Nancy Pelosi"

    limited = await svc.get_congress_trades(client, limit=1)
    assert len(limited["trades"]) == 1
    assert limited["summary"]["trades"] == 4

    # One page fetch served all three calls.
    assert client.get.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [_response(status_code=429), _response(text="<html>checkpoint</html>")],
)
async def test_get_congress_trades_none_when_page_unusable(response):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.return_value = response
    assert await svc.get_congress_trades(client) is None


@pytest.mark.asyncio
async def test_get_congress_trades_none_on_request_error():
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get.side_effect = httpx.ConnectError("down")
    assert await svc.get_congress_trades(client) is None
