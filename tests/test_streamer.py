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


@pytest.fixture(autouse=True)
def curl_credentials(tmp_path, monkeypatch):
    """Authenticate via a curl file so run_stream doesn't skip the stream."""
    curl_path = tmp_path / "curl.txt"
    curl_path.write_text("curl 'https://x.com/i/api/graphql/q/HomeLatestTimeline'")
    monkeypatch.delenv("X_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("X_CT0", raising=False)
    monkeypatch.setenv("X_CURL_PATH", str(curl_path))
    return curl_path


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
    assert persisted["is_options_tweet"] is False
    assert persisted["options_context"] is None
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


@pytest.mark.asyncio
async def test_run_stream_classifies_chart_for_symbol_tweet_with_photo(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 789,
            "text": "$ETH chart update",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "media": ["https://example.com/chart.jpg"],
            "media_types": ["photo"],
            "likes": 1,
            "replies": 0,
            "views": 10,
            "retweets": 0,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols", return_value=(["ETH"], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
        patch(
            "app.runtime.streamer.is_chart", new=AsyncMock(return_value=True)
        ) as mock_is_chart,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[{"symbol": "ETH"}])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["has_chart"] is True
    mock_is_chart.assert_awaited_once_with("https://example.com/chart.jpg")


@pytest.mark.asyncio
async def test_run_stream_passes_through_quoted_tweet_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 901,
            "text": "Main post\n\n> quoted",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "media": [
                {"url": "https://example.com/main.jpg", "type": "photo"},
                {"url": "https://example.com/quoted.jpg", "type": "photo"},
            ],
            "media_types": ["photo", "photo"],
            "quoted_tweet": {
                "id": 902,
                "text": "Quoted body",
                "user_name": "Quoted Author",
                "user_screen_name": "quotedauthor",
                "user_img": "https://example.com/quoted-avatar.jpg",
                "url": "https://x.com/quotedauthor/status/902",
                "created_at": "2026-04-04T11:50:00Z",
                "media": [{"url": "https://example.com/quoted.jpg", "type": "photo"}],
                "tickers": ["TSLA"],
                "hashtags": ["EV"],
                "title": "Quoted title",
                "media_types": ["photo"],
                "likes": 3,
                "retweets": 1,
                "replies": 0,
                "views": 44,
            },
            "likes": 3,
            "replies": 0,
            "views": 20,
            "retweets": 1,
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
        patch("app.runtime.streamer.merge_symbols", return_value=([], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
        patch("app.runtime.streamer.is_chart", new=AsyncMock(return_value=False)),
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["quoted_tweet"] is not None
    assert persisted["quoted_tweet"]["id"] == 902
    assert persisted["quoted_tweet"]["user_name"] == "Quoted Author"
    assert persisted["quoted_tweet"]["created_at"] == "2026-04-04T11:50:00Z"
    assert published[0]["quoted_tweet"]["id"] == 902


@pytest.mark.asyncio
async def test_run_stream_marks_options_intent_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 1002,
            "text": "$TSLA AUG 390c up 15%",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "likes": 7,
            "replies": 1,
            "views": 55,
            "retweets": 2,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols", return_value=(["TSLA"], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[{"symbol": "TSLA"}])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["is_options_tweet"] is True
    assert persisted["options_context"] is not None
    assert persisted["options_context"]["classification"] == "OPTIONS"
    assert persisted["options_context"]["side"] == "CALL"


@pytest.mark.asyncio
async def test_run_stream_does_not_enrich_assets_from_hashtags_only(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 1003,
            "text": "#OOTT #Tankers #IranWar",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "likes": 1,
            "replies": 0,
            "views": 10,
            "retweets": 0,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch(
            "app.runtime.streamer.merge_symbols",
            return_value=([], ["OOTT", "TANKERS", "IRANWAR"]),
        ),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[{"symbol": "TANKERS"}])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_enricher.classify.assert_not_awaited()
    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["assets"] == []
    assert persisted["hashtags"] == ["OOTT", "TANKERS", "IRANWAR"]


@pytest.mark.asyncio
async def test_run_stream_extracts_chart_data_when_no_ticker_mentioned(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 1001,
            "text": "Check out this chart",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "media": ["https://example.com/chart.jpg"],
            "media_types": ["photo"],
            "likes": 1,
            "replies": 0,
            "views": 10,
            "retweets": 0,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    extraction = {
        "symbol": "SPY",
        "exchange": "NYSE",
        "timeframe": "1D",
        "price": 682.98,
        "session": "regular",
    }

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols", return_value=([], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
        patch("app.runtime.streamer.is_chart", new=AsyncMock(return_value=True)),
        patch(
            "app.runtime.streamer.extract_chart_data",
            new=AsyncMock(return_value=extraction),
        ) as mock_extract,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["chart_extraction"] == extraction
    mock_extract.assert_awaited_once_with("https://example.com/chart.jpg")


@pytest.mark.asyncio
async def test_run_stream_skips_chart_extraction_when_ticker_mentioned(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XTIMELINE_LAST_ID_PATH", str(tmp_path / "last_id.txt"))

    tweet = DummyTweet(
        {
            "id": 1002,
            "text": "$SPY chart update",
            "tickers": [],
            "hashtags": [],
            "created_at": "2026-04-04T12:00:00+00:00",
            "media": ["https://example.com/chart.jpg"],
            "media_types": ["photo"],
            "likes": 1,
            "replies": 0,
            "views": 10,
            "retweets": 0,
        },
        is_update=False,
    )
    client_cls = make_client_class(tweet)

    repo = MagicMock()
    repo.upsert_many = AsyncMock(return_value=1)
    repo.update_fields = AsyncMock(return_value=None)

    published_event = asyncio.Event()

    async def _publish(_item):
        published_event.set()

    bc = MagicMock()
    bc.publish = AsyncMock(side_effect=_publish)

    with (
        patch("app.runtime.streamer.xclient.XTimelineClient", client_cls),
        patch("app.runtime.streamer.merge_symbols", return_value=(["SPY"], [])),
        patch("app.runtime.streamer.AssetEnricher") as mock_enricher_cls,
        patch("app.runtime.streamer.is_chart", new=AsyncMock(return_value=True)),
        patch(
            "app.runtime.streamer.extract_chart_data", new=AsyncMock()
        ) as mock_extract,
    ):
        mock_enricher = mock_enricher_cls.return_value
        mock_enricher.classify = AsyncMock(return_value=[{"symbol": "SPY"}])

        task = asyncio.create_task(streamer.run_stream(repo, bc))
        await asyncio.wait_for(published_event.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    persisted = repo.upsert_many.await_args.args[0][0]
    assert persisted["has_chart"] is True
    assert persisted["chart_extraction"] is None
    mock_extract.assert_not_awaited()


# ---------------------------------------------------------------------------
# Credentials and status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_stream_without_credentials_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("X_CURL_PATH", str(tmp_path / "missing.txt"))
    client_cls = MagicMock()

    with patch("app.runtime.streamer.xclient.XTimelineClient", client_cls):
        await asyncio.wait_for(
            streamer.run_stream(MagicMock(), MagicMock()), timeout=1.0
        )

    client_cls.assert_not_called()
    client_cls.from_cookies.assert_not_called()
    assert streamer.STREAM_STATUS["state"] == "disabled"


def test_credential_source_prefers_cookies_over_curl(monkeypatch):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CT0", "csrf")
    assert streamer._credential_source() == "cookies"


def test_credential_source_needs_both_cookies(monkeypatch, tmp_path):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CURL_PATH", str(tmp_path / "missing.txt"))
    assert streamer._credential_source() is None


def test_open_client_from_cookies_passes_env(monkeypatch):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CT0", "csrf")
    monkeypatch.setenv("X_TIMELINE_QUERY_ID", "qid")
    client_cls = MagicMock()

    with patch("app.runtime.streamer.xclient.XTimelineClient", client_cls):
        streamer._open_client("cookies", "state/last_id.txt")

    client_cls.from_cookies.assert_called_once_with(
        "tok", "csrf", query_id="qid", persist_last_id_path="state/last_id.txt"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "http_status,state",
    [(200, "ok"), (401, "auth_failed"), (403, "auth_failed"), (429, "error")],
)
async def test_watch_status_mirrors_last_http_status(monkeypatch, http_status, state):
    monkeypatch.setattr(streamer, "STATUS_POLL_INTERVAL_S", 0.01)
    xc = MagicMock(last_status=http_status)

    task = asyncio.create_task(streamer._watch_status(xc, "cookies"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert streamer.STREAM_STATUS["state"] == state
    assert streamer.STREAM_STATUS["source"] == "cookies"
