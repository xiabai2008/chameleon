"""并发与限速：每域名令牌桶 + 全局并发上限（方案 5.4）。"""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    """令牌桶：capacity 容量，rate 每秒补充。"""

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self.rate = max(rate, 0.01)
        self.capacity = capacity or max(rate, 1)
        self._tokens = self.capacity
        self._updated = time.monotonic()

    async def acquire(self, amount: float = 1.0) -> None:
        while True:
            self._refill()
            if self._tokens >= amount:
                self._tokens -= amount
                return
            wait = (amount - self._tokens) / self.rate
            await asyncio.sleep(min(wait, 1.0))

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._updated = now


class RateLimiter:
    """每域名限速 + 全局并发控制。"""

    def __init__(self, per_domain_qps: float = 2.0, max_concurrent: int = 8) -> None:
        self.per_domain_qps = per_domain_qps
        self._buckets: dict[str, TokenBucket] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()

    async def acquire(self, domain: str) -> None:
        async with self._lock:
            bucket = self._buckets.get(domain)
            if bucket is None:
                bucket = TokenBucket(self.per_domain_qps)
                self._buckets[domain] = bucket
        await bucket.acquire()

    async def __aenter__(self) -> RateLimiter:
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *args: object) -> None:
        self._semaphore.release()
