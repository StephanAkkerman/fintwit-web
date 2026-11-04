"""Tests for the heartbeat that lets a killed backend leave a trace."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.api.main import app
from app.runtime import backend_health
from app.runtime.backend_health import BackendHealth

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)
HEADERS = {"X-API-Key": "test-api-key"}


class Clock:
    def __init__(self):
        self.now = NOW

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def memory(monkeypatch):
    """Control what the process reports as ``(rss_mb, peak_mb)``."""
    reading = {"value": (1000.0, 1200.0)}
    monkeypatch.setattr(backend_health, "read_memory_mb", lambda: reading["value"])
    return reading


def _health(path, clock):
    return BackendHealth(path, now=clock)


def test_first_run_reports_no_restarts(tmp_path, clock, memory):
    health = _health(tmp_path / "health.json", clock)
    health.start()

    snapshot = health.snapshot()

    assert snapshot["started_at"] == NOW.isoformat()
    assert snapshot["unexpected_restarts_24h"] == 0
    assert snapshot["last_unexpected_restart"] is None
    assert snapshot["peak_memory_mb"] == 1200.0


def test_killed_run_counts_as_unexpected_restart(tmp_path, clock, memory):
    path = tmp_path / "health.json"
    killed = _health(path, clock)
    killed.start()
    memory["value"] = (6600.0, 6650.0)
    clock.advance(minutes=30)
    killed.beat()  # no stop(): this is what SIGKILL looks like on disk

    clock.advance(minutes=1)
    memory["value"] = (900.0, 900.0)
    restarted = _health(path, clock)
    restarted.start()

    snapshot = restarted.snapshot()
    assert snapshot["unexpected_restarts_24h"] == 1
    assert (
        snapshot["last_unexpected_restart"] == (NOW + timedelta(minutes=30)).isoformat()
    )
    assert snapshot["peak_memory_mb"] == 6650.0


def test_clean_shutdown_is_not_a_restart(tmp_path, clock, memory):
    path = tmp_path / "health.json"
    first = _health(path, clock)
    first.start()
    first.stop()

    second = _health(path, clock)
    second.start()

    assert second.snapshot()["unexpected_restarts_24h"] == 0


def test_beat_after_stop_stays_clean(tmp_path, clock, memory):
    """A heartbeat still in its thread must not undo the clean-shutdown mark."""
    path = tmp_path / "health.json"
    first = _health(path, clock)
    first.start()
    first.stop()
    first.beat()

    second = _health(path, clock)
    second.start()

    assert second.snapshot()["unexpected_restarts_24h"] == 0


def test_restarts_older_than_a_day_leave_the_count_and_peak(tmp_path, clock, memory):
    path = tmp_path / "health.json"
    killed = _health(path, clock)
    memory["value"] = (6600.0, 6650.0)
    killed.start()

    clock.advance(minutes=1)
    memory["value"] = (900.0, 900.0)
    restarted = _health(path, clock)
    restarted.start()
    clock.advance(hours=25)

    snapshot = restarted.snapshot()
    assert snapshot["unexpected_restarts_24h"] == 0
    assert snapshot["peak_memory_mb"] == 900.0
    # Still kept as history, so the last one is known beyond the window.
    assert snapshot["last_unexpected_restart"] == NOW.isoformat()


def test_history_past_retention_is_dropped(tmp_path, clock, memory):
    path = tmp_path / "health.json"
    _health(path, clock).start()
    clock.advance(minutes=1)
    _health(path, clock).start()  # one unexpected restart on record

    clock.advance(days=8)
    _health(path, clock).start()  # and the second run was killed too

    restarts = json.loads(path.read_text())["restarts"]
    assert len(restarts) == 1


def test_corrupt_file_starts_fresh(tmp_path, clock, memory):
    path = tmp_path / "health.json"
    path.write_text("{not json")

    health = _health(path, clock)
    health.start()

    assert health.snapshot()["unexpected_restarts_24h"] == 0
    assert json.loads(path.read_text())["run"]["clean_shutdown"] is False


def test_unwritable_path_does_not_stop_the_backend(tmp_path, clock, memory):
    blocker = tmp_path / "file"
    blocker.write_text("")

    health = _health(blocker / "health.json", clock)
    health.start()
    health.beat()
    health.stop()

    assert health.snapshot()["started_at"] == NOW.isoformat()


def test_missing_memory_readings_report_none(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(backend_health, "read_memory_mb", lambda: (None, None))
    health = _health(tmp_path / "health.json", clock)
    health.start()
    health.beat()

    assert health.snapshot()["peak_memory_mb"] is None


def test_read_memory_parses_proc_status(tmp_path, monkeypatch):
    status = tmp_path / "status"
    status.write_text(
        "Name:\tuvicorn\nVmHWM:\t 2097152 kB\nVmRSS:\t 1048576 kB\nThreads:\t75\n"
    )
    monkeypatch.setattr(backend_health, "_PROC_STATUS", status)

    assert backend_health.read_memory_mb() == (1024.0, 2048.0)


def test_read_memory_without_proc_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_health, "_PROC_STATUS", tmp_path / "missing")

    assert backend_health.read_memory_mb() == (None, None)


async def test_status_endpoint_reports_the_snapshot(
    async_client, tmp_path, clock, memory, monkeypatch
):
    health = _health(tmp_path / "health.json", clock)
    health.start()
    monkeypatch.setattr(app.state, "backend_health", health, raising=False)

    response = await async_client.get("/api/backend/status", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["started_at"] == NOW.isoformat()


async def test_status_endpoint_without_a_heartbeat(async_client, monkeypatch):
    monkeypatch.setattr(app.state, "backend_health", None, raising=False)

    response = await async_client.get("/api/backend/status", headers=HEADERS)

    assert response.status_code == 503
