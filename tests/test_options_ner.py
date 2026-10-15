import pytest

from app.ml.options_ner import (
    AlnumBoundarySplitter,
    build_options_result,
    normalize_right,
    parse_premium,
)
from app.runtime.options_intent import detect_options


def _span(text, start, confidence=0.95):
    return {
        "text": text,
        "start": start,
        "end": start + len(text),
        "confidence": confidence,
    }


def test_splitter_breaks_letters_from_digits_but_keeps_dates_whole():
    tokens = [t for t, _, _ in AlnumBoundarySplitter()("$AAPL 350C 11/06/2026 4.37avg")]
    assert tokens == ["$", "aapl", "350", "c", "11/06/2026", "4.37", "avg"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("$1.2M", 1_200_000.0),
        ("$993K", 993_000.0),
        ("23 million", 23_000_000.0),
        ("$5,400", 5400.0),
    ],
)
def test_parse_premium(text, expected):
    assert parse_premium(text) == expected


def test_single_contract_is_options():
    # "$AAPL 350 C 11/06/2026 $1.2M 4.37avg"
    entities = {
        "ticker": [_span("$AAPL", 0)],
        "strike": [_span("350", 6)],
        "option_type": [_span("C", 10, 0.9)],
        "expiry": [_span("11/06/2026", 12)],
        "premium": [_span("$1.2M", 23)],
        "price": [_span("4.37", 29)],
    }
    result = build_options_result(entities)

    assert result["is_options_tweet"] is True
    ctx = result["options_context"]
    assert ctx["classification"] == "OPTIONS"
    assert ctx["side"] == "CALL"
    assert ctx["confidence"] == "high"
    assert ctx["cashtags"] == ["AAPL"]
    assert ctx["contracts"] == [
        {
            "symbol": "AAPL",
            "right": "CALL",
            "strike": 350.0,
            "expiry": "11/06/2026",
            "notional_usd": 1_200_000.0,
            "price": 4.37,
            "source": "model",
        }
    ]


def test_two_contracts_are_split_at_the_second_ticker():
    # "$AAPL 350C and $TSLA 300P"
    entities = {
        "ticker": [_span("$AAPL", 0), _span("$TSLA", 15)],
        "strike": [_span("350", 6), _span("300", 21)],
        "option_type": [_span("C", 9), _span("P", 24)],
    }
    ctx = build_options_result(entities)["options_context"]

    assert [(c["symbol"], c["strike"], c["right"]) for c in ctx["contracts"]] == [
        ("AAPL", 350.0, "CALL"),
        ("TSLA", 300.0, "PUT"),
    ]
    assert ctx["side"] == "MIXED"


def test_ticker_without_call_or_put_is_not_options():
    result = build_options_result(
        {"ticker": [_span("$NVDA", 0)], "price": [_span("140", 6)]}
    )

    assert result["is_options_tweet"] is False
    assert result["options_context"]["classification"] == "SPOT_OR_OTHER"


def test_lone_call_word_is_not_options():
    result = build_options_result({"option_type": [_span("calls", 10)]})

    assert result["is_options_tweet"] is False


def test_quote_of_an_options_tweet_is_options():
    quoted = {
        "ticker": [_span("$SPY", 0)],
        "strike": [_span("500", 5)],
        "option_type": [_span("puts", 9)],
    }
    result = build_options_result({}, quoted)

    assert result["is_options_tweet"] is True
    ctx = result["options_context"]
    assert ctx["from_quote"] is True
    assert ctx["contracts"][0]["source"] == "model_quoted"
    assert ctx["side"] == "PUT"


class _FakeRecognizer:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def recognize(self, text, quoted_text=None):
        self.calls.append((text, quoted_text))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_detect_options_prefers_the_recognizer():
    expected = build_options_result(
        {
            "ticker": [_span("$SPY", 0)],
            "strike": [_span("500", 5)],
            "option_type": [_span("c", 8)],
        }
    )
    recognizer = _FakeRecognizer(result=expected)

    result = await detect_options("$SPY 500c", "quoted", recognizer)

    assert result == expected
    assert recognizer.calls == [("$SPY 500c", "quoted")]


@pytest.mark.asyncio
async def test_detect_options_falls_back_to_heuristic_when_the_model_fails():
    recognizer = _FakeRecognizer(error=RuntimeError("boom"))

    result = await detect_options("$TSLA AUG 390c up about 15%", None, recognizer)

    assert result["is_options_tweet"] is True
    assert result["options_context"]["contracts"][0]["source"] == "compact"


@pytest.mark.asyncio
async def test_detect_options_heuristic_counts_quoted_options_tweets():
    result = await detect_options("Look at this", "$TSLA AUG 390c up about 15%")

    assert result["is_options_tweet"] is True


@pytest.mark.parametrize(
    "text,expected",
    [
        ("C", "CALL"),
        ("calls", "CALL"),
        ("350P", "PUT"),
        ("Puts", "PUT"),
        ("CASHES", None),
        ("over", None),
        ("long", None),
    ],
)
def test_normalize_right_accepts_only_call_and_put_spellings(text, expected):
    assert normalize_right(text) == expected


def test_stray_option_type_span_is_not_options():
    # "Manchester City OVER 1.5 goals CASHES ... at $0.49" (issue #216)
    result = build_options_result(
        {
            "ticker": [_span("Manchester City", 0)],
            "option_type": [_span("CASHES", 30)],
            "price": [_span("$0.49", 90)],
        }
    )

    assert result["is_options_tweet"] is False


@pytest.mark.asyncio
async def test_detect_options_needs_a_ticker_and_a_contract_detail():
    # "Bitcoin got the call. ... $BTC long." names a call and a ticker, but no
    # strike, expiry, premium or price: not an options trade (issue #216).
    recognizer = _FakeRecognizer(
        result=build_options_result(
            {"option_type": [_span("call", 16)], "ticker": [_span("$BTC", 60)]}
        )
    )

    result = await detect_options(
        "Bitcoin got the call. Follow the squiggle.\n\n@LSDinmycoffee's $BTC long.",
        None,
        recognizer,
        ["BTC"],
    )

    assert result["is_options_tweet"] is False
    assert result["options_context"]["contracts"] == []


@pytest.mark.asyncio
async def test_detect_options_drops_contracts_without_a_ticker():
    recognizer = _FakeRecognizer(
        result=build_options_result(
            {"option_type": [_span("calls", 0)], "premium": [_span("$2M", 6)]}
        )
    )

    result = await detect_options("calls $2M bought", None, recognizer)

    assert result["is_options_tweet"] is False


@pytest.mark.asyncio
async def test_detect_options_keeps_a_strike_written_without_a_cashtag():
    recognizer = _FakeRecognizer(
        result=build_options_result(
            {
                "ticker": [_span("SPY", 0)],
                "strike": [_span("590", 4)],
                "option_type": [_span("P", 7)],
            }
        )
    )

    result = await detect_options("SPY 590P", None, recognizer)

    assert result["is_options_tweet"] is True
    assert result["options_context"]["contracts"][0]["symbol"] == "SPY"


@pytest.mark.asyncio
async def test_detect_options_needs_a_cashtag_when_there_is_no_strike():
    entities = {
        "ticker": [_span("NVDA", 0)],
        "option_type": [_span("calls", 5)],
        "premium": [_span("$1.2M", 11)],
    }

    untagged = await detect_options(
        "NVDA calls $1.2M", None, _FakeRecognizer(result=build_options_result(entities))
    )
    tagged = await detect_options(
        "NVDA calls $1.2M",
        None,
        _FakeRecognizer(result=build_options_result(entities)),
        ["NVDA"],
    )

    assert untagged["is_options_tweet"] is False
    assert tagged["is_options_tweet"] is True
