"""Token bucket for the Hooktheory API.

The quota -- 10 requests per 10 seconds -- belongs to the *account*, not to a
user or a request. That means this bucket must be process-global, and must move
to Redis the moment there is more than one worker process. Getting this wrong
does not degrade one user's experience; it 429s everybody.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import deque
from collections.abc import Callable, Mapping


class TokenBucket:
    """Sliding-window limiter with an injectable clock.

    Capacity is deliberately set below the server's real limit, leaving headroom
    for clock skew and for the retry traffic a 429 would otherwise cause.
    """

    def __init__(
        self,
        capacity: int = 8,
        refill_period_s: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], object] | None = None,
    ) -> None:
        self.capacity = capacity
        self.refill_period_s = refill_period_s
        self._clock = clock
        self._sleep = sleep or asyncio.sleep
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._blocked_until: float = 0.0

    def _prune(self, now: float) -> None:
        cutoff = now - self.refill_period_s
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    async def acquire(self) -> None:
        """Block until a request may be sent, then record it."""
        while True:
            async with self._lock:
                now = self._clock()
                self._prune(now)
                wait = 0.0
                if now < self._blocked_until:
                    wait = self._blocked_until - now
                elif len(self._timestamps) >= self.capacity:
                    wait = self._timestamps[0] + self.refill_period_s - now
                if wait <= 0:
                    self._timestamps.append(now)
                    return
            await self._sleep(min(wait, self.refill_period_s))

    def observe(self, headers: Mapping[str, str]) -> None:
        """Resync from the server's own accounting."""
        remaining = _int(headers.get("X-Rate-Limit-Remaining"))
        reset = _float(headers.get("X-Rate-Limit-Reset"))
        limit = _int(headers.get("X-Rate-Limit-Limit"))
        if limit:
            self.capacity = min(self.capacity, max(limit - 2, 1))
        if remaining is not None and remaining <= 0 and reset:
            self._blocked_until = max(self._blocked_until, self._clock() + reset)

    def penalize(self, retry_after_s: float | None, attempt: int) -> float:
        """Record a 429 and return how long to wait before retrying."""
        backoff = retry_after_s if retry_after_s else min(
            self.refill_period_s, 2.0**attempt
        )
        jitter = random.uniform(0, 0.5)
        self._blocked_until = max(
            self._blocked_until, self._clock() + backoff + jitter
        )
        return backoff + jitter


def _int(raw: str | None) -> int | None:
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _float(raw: str | None) -> float | None:
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None
