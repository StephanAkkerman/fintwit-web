"""Heartbeat on disk, so a backend that gets killed leaves a trace.

SIGKILL (the kernel's out-of-memory killer, for one) gives the process no
chance to log anything: the output simply stops, and Docker's restart policy
hides the rest. So each run records itself in a small JSON file as it goes and
marks itself clean on the way out. A run that finds an unclean record from the
one before knows that run died, and logs and reports it.

Peak memory comes from the kernel's own high-water mark rather than from the
samples, so a spike between two heartbeats still counts. Hosts without
``/proc`` (Windows, macOS) report no memory figures.
"""

import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PATH = "state/backend_health.json"
DEFAULT_INTERVAL = 60
# Heartbeats between memory lines in the log.
_LOG_EVERY = 15
_REPORT_WINDOW = timedelta(hours=24)
_HISTORY_RETENTION = timedelta(days=7)
_PROC_STATUS = Path("/proc/self/status")


def read_memory_mb() -> tuple[float | None, float | None]:
    """Read this process's memory use.

    Returns
    -------
    tuple[float | None, float | None]
        Current and peak resident memory in MB; ``None`` where the host has
        no ``/proc``.
    """
    try:
        status = _PROC_STATUS.read_text(encoding="utf-8")
    except OSError:
        return None, None

    values = {}
    for line in status.splitlines():
        key, _, rest = line.partition(":")
        if key in ("VmRSS", "VmHWM"):
            values[key] = int(rest.split()[0]) / 1024
    return values.get("VmRSS"), values.get("VmHWM")


class BackendHealth:
    """This run's heartbeat, and the unexpected restarts before it.

    Parameters
    ----------
    path : str | os.PathLike
        JSON file holding the heartbeat. It must outlive the container.
    now : Callable[[], datetime]
        Clock, replaced in tests.
    """

    def __init__(
        self,
        path: str | os.PathLike,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._path = Path(path)
        self._now = now
        # A beat runs in a worker thread and can outlast its cancelled task.
        self._lock = threading.Lock()
        self._restarts: list[dict] = []
        self._run: dict = {}
        self._write_failed = False

    def start(self) -> None:
        """Record this run, and any earlier run that never shut down cleanly."""
        with self._lock:
            now = self._now()
            previous = self._load()
            self._restarts = previous.get("restarts") or []
            run = previous.get("run")
            if run and not run.get("clean_shutdown"):
                self._record_restart(run, now)
            cutoff = (now - _HISTORY_RETENTION).isoformat()
            self._restarts = [
                restart
                for restart in self._restarts
                if restart["restarted_at"] >= cutoff
            ]

            rss, peak = read_memory_mb()
            self._run = {
                "started_at": now.isoformat(),
                "last_seen": now.isoformat(),
                "rss_mb": rss,
                "peak_memory_mb": peak,
                "clean_shutdown": False,
            }
            self._save()

    def beat(self) -> None:
        """Refresh the heartbeat."""
        with self._lock:
            rss, peak = read_memory_mb()
            self._run["last_seen"] = self._now().isoformat()
            self._run["rss_mb"] = rss
            self._run["peak_memory_mb"] = peak
            self._save()

    def stop(self) -> None:
        """Mark this run as having shut down on purpose."""
        with self._lock:
            self._run["clean_shutdown"] = True
            self._save()

    def snapshot(self) -> dict:
        """Summarise this run and the last 24 hours for the dashboard.

        Returns
        -------
        dict
            ``started_at``, ``unexpected_restarts_24h``,
            ``last_unexpected_restart`` and ``peak_memory_mb``. The peak covers
            this run and every run that died within the window, which is where
            the figure that explains a kill lives.
        """
        with self._lock:
            cutoff = (self._now() - _REPORT_WINDOW).isoformat()
            recent = [
                restart
                for restart in self._restarts
                if restart["restarted_at"] >= cutoff
            ]
            peaks = [restart.get("peak_memory_mb") for restart in recent]
            peaks.append(self._run.get("peak_memory_mb"))
            known_peaks = [peak for peak in peaks if peak is not None]
            return {
                "started_at": self._run.get("started_at"),
                "unexpected_restarts_24h": len(recent),
                "last_unexpected_restart": (
                    self._restarts[-1]["last_seen"] if self._restarts else None
                ),
                "peak_memory_mb": max(known_peaks) if known_peaks else None,
            }

    def memory_line(self) -> str:
        """Describe current memory use for the log."""
        with self._lock:
            return (
                f"rss={self._run.get('rss_mb')} MB "
                f"peak={self._run.get('peak_memory_mb')} MB"
            )

    def _record_restart(self, run: dict, now: datetime) -> None:
        """Add the dead ``run`` to the history and say so in the log."""
        self._restarts.append(
            {
                "last_seen": run.get("last_seen"),
                "restarted_at": now.isoformat(),
                "peak_memory_mb": run.get("peak_memory_mb"),
            }
        )
        logger.warning(
            "[health] previous run stopped unexpectedly: last seen %s, peak "
            "memory %s MB. No shutdown was logged, so check for an out-of-memory "
            "kill with: sudo dmesg -T | grep -i 'killed process'",
            run.get("last_seen"),
            run.get("peak_memory_mb"),
        )

    def _load(self) -> dict:
        """Read the file, treating a missing or unreadable one as empty."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning("[health] ignoring %s: %r", self._path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        """Replace the file atomically; a kill mid-write must not corrupt it."""
        temporary = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps({"run": self._run, "restarts": self._restarts}),
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
        except OSError as exc:
            # Losing the trace is not worth losing the backend; warn once.
            if not self._write_failed:
                logger.warning("[health] cannot write %s: %r", self._path, exc)
            self._write_failed = True


async def run_heartbeat(
    health: BackendHealth, interval: int = DEFAULT_INTERVAL
) -> None:
    """Refresh ``health`` every ``interval`` seconds.

    Parameters
    ----------
    health : BackendHealth
        The heartbeat to refresh.
    interval : int
        Seconds between heartbeats.
    """
    beats = 0
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(health.beat)
        beats += 1
        if beats % _LOG_EVERY == 0:
            logger.info("[health] memory %s", health.memory_line())
