import json

import httpx
import pytest

from app.services import fund_holdings_service as svc

_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _table(*rows):
    body = "".join(
        f"""<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass>
        <cusip>{cusip}</cusip><value>{value}</value>
        <shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
        {f"<putCall>{instrument}</putCall>" if instrument else ""}</infoTable>"""
        for name, cusip, value, shares, instrument in rows
    )
    return f'<informationTable xmlns="{_NS}">{body}</informationTable>'


def test_parse_sums_rows_per_cusip_and_keeps_options_apart():
    positions = svc.parse_information_table(
        _table(
            ("APPLE INC", "037833100", 1000, 10, None),
            ("APPLE INC", "037833100", 500, 5, None),
            ("APPLE INC", "037833100", 300, 3, "Call"),
        ),
        "2026-06-30",
    )
    assert positions[("037833100", None)]["value"] == 1500
    assert positions[("037833100", None)]["shares"] == 15
    assert positions[("037833100", "call")]["value"] == 300


def test_convertible_notes_are_kept_apart():
    table = _table(("BILL HOLDINGS INC", "090043AF7", 9_000_000, 10_000_000, None))
    table = table.replace("<sshPrnamtType>SH<", "<sshPrnamtType>PRN<")
    positions = svc.parse_information_table(table, "2026-06-30")
    assert list(positions) == [("090043AF7", "note")]


def test_values_reported_in_thousands_are_scaled():
    # $892k for 3.7M shares of a $238 stock: the filer reported thousands.
    positions = svc.parse_information_table(
        _table(
            ("AMAZON COM INC", "023135106", 892310, 3743854, None),
            ("ELEVANCE HEALTH", "036752103", 493140, 1275154, None),
        ),
        "2026-06-30",
    )
    assert positions[("023135106", None)]["value"] == 892_310_000


def _pos(cusip, value, shares, instrument=None, issuer=None):
    return {
        (cusip, instrument): {
            "cusip": cusip,
            "issuer": issuer or cusip,
            "instrument": instrument,
            "value": value,
            "shares": shares,
        }
    }


def test_diff_labels_each_change():
    current = {
        **_pos("NEW", 100, 10),
        **_pos("ADD", 300, 30),
        **_pos("CUT", 50, 5),
        **_pos("SAME", 550, 100),
    }
    previous = {
        **_pos("ADD", 100, 10),
        **_pos("CUT", 100, 10),
        **_pos("SAME", 500, 101),
        **_pos("GONE", 200, 20),
    }
    rows = {r["cusip"]: r for r in svc.diff_positions(current, previous)}

    assert rows["NEW"]["action"] == "new"
    assert rows["ADD"]["action"] == "added"
    assert rows["ADD"]["shares_change_pct"] == 200.0
    assert rows["ADD"]["value_change"] == 200.0  # 20 more shares at $10
    assert rows["CUT"]["action"] == "reduced"
    assert rows["SAME"]["action"] == "unchanged"  # -1% is noise
    assert rows["GONE"]["action"] == "sold_out"
    assert rows["GONE"]["value_change"] == -200.0
    assert rows["SAME"]["weight_pct"] == 55.0

    summary = svc.summarize_fund(list(rows.values()))
    assert summary["positions"] == 4
    assert [r["cusip"] for r in summary["buys"]] == ["ADD", "NEW"]
    assert [r["cusip"] for r in summary["sells"]] == ["GONE", "CUT"]
    assert summary["top_holdings"][0]["cusip"] == "SAME"
    assert (summary["new_positions"], summary["sold_out"]) == (1, 1)


def test_across_funds_ranks_by_how_many_funds_agree():
    def row(cusip, action, value_change=0.0, value=100.0, instrument=None):
        return {
            "cusip": cusip,
            "issuer": cusip,
            "instrument": instrument,
            "action": action,
            "value_change": value_change,
            "value": value,
        }

    across = svc.summarize_across(
        {
            "A": [
                row("X", "new", 10),
                row("Y", "added", 900),
                row("Z", "new", 5, instrument="call"),
            ],
            "B": [row("X", "added", 20), row("Y", "sold_out", -50, value=0)],
        }
    )
    assert [e["cusip"] for e in across["most_bought"]] == ["X", "Y"]
    assert across["most_bought"][0]["funds"] == ["A", "B"]
    assert across["most_bought"][0]["new_or_exited"] == 1
    assert [e["cusip"] for e in across["most_sold"]] == ["Y"]
    assert [e["cusip"] for e in across["most_held"]] == ["X", "Y"]


def test_latest_filings_skip_amendments():
    submissions = {
        "filings": {
            "recent": {
                "form": ["4", "13F-HR/A", "13F-HR", "13F-HR", "13F-HR"],
                "accessionNumber": ["a", "b", "c", "d", "e"],
                "reportDate": [
                    "",
                    "2026-03-31",
                    "2026-06-30",
                    "2026-03-31",
                    "2025-12-31",
                ],
                "filingDate": [
                    "",
                    "2026-08-20",
                    "2026-08-14",
                    "2026-05-15",
                    "2026-02-14",
                ],
            }
        }
    }
    filings = svc.latest_13f_filings(submissions)
    assert [f["accession"] for f in filings] == ["c", "d"]


def test_extra_funds_from_env(monkeypatch):
    monkeypatch.setenv("FUND_HOLDINGS_EXTRA_CIKS", "1067983, 123, abc")
    tracked = svc.funds()
    assert tracked[-1] == (123, None, None)
    assert len(tracked) == len(svc.FUNDS) + 1


def _sec_handler(seen):
    submissions = {
        "name": "TEST FUND LP",
        "filings": {
            "recent": {
                "form": ["13F-HR", "13F-HR"],
                "accessionNumber": ["0000000001-26-000002", "0000000001-26-000001"],
                "reportDate": ["2026-06-30", "2026-03-31"],
                "filingDate": ["2026-08-14", "2026-05-15"],
            }
        },
    }
    tables = {
        "000000000126000002": _table(
            ("APPLE INC", "037833100", 2_000_000, 10_000, None),
            ("NEWCO", "NEW000000", 500_000, 5_000, None),
        ),
        "000000000126000001": _table(("APPLE INC", "037833100", 900_000, 5_000, None)),
    }

    def handler(request):
        seen.append((request.url.host, request.headers.get("user-agent")))
        url = str(request.url)
        if "submissions" in url:
            return httpx.Response(200, json=submissions)
        accession = url.split("/")[-2]
        if url.endswith("index.json"):
            items = [{"name": "primary_doc.xml"}, {"name": "table.xml"}]
            return httpx.Response(200, json={"directory": {"item": items}})
        if url.endswith("table.xml"):
            return httpx.Response(200, text=tables[accession])
        return httpx.Response(404)

    return handler


@pytest.mark.asyncio
async def test_build_fund_holdings_end_to_end(monkeypatch):
    monkeypatch.setattr(svc, "FUNDS", [(1, "Test Fund", "Jane Doe")])
    monkeypatch.delenv("FUND_HOLDINGS_EXTRA_CIKS", raising=False)
    monkeypatch.setenv("SEC_USER_AGENT", "tester me@example.org")
    seen = []
    asked = []

    async def mapper(cusips):
        asked.extend(cusips)
        return {"037833100": {"ticker": "AAPL", "name": "APPLE INC"}}

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_sec_handler(seen))
    ) as client:
        data = await svc.build_fund_holdings(client, mapper, "2026-10-19")

    fund = data["funds"][0]
    assert fund["name"] == "Test Fund"
    assert fund["report_date"] == "2026-06-30"
    assert fund["prev_report_date"] == "2026-03-31"
    assert fund["stale"] is False
    assert fund["filing_url"].endswith(
        "000000000126000002/0000000001-26-000002-index.html"
    )
    assert [(r["ticker"], r["action"]) for r in fund["buys"]] == [
        ("AAPL", "added"),
        (None, "new"),
    ]
    assert data["most_held"][0]["ticker"] == "AAPL"
    assert sorted(set(asked)) == ["037833100", "NEW000000"]
    assert data["missing"] == []
    assert all(ua == "tester me@example.org" for _, ua in seen)


@pytest.mark.asyncio
async def test_openfigi_lookup_retries_misses_without_us_filter(monkeypatch):
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    bodies = []

    def handler(request):
        jobs = json.loads(request.content)
        bodies.append(jobs)
        if "exchCode" in jobs[0]:
            return httpx.Response(
                200,
                json=[
                    {"data": [{"ticker": "AAPL", "name": "APPLE INC"}]},
                    {"warning": "No identifier found."},
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "data": [
                        {"ticker": "X1", "marketSector": "Corp"},
                        {"ticker": "ASML", "name": "ASML", "marketSector": "Equity"},
                    ]
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found = await svc.openfigi_lookup(client, ["037833100", "N07059210"])

    assert found["037833100"]["ticker"] == "AAPL"
    assert found["N07059210"]["ticker"] == "ASML"
    assert [len(b) for b in bodies] == [2, 1]
    assert [j["idType"] for j in bodies[0]] == ["ID_CUSIP", "ID_CINS"]


@pytest.mark.asyncio
async def test_cusip_mapper_only_asks_for_unknown_cusips(
    cusip_ticker_repo, monkeypatch
):
    await cusip_ticker_repo.upsert_many(
        {"KNOWN0000": {"ticker": "KNW", "name": "Known"}}
    )
    asked = []

    async def fake_lookup(client, cusips):
        asked.extend(cusips)
        return {c: {"ticker": None, "name": None} for c in cusips}

    monkeypatch.setattr(svc, "openfigi_lookup", fake_lookup)
    mapper = svc.make_cusip_mapper(None, cusip_ticker_repo)

    first = await mapper(["KNOWN0000", "MISS00000"])
    second = await mapper(["KNOWN0000", "MISS00000"])

    assert first["KNOWN0000"]["ticker"] == "KNW"
    assert second["MISS00000"] == {"ticker": None, "name": None}
    assert asked == ["MISS00000"]
