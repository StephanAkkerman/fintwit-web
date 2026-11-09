from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import Base
from app.infra.repos import IbkrRepo
from app.runtime.ibkr_flex_sync import sync_flex_once
from app.services.ibkr_flex import (
    FlexError,
    close_of,
    fetch_statement,
    flex_account_summary,
    parse_flex_datetime,
    parse_statement,
)

STATEMENT = """<FlexQueryResponse queryName="fintwit" type="AF">
<FlexStatements count="1">
<FlexStatement accountId="U123" fromDate="20261009" toDate="20261106" period="Last30CalendarDays" whenGenerated="20261109;030102">
<EquitySummaryInBase>
<EquitySummaryByReportDateInBase accountId="U123" currency="EUR" reportDate="20261105" cash="2500" stock="9000" options="0" total="11500" />
<EquitySummaryByReportDateInBase accountId="U123" currency="EUR" reportDate="20261106" cash="3159.2" stock="8800" options="40" total="11999.2" />
</EquitySummaryInBase>
<CashReport>
<CashReportCurrency accountId="U123" currency="BASE_SUMMARY" levelOfDetail="BaseCurrency" endingCash="3159.2" />
<CashReportCurrency accountId="U123" currency="USD" levelOfDetail="Currency" endingCash="12.5" />
</CashReport>
<OpenPositions>
<OpenPosition accountId="U123" currency="USD" assetCategory="STK" symbol="AAPL" conid="265598" listingExchange="NASDAQ" multiplier="1" strike="" expiry="" putCall="" reportDate="20261106" position="4" markPrice="268.5" positionValue="1074" costBasisPrice="230.25" fifoPnlUnrealized="153" levelOfDetail="SUMMARY" />
<OpenPosition accountId="U123" currency="USD" assetCategory="STK" symbol="AAPL" conid="265598" listingExchange="NASDAQ" multiplier="1" position="4" markPrice="268.5" costBasisPrice="230.25" levelOfDetail="LOT" />
<OpenPosition accountId="U123" currency="GBP" assetCategory="STK" symbol="ARKG" conid="1" listingExchange="LSEETF" multiplier="1" position="75" markPrice="5.1" positionValue="382.5" costBasisPrice="4.2" fifoPnlUnrealized="67.5" levelOfDetail="SUMMARY" />
<OpenPosition accountId="U123" currency="USD" assetCategory="OPT" symbol="DRAM  261218C00030000" underlyingSymbol="DRAM" conid="2" listingExchange="CBOE" multiplier="100" strike="30" expiry="20261218" putCall="C" position="1" markPrice="0.4" positionValue="40" costBasisPrice="1.1" fifoPnlUnrealized="-70" levelOfDetail="SUMMARY" />
</OpenPositions>
<Trades>
<Trade accountId="U123" currency="USD" assetCategory="STK" symbol="AVGO" buySell="SELL" quantity="-3" tradePrice="331.2" ibCommission="-1.02" dateTime="20261106;101500" ibExecID="0000e0d5.1" levelOfDetail="EXECUTION" />
<Trade accountId="U123" currency="USD" assetCategory="STK" symbol="AMZN" buySell="BUY" quantity="3" tradePrice="244" ibCommission="-1" dateTime="20261103;093205" ibExecID="0000e0d5.2" levelOfDetail="EXECUTION" />
<Trade accountId="U123" currency="USD" assetCategory="STK" symbol="AMZN" buySell="BUY" quantity="3" tradePrice="244" levelOfDetail="ORDER" />
</Trades>
</FlexStatement>
</FlexStatements>
</FlexQueryResponse>"""


@pytest.fixture
async def repo():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield IbkrRepo(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


class _Gateway:
    def __init__(self, state):
        self._state = state

    def state(self):
        return self._state


def test_parse_statement_matches_gateway_rows():
    [statement] = parse_statement(STATEMENT)

    assert statement["account"] == "U123"
    assert statement["to_date"] == date(2026, 11, 6)

    positions = {p["symbol"]: p for p in statement["positions"]}
    assert set(positions) == {"AAPL", "ARKG", "DRAM"}  # LOT row skipped
    assert positions["AAPL"]["avg_cost"] == 230.25
    assert positions["ARKG"]["exchange"] == "LSEETF"
    option = positions["DRAM"]
    # TWS names options by underlying and quotes avg cost per contract.
    assert option["local_symbol"] == "DRAM  261218C00030000"
    assert option["avg_cost"] == pytest.approx(110.0)
    assert (option["expiry"], option["strike"], option["right"]) == (
        "20261218",
        30.0,
        "C",
    )

    trades = {t["exec_id"]: t for t in statement["trades"]}
    assert set(trades) == {"0000e0d5.1", "0000e0d5.2"}  # ORDER row skipped
    sell = trades["0000e0d5.1"]
    assert (sell["side"], sell["quantity"], sell["commission"]) == ("SLD", 3, 1.02)
    # 10:15 Eastern on Nov 6 (EST) is 15:15 UTC.
    assert sell["executed_at"] == datetime(2026, 11, 6, 15, 15, tzinfo=timezone.utc)

    assert [r["report_date"] for r in statement["equity"]] == [
        "2026-11-05",
        "2026-11-06",
    ]
    assert statement["equity"][-1]["total"] == 11999.2


def test_parse_statement_without_nav_uses_cash_report():
    xml = (
        STATEMENT.split("<EquitySummaryInBase>")[0]
        + STATEMENT.split("</EquitySummaryInBase>")[1]
    )
    [statement] = parse_statement(xml)
    [row] = statement["equity"]
    assert row["report_date"] == "2026-11-06"
    assert row["cash"] == 3159.2
    assert row["total"] is None


def test_parse_statement_without_positions_section_is_not_empty_account():
    xml = STATEMENT.split("<OpenPositions>")[0] + STATEMENT.split("</OpenPositions>")[1]
    [statement] = parse_statement(xml)
    assert statement["positions"] is None


def test_parse_statement_rejects_non_statement():
    with pytest.raises(FlexError):
        parse_statement(
            "<FlexStatementResponse><Status>Fail</Status></FlexStatementResponse>"
        )


def test_parse_flex_datetime_accepts_other_formats():
    expected = datetime(2026, 7, 1, 13, 30, tzinfo=timezone.utc)  # EDT
    assert parse_flex_datetime("20260701;093000") == expected
    assert parse_flex_datetime("2026-07-01, 09:30:00") == expected
    assert parse_flex_datetime("") is None


def _transport(replies):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=replies.pop(0))

    return httpx.MockTransport(handler), calls


async def test_fetch_statement_polls_until_ready():
    transport, calls = _transport(
        [
            "<FlexStatementResponse><Status>Success</Status>"
            "<ReferenceCode>42</ReferenceCode>"
            "<Url>https://example.test/GetStatement</Url></FlexStatementResponse>",
            "<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode>"
            "<ErrorMessage>Statement generation in progress</ErrorMessage>"
            "</FlexStatementResponse>",
            STATEMENT,
        ]
    )
    async with httpx.AsyncClient(transport=transport) as client:
        xml = await fetch_statement("tok", "99", client=client, poll_delay=0)

    assert xml == STATEMENT
    assert calls[0].url.params["q"] == "99"
    assert calls[1].url.host == "example.test"
    assert calls[2].url.params["q"] == "42"


async def test_fetch_statement_reports_a_bad_token():
    transport, _ = _transport(
        [
            "<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode>"
            "<ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>"
        ]
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(FlexError, match="1012.*Token has expired"):
            await fetch_statement("tok", "99", client=client, poll_delay=0)


async def test_sync_skips_trades_the_gateway_already_stored(repo):
    await repo.upsert_trades(
        [
            {
                "exec_id": "0000e0d5.1",
                "account": "U123",
                "symbol": "AVGO",
                "sec_type": "STK",
                "currency": "USD",
                "side": "SLD",
                "quantity": 3.0,
                "price": 331.2,
                "commission": 1.02,
                "executed_at": datetime(2026, 11, 6, 15, 15, tzinfo=timezone.utc),
            }
        ]
    )
    await sync_flex_once(repo, STATEMENT)
    trades = await repo.list_trades(min_value=0)
    assert sorted(t["exec_id"] for t in trades) == ["0000e0d5.1", "0000e0d5.2"]


async def test_sync_writes_positions_as_of_the_close_when_gateway_is_down(repo):
    counts = await sync_flex_once(repo, STATEMENT, _Gateway("logged_out"))

    assert counts["positions"] == 3
    assert counts["statement_date"] == date(2026, 11, 6)
    positions = await repo.list_positions()
    assert {p["synced_at"] for p in positions} == {
        close_of(date(2026, 11, 6)).isoformat()
    }
    assert positions[0]["ibkr_market_price"] is not None


async def test_sync_leaves_positions_to_a_syncing_gateway(repo):
    counts = await sync_flex_once(repo, STATEMENT, _Gateway("ok"))
    assert counts["positions"] == 0
    assert await repo.list_positions() == []


async def test_sync_keeps_newer_gateway_positions(repo):
    await repo.sync_positions(
        "U123",
        [
            {
                "account": "U123",
                "symbol": "AAPL",
                "sec_type": "STK",
                "currency": "USD",
                "quantity": 5.0,
                "avg_cost": 230.0,
            }
        ],
        synced_at=close_of(date(2026, 11, 6)) + timedelta(hours=1),
    )
    counts = await sync_flex_once(repo, STATEMENT, _Gateway("logged_out"))
    assert counts["positions"] == 0
    [position] = await repo.list_positions()
    assert position["quantity"] == 5.0


async def test_equity_upsert_keeps_total_when_a_later_statement_lacks_it(repo):
    await sync_flex_once(repo, STATEMENT)
    xml = (
        STATEMENT.split("<EquitySummaryInBase>")[0]
        + STATEMENT.split("</EquitySummaryInBase>")[1]
    )
    await sync_flex_once(
        repo, xml.replace('endingCash="3159.2"', 'endingCash="3000"', 1)
    )

    [latest] = await repo.latest_equity()
    assert (latest["report_date"], latest["cash"], latest["total"]) == (
        "2026-11-06",
        3000.0,
        11999.2,
    )
    assert len(await repo.list_equity(since="2026-11-06")) == 1


def test_flex_account_summary_shapes_like_gateway():
    summary = flex_account_summary(
        [
            {
                "account": "U123",
                "report_date": "2026-11-06",
                "currency": "EUR",
                "cash": 3159.2,
                "stock": 8800.0,
                "options": 40.0,
                "total": 11999.2,
            }
        ]
    )
    assert summary["TotalCashValue"] == {
        "value": 3159.2,
        "currency": "EUR",
        "as_of": "2026-11-06",
        "source": "flex",
    }
    assert summary["NetLiquidation"]["value"] == 11999.2
    assert summary["GrossPositionValue"]["value"] == 8840.0
    assert flex_account_summary([]) == {}
