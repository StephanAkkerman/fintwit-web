import httpx
import pytest

from app.services import insider_trades_service as svc

_HEAD = """<table width="100%" class="tinytable"><thead><tr>
<th width="31"><h3>X</h3></th>
<th width="108"><h3>Filing&nbsp;Date</h3></th>
<th width="64"><h3>Trade&nbsp;Date</h3></th>
<th width="45"><h3>Ticker</h3></th>
{company_header}<th width="180"><h3>Insider&nbsp;Name</h3></th><th width="100"><h3>Title</h3></th>
<th><h3>Trade&nbsp;Type&nbsp;&nbsp;</h3></th>
<th><h3>Price</h3></th>
<th><h3>Qty</h3></th>
<th><h3>Owned</h3></th>
<th><h3>&Delta;Own</h3></th>
<th><h3>Value</h3></th>
<th><h3>1d</h3></th><th><h3>1w</h3></th><th><h3>1m</h3></th><th><h3>6m</h3></th>
</tr></thead><tbody>
"""


def _row(
    ticker="ACME",
    insider="Doe Jane",
    title="CEO",
    trade="P - Purchase",
    value="+$250,000",
    remarks="",
    traded="2026-10-14",
    delta="+5%",
    company=True,
):
    company_cell = f'<td><a href="/{ticker}">{ticker} Corp.</a></td>' if company else ""
    return (
        '<tr style="background:#edffed">'
        f"<td align=right>{remarks}</td>"
        '<td align=right><div><a href="http://www.sec.gov/Archives/edgar/data/1/2/form4.xml" '
        'title="SEC Form 4" target="_blank">2026-10-16 21:57:56</a></div></td>'
        f"<td align=right><div>{traded}</div></td>"
        f"<td><b> <a href=\"/{ticker}\" onmouseover=\"Tip('<img src=\\'chart.ashx?chart={ticker}\\' "
        f"width=\\'360px\\'>', DELAY, 1)\" onmouseout=\"UnTip()\">{ticker}</a></b></td>"
        f"{company_cell}"
        f'<td><a href="/insider/{insider.replace(" ", "-")}/1951275" title="x">{insider}</a></td>'
        f"<td>{title}</td><td>{trade}</td>"
        "<td align=right>$10.00</td><td align=right>+25,000</td>"
        f"<td align=right>525,000</td><td align=right>{delta}</td>"
        f"<td align=right>{value}</td>"
        "<td align=right></td><td align=right></td><td align=right></td><td align=right></td>"
        "</tr>\n"
    )


def _page(*rows, company=True):
    header = '<th width="190"><h3>Company&nbsp;Name</h3></th>' if company else ""
    return _HEAD.format(company_header=header) + "".join(rows) + "</tbody></table>"


def test_parses_a_purchase_row():
    trades = svc.extract_trades(_page(_row(remarks="DM")))
    assert trades == [
        {
            "filed_at": "2026-10-16 21:57:56",
            "traded": "2026-10-14",
            "ticker": "ACME",
            "company": "ACME Corp.",
            "insider": "Doe Jane",
            "insider_cik": "1951275",
            "title": "CEO",
            "is_officer": True,
            "is_ten_percent_owner": False,
            "side": "buy",
            "trade_label": "P - Purchase",
            "with_option_exercise": False,
            "price": 10.0,
            "shares": 25000.0,
            "owned_after": 525000.0,
            "owned_change_pct": 5.0,
            "new_position": False,
            "value": 250000.0,
            "remarks": ["derivative", "multiple_transactions"],
            "filing_url": "http://www.sec.gov/Archives/edgar/data/1/2/form4.xml",
        }
    ]


def test_one_ticker_screen_without_company_column():
    trades = svc.extract_trades(
        _page(_row(trade="S - Sale+OE", value="-$1,000", company=False), company=False)
    )
    assert trades[0]["company"] is None
    assert trades[0]["side"] == "sell"
    assert trades[0]["with_option_exercise"] is True
    assert trades[0]["value"] == -1000.0


def test_skips_other_codes_and_overflowed_values():
    trades = svc.extract_trades(
        _page(
            _row(trade="F - Tax"),
            _row(value="+$2,147,483,647", delta="New"),
        )
    )
    assert len(trades) == 1
    assert trades[0]["value"] is None
    assert trades[0]["new_position"] is True


def test_missing_table_or_headers_is_none():
    assert svc.extract_trades("<html>maintenance</html>") is None
    assert svc.extract_trades('<table class="tinytable"></table>') is None


def test_summary_ranks_cluster_buys_and_skips_option_sales():
    trades = svc.extract_trades(
        _page(
            _row(ticker="AAA", insider="One", value="+$100,000"),
            _row(ticker="AAA", insider="Two", title="Dir", value="+$50,000"),
            _row(ticker="BBB", insider="Big", title="10%", value="+$9,000,000"),
            _row(ticker="CCC", trade="S - Sale+OE", value="-$5,000,000"),
            _row(ticker="DDD", trade="S - Sale", value="-$700,000"),
        )
    )
    summary = svc.summarize(trades)

    assert [c["ticker"] for c in summary["cluster_buys"]] == ["AAA"]
    assert summary["cluster_buys"][0]["insiders"] == ["One", "Two"]
    assert summary["cluster_buys"][0]["officers"] == ["One"]
    assert summary["cluster_buys"][0]["value"] == 150000.0
    assert [b["ticker"] for b in summary["top_buys"]] == ["BBB", "AAA"]
    assert [s["ticker"] for s in summary["top_sells"]] == ["DDD"]
    assert (summary["buys"], summary["sells"]) == (3, 2)
    assert summary["buy_share_pct"] == pytest.approx(
        9_150_000 / (9_150_000 + 5_700_000) * 100, abs=0.1
    )


@pytest.mark.asyncio
async def test_get_insider_trades_filters_side_and_caches():
    svc._reset_cache_for_tests()
    calls = []

    def handler(request):
        calls.append(dict(request.url.params))
        return httpx.Response(
            200,
            text=_page(
                _row(ticker="AAA"), _row(ticker="BBB", trade="S - Sale", value="-$9")
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sells = await svc.get_insider_trades(client, ticker="aaa", side="sell")
        both = await svc.get_insider_trades(client, ticker="AAA")

    assert len(calls) == 1
    assert calls[0]["s"] == "AAA" and calls[0]["vl"] == "25" and calls[0]["fd"] == "30"
    assert [t["ticker"] for t in sells["trades"]] == ["BBB"]
    assert len(both["trades"]) == 2
    assert sells["summary"]["buys"] == 1
    assert sells["filter"] == {
        "days": 30,
        "min_value": 25000,
        "ticker": "AAA",
        "side": "sell",
    }
    svc._reset_cache_for_tests()


@pytest.mark.asyncio
async def test_get_insider_trades_none_when_unreachable():
    svc._reset_cache_for_tests()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(503))
    ) as client:
        assert await svc.get_insider_trades(client) is None
