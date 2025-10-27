# app/runtime/state.py
import asyncio
from collections import deque
from typing import Deque, Iterable

from xclient import Tweet


class TweetStore:
    """In-memory ring buffer with async-safe operations."""

    def __init__(self, capacity: int = 2000):
        self._buf: Deque[Tweet] = deque(maxlen=capacity)
        self._lock = asyncio.Lock()

    async def append(self, t: Tweet) -> None:
        async with self._lock:
            self._buf.append(t)

    async def latest(self, limit: int = 50) -> list[dict]:
        async with self._lock:
            items = list(self._buf)[-limit:][::-1]
        # Serialize for JSON response
        return [t.to_dict() for t in items]

    async def all(self) -> Iterable[Tweet]:
        async with self._lock:
            return list(self._buf)
