import io
import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.infra.db import init_db
from app.infra.repos import TweetRepo
from app.runtime.scrape_tweets import (
    compile_filters,
    iter_matching_tweets,
    split_quoted,
    text_matches,
    write_records,
)

POSITIVE = [
    "$AAPL 350 C 11/06/2026 $1.2M 4.37avg",
    "$RIOT 22 C 10/30/2026  for $1.3M",
    "$MSTR\n 172.5 Call (10/23) - $3.9M @ 5.27",
    "$LITE\n 1150 Call (1/15/27) - $30M @ 139.92",
    "$STLA - $675K Call buyer",
    "$1200 calls on $MU are $7",
    "Some flow on $IBIT 10/16 44c today",
    "HUGE $SPY bullish flow for $22.2M on the 825 call strike for 9/30exp",
    "Large $RIOT call buyers coming in here",
]
NEGATIVE = [
    "$AAPL is looking bullish! Great earnings report.",
    "Call me when $TSLA hits 300",
    "Meeting on 10/2 about the 5 C-suite hires",
    "$BTC up 3% today, 24/7 market",
]


@pytest.mark.parametrize("text", POSITIVE)
def test_options_preset_matches(text):
    assert text_matches(text, compile_filters(presets=["options"]))


@pytest.mark.parametrize("text", NEGATIVE)
def test_options_preset_ignores_non_options(text):
    assert not text_matches(text, compile_filters(presets=["options"]))


def test_exclude_and_match_all():
    inc = compile_filters(["aapl", r"\d+ C"])
    exc = compile_filters(["giveaway"])
    assert text_matches("$AAPL 350 C", inc, exc, match_all=True)
    assert not text_matches("$AAPL 350 C giveaway", inc, exc)
    assert not text_matches("$AAPL stock", inc, exc, match_all=True)
    assert text_matches("$AAPL stock", inc)


def test_compile_filters_rejects_bad_input():
    with pytest.raises(ValueError, match="unknown preset"):
        compile_filters(presets=["nope"])
    with pytest.raises(ValueError, match="invalid regex"):
        compile_filters(["("])


def test_write_records_formats():
    rec = [{"id": "1", "text": "a,b", "tickers": ["X"]}]
    buf = io.StringIO()
    write_records(rec, buf, "jsonl")
    assert json.loads(buf.getvalue()) == rec[0]
    buf = io.StringIO()
    write_records(rec, buf, "csv")
    assert buf.getvalue().splitlines()[1] == '1,"a,b","[""X""]"'


@pytest_asyncio.fixture
async def factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await init_db(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _tweet(id_, text):
    return {
        "id": id_,
        "text": text,
        "user_name": "u",
        "user_screen_name": "u",
        "user_img": "",
        "url": f"https://x.com/u/status/{id_}",
        "media": [],
        "tickers": [],
        "hashtags": [],
        "title": "",
        "media_types": [],
        "created_at": None,
    }


@pytest.mark.asyncio
async def test_iter_matching_tweets_dedupes_and_limits(factory):
    repo = TweetRepo(factory)
    for i, text in enumerate(
        [
            "$AAPL 350 C 11/06/2026 $1.2M",
            "$AAPL  350 c 11/06/2026 $1.2M",  # same alert, different spacing/case
            "just a normal tweet",
            "$STLA - $675K Call buyer",
        ]
    ):
        await repo.upsert_many([_tweet(i + 1, text)])
    inc = compile_filters(presets=["options"])

    got = [t async for t in iter_matching_tweets(factory, inc, batch_size=2)]
    assert [t["id"] for t in got] == ["4", "2"]  # newest first, dup dropped

    kept = [
        t async for t in iter_matching_tweets(factory, inc, dedupe=False, batch_size=2)
    ]
    assert len(kept) == 3

    one = [t async for t in iter_matching_tweets(factory, inc, limit=1)]
    assert len(one) == 1


QUOTE_TWEET = "you son of a peach\n\n> [@k](https://twitter.com/k):\n> bought $MU 900 C 12/18/2026"


def test_split_quoted():
    assert split_quoted("plain $AAPL 350 C 11/06") == ("plain $AAPL 350 C 11/06", "")
    own, quoted = split_quoted(QUOTE_TWEET)
    assert own == "you son of a peach"
    assert quoted.startswith("> [@k]") and "900 C" in quoted


@pytest.mark.asyncio
async def test_quoted_text_is_not_matched_by_default(factory):
    repo = TweetRepo(factory)
    await repo.upsert_many(
        [
            _tweet(1, QUOTE_TWEET),
            _tweet(2, "$AAPL 350 C 11/06/2026\n\n> [@k](https://x.com/k):\n> nice"),
        ]
    )
    inc = compile_filters(presets=["options"])

    got = [t async for t in iter_matching_tweets(factory, inc)]
    assert [t["id"] for t in got] == ["2"]
    assert got[0]["text"] == "$AAPL 350 C 11/06/2026"
    assert "nice" in got[0]["quoted_text"]

    both = [t async for t in iter_matching_tweets(factory, inc, include_quoted=True)]
    assert {t["id"] for t in both} == {"1", "2"}
