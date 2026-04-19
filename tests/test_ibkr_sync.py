import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.runtime.ibkr_sync import run_ibkr_sync


class _RepoStub:
    def __init__(self):
        self.sync_positions = AsyncMock()
        self.upsert_trades = AsyncMock()


class _GatewayStub:
    def __init__(self, connected=False, connect_result=True):
        self._connected = connected
        self._connect_result = connect_result
        self.connect = AsyncMock(side_effect=self._connect)
        self.get_positions = AsyncMock(return_value=[])
        self.get_executions = AsyncMock(return_value=[])
        self.disconnect_called = False
        self.last_sync = None
        self.last_error = "initial"

    async def _connect(self):
        if self._connect_result:
            self._connected = True
            self.last_error = None
        return self._connect_result

    def is_connected(self):
        return self._connected

    def disconnect(self):
        self.disconnect_called = True


@pytest.mark.asyncio
async def test_run_ibkr_sync_connect_failure_does_not_report_success(monkeypatch):
    repo = _RepoStub()
    gateway = _GatewayStub(connected=False, connect_result=False)
    gateway.last_error = "Connect timeout"

    async def _cancel_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("app.runtime.ibkr_sync.asyncio.sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_ibkr_sync(repo, gateway, interval=60)

    repo.sync_positions.assert_not_awaited()
    repo.upsert_trades.assert_not_awaited()
    assert gateway.last_sync is None


@pytest.mark.asyncio
async def test_run_ibkr_sync_success_sets_last_sync(monkeypatch):
    repo = _RepoStub()
    gateway = _GatewayStub(connected=False, connect_result=True)

    async def _cancel_sleep(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr("app.runtime.ibkr_sync.asyncio.sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_ibkr_sync(repo, gateway, interval=60)

    assert isinstance(gateway.last_sync, datetime)
    gateway.connect.assert_awaited()
