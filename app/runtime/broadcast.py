# app/runtime/broadcast.py
import asyncio
from typing import Any


class Broadcaster:
    """Fan-out with per-subscriber queues; drops slow consumers."""

    def __init__(self, max_per_sub: int = 256):
        self._subs: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._max = max_per_sub

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue(self._max)
        async with self._lock:
            self._subs.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subs.discard(q)

    async def publish(self, item: Any) -> None:
        async with self._lock:
            dead = []
            for q in list(self._subs):
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subs.discard(q)
