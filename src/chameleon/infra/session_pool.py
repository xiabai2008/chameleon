"""Session 池：每个 session 绑定独立 UA + cookie jar，域名级复用（方案 5.2）。"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Sequence
from urllib.parse import urlparse

import httpx

from chameleon.anti_detection.identity_faker import IdentityFaker
from chameleon.engines.http_engine import HttpEngine

_DEFAULT_TIMEOUT = 15.0


class SessionPool:
    """管理 N 个 HttpEngine（各绑定唯一 UA 与 cookie jar）。

    - acquire(domain): 按域名轮询分配 session（同域名尽量复用，保持登录态）
    - mark_blocked(engine): 标记被反爬的 session，后续请求轮换到其他 session
    """

    def __init__(self, size: int = 4, *, timeout: float = _DEFAULT_TIMEOUT, ua_pool: Sequence[str] | None = None) -> None:
        self._faker = IdentityFaker(ua_pool=tuple(ua_pool) if ua_pool else None)
        header_sets = self._faker.generate_headers_many(count=max(size, 1))
        self._engines: list[HttpEngine] = [
            HttpEngine(timeout=timeout, client=httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
                http2=True,
                headers={"User-Agent": headers["User-Agent"], "Accept-Encoding": "gzip, deflate, br"},
            ))
            for headers in header_sets
        ]
        self._size = len(self._engines)
        self._blocked: set[int] = set()
        self._rr = itertools.count()
        self._domain_map: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def engine(self, index: int) -> HttpEngine:
        return self._engines[index]

    async def acquire(self, domain: str) -> HttpEngine:
        """获取该域名对应的 session（同域名连续复用同一 session）。"""
        async with self._lock:
            index = self._domain_map.get(domain)
            if index is not None and index not in self._blocked:
                return self._engines[index]
            for offset in range(self._size):
                candidate = (next(self._rr) + offset) % self._size
                if candidate not in self._blocked:
                    self._domain_map[domain] = candidate
                    return self._engines[candidate]
            # 全部被标记：解除所有标记，重新分配
            self._blocked.clear()
            index = next(self._rr) % self._size
            self._domain_map[domain] = index
            return self._engines[index]

    async def mark_blocked(self, engine: HttpEngine) -> None:
        try:
            index = self._engines.index(engine)
        except ValueError:
            return
        async with self._lock:
            self._blocked.add(index)
            # 清除该 session 的 cookie（避免被标记的 session 继续被复用）
            await engine.clear_cookies()

    def clear_blocked(self) -> None:
        self._blocked.clear()

    @staticmethod
    def domain_of(url: str) -> str:
        return urlparse(url).netloc.lower()

    async def close(self) -> None:
        for engine in self._engines:
            await engine.close()
