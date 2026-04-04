import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.runtime import streamer


class DummyTweet:
    def __init__(self, payload: dict, is_update: bool = False):
        self._payload = payload
        self.is_update = is_update

    def to_dict(self) -> dict:
        return dict(self._payload)


def make_client_class(tweet: DummyTweet):
    class DummyXTimelineClient:
        instances = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.stream_calls = []
            DummyXTimelineClient.instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, **kwargs):
            self.stream_calls.append(kwargs)

            async def gen():
                yield tweet
                await asyncio.Future()

            return gen()

    return DummyXTimelineClient


@pytest.mark.asyncio
async def test_run_stream_new_tweet_upserts_and_broadcasts(tmp_path, monkeypatch):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 123,
            "text": "Watching $AAPL",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "likes": 10,
            "replies": 1,
            "views": 100,
            "retweets": 2,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published = []
    published_event = asyncio.Event()

    async def _publish(item):
        published.append(item)
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols", return_value=(["AAPL"], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[{"symbol": "AAPL"}])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    repo.upsert_many.assert_awaited_once()
    repo.update_fields.assert_not_awaited()
    mock_enricher.classify.assert_awaited_once_with(["AAPL"])

    persisted = repo.upsert_many.await_args.args[0][0]
    assert isinstance(persisted["created_at"], datetime)
    assert persisted["assets"] == [{"symbol": "AAPL"}]
    assert published[0]["id"] == 123

    instance = client_cls.instances[0]
    assert instance.kwargs["persist_last_id_path"] == str(tmp_path / "last_id.txt")
    assert instance.stream_calls[0]["mode"] == "with_updates"


@pytest.mark.asyncio
async def test_run_stream_update_tweet_updates_metrics_and_broadcasts(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 456,
            "likes": 100.0,
            "replies": 5,
            "views": 1000,
            "retweets": 20,
            "text": "unchanged text",
        },
        is_update=True,
    )
    client_cls = make_client_class(tweet)

    updated_row = {
        "id": 456,
        "likes": 100,
        "replies": 5,
        "views": 1000,
        "retweets": 20,
    }

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=updated_row)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols") as mock_merge_symbols,
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    repo.update_fields.assert_awaited_once_with(
        456,
        {"replies": 5, "likes": 100, "views": 1000, "retweets": 20},
    )
    repo.upsert_many.assert_not_awaited()
    mock_merge_symbols.assert_not_called()
    mock_enricher.classify.assert_not_awaited()
    bc.publish.assert_awaited_once_with(updated_row)
