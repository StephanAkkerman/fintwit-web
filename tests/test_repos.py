import pytest

from tests.conftest import SAMPLE_TWEETS


@pytest.mark.asyncio
async def test_upsert_many_inserts_returns_count(tweet_repo):
    count = await tweet_repo.upsert_many(SAMPLE_TWEETS)
    assert count == len(SAMPLE_TWEETS)


@pytest.mark.asyncio
async def test_upsert_many_empty_list_returns_zero(tweet_repo):
    count = await tweet_repo.upsert_many([])
    assert count == 0


@pytest.mark.asyncio
async def test_upsert_many_updates_text_on_conflict(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[0]])
    updated = {**SAMPLE_TWEETS[0], "text": "Updated text"}
    count = await tweet_repo.upsert_many([updated])
    assert count == 1
    rows = await tweet_repo.latest()
    assert rows[0]["text"] == "Updated text"


@pytest.mark.asyncio
async def test_upsert_many_updates_assets_on_conflict(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[0]])
    new_assets = [{"symbol": "AAPL", "kind": "EQUITY", "financials": None}]
    updated = {**SAMPLE_TWEETS[0], "assets": new_assets}
    await tweet_repo.upsert_many([updated])
    rows = await tweet_repo.latest()
    assert rows[0]["assets"] == new_assets


@pytest.mark.asyncio
async def test_latest_returns_results_ordered_desc_by_id(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.latest()
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_latest_respects_limit(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.latest(limit=2)
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_latest_returns_all_expected_fields(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[0]])
    rows = await tweet_repo.latest()
    row = rows[0]
    expected_keys = {
        "id",
        "text",
        "user_name",
        "user_screen_name",
        "user_img",
        "url",
        "media",
        "tickers",
        "hashtags",
        "title",
        "media_types",
        "assets",
    }
    assert expected_keys.issubset(row.keys())


@pytest.mark.asyncio
async def test_latest_preserves_assets(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[0]])
    rows = await tweet_repo.latest()
    assert rows[0]["assets"] == SAMPLE_TWEETS[0]["assets"]


@pytest.mark.asyncio
async def test_latest_preserves_media_and_tickers(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[1]])
    rows = await tweet_repo.latest()
    assert rows[0]["media"] == SAMPLE_TWEETS[1]["media"]
    assert rows[0]["tickers"] == SAMPLE_TWEETS[1]["tickers"]


@pytest.mark.asyncio
async def test_latest_empty_db_returns_empty_list(tweet_repo):
    rows = await tweet_repo.latest()
    assert rows == []


@pytest.mark.asyncio
async def test_by_id_returns_row_when_present(tweet_repo):
    await tweet_repo.upsert_many([SAMPLE_TWEETS[0]])
    row = await tweet_repo.by_id(1001)
    assert row is not None
    assert row["id"] == 1001


@pytest.mark.asyncio
async def test_update_fields_updates_engagement_without_replacing_content(tweet_repo):
    original = {
        **SAMPLE_TWEETS[0],
        "replies": 1,
        "likes": 10,
        "views": 100,
        "retweets": 2,
    }
    await tweet_repo.upsert_many([original])

    updated = await tweet_repo.update_fields(1001, {"likes": 42, "views": 999})

    assert updated is not None
    assert updated["likes"] == 42
    assert updated["views"] == 999
    assert updated["text"] == original["text"]
    assert updated["tickers"] == original["tickers"]


@pytest.mark.asyncio
async def test_update_fields_returns_none_for_missing_row(tweet_repo):
    updated = await tweet_repo.update_fields(999999, {"likes": 1})
    assert updated is None


@pytest.mark.asyncio
async def test_since_id_excludes_boundary_id(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.since_id(since=1001)
    ids = [r["id"] for r in rows]
    assert 1001 not in ids
    assert 1002 in ids
    assert 1003 in ids


@pytest.mark.asyncio
async def test_since_id_returns_ascending_order(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.since_id(since=1000)
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)


@pytest.mark.asyncio
async def test_since_id_respects_limit(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.since_id(since=1000, limit=1)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_since_id_no_results_when_since_is_max(tweet_repo):
    await tweet_repo.upsert_many(SAMPLE_TWEETS)
    rows = await tweet_repo.since_id(since=9999)
    assert rows == []
