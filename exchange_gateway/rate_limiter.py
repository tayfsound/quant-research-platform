import asyncio
import time


class RateLimiter:
    def __init__(self, max_per_second: int = 10):
        self._tokens = max_per_second
        self._last = time.monotonic()

    async def acquire(self):
        now = time.monotonic()
        self._tokens += (now - self._last) * self._tokens / 1.0
        self._last = now
        if self._tokens < 1:
            await asyncio.sleep(1 - self._tokens)
        self._tokens -= 1
