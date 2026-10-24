"""Small in-memory limit so one chat cannot flood the bot."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        bucket = self._events[key]
        while bucket and moment - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.max_events:
            return False
        bucket.append(moment)
        return True
