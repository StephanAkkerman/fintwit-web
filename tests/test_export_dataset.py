import gzip
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.infra.db import TweetRow
from app.runtime.export_dataset import export_subscriber_ids, export_tweets


def _row(id: int, **kw) -> TweetRow:
    base = dict(
        id=id,
        text=f"tweet {id}",
        user_name="n",
        user_screen_name="u",
        user_img="",
        url=f"https://x.com/u/status/{id}",
        media=[],
        tickers=[],
        hashtags=[],
        title="",
        media_types=[],
    )
    return TweetRow(**{**base, **kw})


def _read(out_dir) -> list[dict]:
    rows = []
    for path in sorted(out_dir.glob("tweets-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            rows += [json.loads(line) for line in fh]
    return rows


@pytest.mark.asyncio
async def test_export_excludes_subscriber_tweets(db_engine, tmp_path):
    async with async_sessionmaker(db_engine)() as session:
        session.add_all(
            [
                _row(1, is_subscriber_only=False),
                _row(2, is_subscriber_only=None),
                _row(3, is_subscriber_only=True),
                _row(4, quoted_tweet={"is_subscriber_only": True}),
                _row(5, quoted_tweet={"is_subscriber_only": False}),
            ]
        )
        await session.commit()

    stats = await export_tweets(engine=db_engine, out_dir=tmp_path, batch_size=2)

    rows = _read(tmp_path)
    assert [r["id"] for r in rows] == [1, 2, 5]
    assert "is_subscriber_only" not in rows[0]
    assert stats.exported == 3
    assert stats.skipped_subscriber == 1  # id 4; id 3 is filtered in SQL


@pytest.mark.asyncio
async def test_subscriber_ids_covers_own_and_quoted_flags(db_engine, tmp_path):
    async with async_sessionmaker(db_engine)() as session:
        session.add_all(
            [
                _row(1, is_subscriber_only=False),
                _row(2, is_subscriber_only=None),
                _row(3, is_subscriber_only=True),
                _row(4, quoted_tweet={"is_subscriber_only": True}),
                _row(5, quoted_tweet={"is_subscriber_only": False}),
            ]
        )
        await session.commit()
    path = tmp_path / "ids.txt"

    count = await export_subscriber_ids(engine=db_engine, path=path, batch_size=1)

    assert path.read_text().split() == ["3", "4"]
    assert count == 2


@pytest.mark.asyncio
async def test_export_reports_progress_per_batch(db_engine, tmp_path):
    async with async_sessionmaker(db_engine)() as session:
        session.add_all([_row(i) for i in range(1, 6)])
        await session.commit()
    calls = []

    await export_tweets(
        engine=db_engine,
        out_dir=tmp_path,
        batch_size=2,
        on_progress=lambda s, total: calls.append((s.exported, total)),
    )

    assert calls == [(2, 5), (4, 5), (5, 5)]


@pytest.mark.asyncio
async def test_export_shards_and_limit(db_engine, tmp_path):
    async with async_sessionmaker(db_engine)() as session:
        session.add_all([_row(i) for i in range(1, 8)])
        await session.commit()

    stats = await export_tweets(
        engine=db_engine, out_dir=tmp_path, shard_size=3, limit=5
    )

    assert stats.exported == 5
    assert stats.files == 2
    assert len(_read(tmp_path)) == 5
