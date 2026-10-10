"""In-memory token bucket.

The bucket holds up to `capacity` tokens and refills at a steady rate. Each request takes one
token; an empty bucket means "rejected, come back in N seconds". Capacity is the burst that is
allowed at once; the refill rate is the long-run average.

Limits of this implementation, by design:
- One bucket per process. With several server instances each has its own bucket, so the real
  limit becomes N x the configured one. A shared limit needs a shared store (e.g. Redis).
- One bucket for all callers. It protects the LLM quota, not fairness between users: one
  busy caller can use every token. Per-caller buckets would need a trustworthy caller identity.
"""

import time
from collections.abc import Callable

from app.errors import RateLimited


class TokenBucket:
    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,  # injectable for tests
    ) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("capacity must be >= 1 and refill_per_second > 0")
        self._capacity = float(capacity)
        self._refill_per_second = refill_per_second
        self._clock = clock
        self._tokens = float(capacity)  # start full: the first burst is allowed
        self._updated = clock()

    def take(self) -> None:
        """Take one token, or raise RateLimited saying how long until one is available.

        No lock: there is no `await` in here, so on the single-threaded event loop nothing
        else can run between reading and writing `_tokens`. With threads this would need a mutex.
        """
        now = self._clock()
        # Lazy refill: no background timer. Add what accrued since the last call, capped.
        elapsed = now - self._updated
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
        self._updated = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return
        retry_after = (1.0 - self._tokens) / self._refill_per_second
        raise RateLimited("Too many questions right now; try again shortly", retry_after)
