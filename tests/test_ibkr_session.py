"""Tests for telling a logged-out IB Gateway apart from a healthy one."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.main import app
from app.services import ibkr
from app.services.ibkr import IbkrGateway, session_state

NOW = datetime(2026, 10, 23, 15, 30, tzinfo=timezone.utc)
HEADERS = {"X-API-Key": "test-api-key"}


def _state(**overrides):
    kwargs = {
        "socket_connected": True,
        "session_lost_at": None,
        "last_sync": NOW - timedelta(seconds=30),
        "relogin_requested_at": None,
        "stale_after": 180,
        "now": NOW,
    }
    return session_state(**{**kwargs, **overrides})


def test_session_state_ok_while_syncing():
    assert _state() == "ok"


def test_session_state_logged_out_although_socket_is_open():
    assert _state(session_lost_at=NOW - timedelta(minutes=1)) == "logged_out"


def test_session_state_stale_when_sync_stopped():
    assert _state(last_sync=NOW - timedelta(minutes=7)) == "stale"
    assert _state(last_sync=None) == "stale"


def test_session_state_disconnected_without_socket():
    assert _state(socket_connected=False) == "disconnected"


def test_session_state_restarting_until_first_sync_after_relogin():
    requested = NOW - timedelta(minutes=1)
    before = NOW - timedelta(minutes=10)
    assert (
        _state(socket_connected=False, relogin_requested_at=requested, last_sync=before)
        == "restarting"
    )
    # A sync after the request means the new login went through.
    assert (
        _state(relogin_requested_at=requested, last_sync=NOW - timedelta(seconds=5))
        == "ok"
    )
    # Past the 2FA window, an unapproved login is just disconnected again.
    assert (
        _state(
            socket_connected=False,
            relogin_requested_at=NOW - timedelta(minutes=6),
            last_sync=before,
        )
        == "disconnected"
    )


def _bare_gateway() -> IbkrGateway:
    """An IbkrGateway without its ib_insync thread, for event handlers."""
    gateway = object.__new__(IbkrGateway)
    gateway.session_lost_at = None
    gateway.last_error = None
    return gateway


def test_on_error_tracks_session_lost_and_restored():
    gateway = _bare_gateway()

    gateway._on_error(-1, 1100, "Connectivity between IB and TWS has been lost.")
    assert gateway.session_lost_at is not None
    assert "lost its IBKR session" in gateway.last_error

    gateway._on_error(-1, 1102, "Connectivity has been restored - data maintained.")
    assert gateway.session_lost_at is None


def test_on_error_ignores_unrelated_codes():
    gateway = _bare_gateway()
    gateway._on_error(-1, 2104, "Market data farm connection is OK:usfarm")
    assert gateway.session_lost_at is None
    assert gateway.last_error is None


@pytest.mark.asyncio
async def test_get_executions_times_out_instead_of_hanging():
    gateway = _bare_gateway()
    gateway._request_timeout = 0.01
    gateway._ensure_connected = AsyncMock(return_value=True)

    async def _never_answers():
        await asyncio.sleep(10)

    gateway._submit = lambda coro: (coro.close(), _never_answers())[1]

    with pytest.raises(RuntimeError, match="no answer"):
        await gateway.get_executions()


class _StatusGateway:
    def __init__(self, state="logged_out"):
        self._state = state
        self.last_sync = NOW
        self.last_error = "IB Gateway lost its IBKR session"
        self.relogin_requested_at = None

    def state(self):
        return "restarting" if self.relogin_requested_at else self._state


@pytest.fixture
def status_gateway():
    previous = getattr(app.state, "ibkr_gateway", None)
    gateway = _StatusGateway()
    app.state.ibkr_gateway = gateway
    yield gateway
    app.state.ibkr_gateway = previous


@pytest.mark.asyncio
async def test_status_is_not_connected_when_logged_out(
    async_client, status_gateway, monkeypatch
):
    monkeypatch.setenv("IBKR_GATEWAY_CONTROL_URL", "http://ibgateway-control:2375")
    response = await async_client.get("/api/ibkr/status", headers=HEADERS)

    body = response.json()
    assert body["state"] == "logged_out"
    assert body["connected"] is False
    assert body["relogin_available"] is True


@pytest.mark.asyncio
async def test_relogin_needs_control_url(async_client, status_gateway, monkeypatch):
    monkeypatch.delenv("IBKR_GATEWAY_CONTROL_URL", raising=False)
    response = await async_client.post("/api/ibkr/relogin", headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_relogin_restarts_gateway_once(async_client, status_gateway, monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_CONTROL_URL", "http://ibgateway-control:2375")
    with patch(
        "app.api.main.restart_gateway_container", new_callable=AsyncMock
    ) as restart:
        first = await async_client.post("/api/ibkr/relogin", headers=HEADERS)
        second = await async_client.post("/api/ibkr/relogin", headers=HEADERS)

    assert first.status_code == 200
    assert first.json() == {"state": "restarting"}
    assert second.status_code == 429
    restart.assert_awaited_once()


@pytest.mark.asyncio
async def test_relogin_failure_allows_retry(async_client, status_gateway, monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_CONTROL_URL", "http://ibgateway-control:2375")
    with patch(
        "app.api.main.restart_gateway_container",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("refused"),
    ):
        response = await async_client.post("/api/ibkr/relogin", headers=HEADERS)

    assert response.status_code == 502
    assert status_gateway.relogin_requested_at is None


@pytest.mark.asyncio
async def test_restart_gateway_container_calls_only_the_restart_endpoint(monkeypatch):
    monkeypatch.setenv("IBKR_GATEWAY_CONTROL_URL", "http://proxy:2375/")
    seen = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(204)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        ibkr.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(_handler), **kw),
    )
    await ibkr.restart_gateway_container()

    assert seen == [("POST", "/containers/fintwit-ibgateway/restart")]
