"""代理池管理：健康检查、评分淘汰、地理区域选择（方案 5.2 ProxyManager）。

支持两种后端：
- memory: 进程内池（单机、测试）
- redis: 分布式池（zset 存分数，set 存区域）
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx

from chameleon.core.config import ProxyConfig
from chameleon.core.exceptions import ProxyUnavailableError
from chameleon.core.models import ProxyInfo
from chameleon.infra.logging import get_logger

log = get_logger("proxy")

ProxyChecker = Callable[[str], Awaitable[tuple[bool, float]]]

DEFAULT_PROBE_URL = "https://www.gstatic.com/generate_204"


async def default_proxy_checker(proxy: str, probe_url: str = DEFAULT_PROBE_URL, timeout_seconds: float = 5.0) -> tuple[bool, float]:
    """探活：请求谷歌 204 端点，返回 (存活, 延迟ms)。"""
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=timeout_seconds, follow_redirects=False) as client:
            started = time.perf_counter()
            resp = await client.get(probe_url)
            elapsed_ms = (time.perf_counter() - started) * 1000
            return resp.status_code < 400, elapsed_ms
    except Exception:
        return False, 0.0


class ProxyManager:
    """代理池。get() 返回加权选择的健康代理，mark_failed/mark_success 更新评分。"""

    def __init__(
        self,
        config: ProxyConfig,
        *,
        checker: ProxyChecker | None = None,
        redis_client: object | None = None,
    ) -> None:
        self.config = config
        self._checker = checker or default_proxy_checker
        self._redis = redis_client
        self._pool: dict[str, ProxyInfo] = {}
        self._lock = asyncio.Lock()
        if config.pool_type == "redis" and redis_client is None:
            from redis.asyncio import Redis

            self._redis = Redis.from_url(config.redis_url)
        self._load_static()

    def _load_static(self) -> None:
        for proxy in self.config.static_list:
            self._pool[proxy] = ProxyInfo(proxy=proxy, score=self.config.default_score)

    async def add(self, proxy: str, region: str | None = None) -> None:
        async with self._lock:
            if proxy in self._pool:
                return
            self._pool[proxy] = ProxyInfo(proxy=proxy, region=region, score=self.config.default_score)
            log.info("proxy_added", proxy=proxy, region=region)

    async def get(self, region: str | None = None) -> str:
        """按健康分数加权随机选择代理；region 过滤。"""
        if self.config.pool_type == "redis":
            return await self._get_redis(region)
        return await self._get_memory(region)

    async def _get_memory(self, region: str | None) -> str:
        async with self._lock:
            candidates = [p for p in self._pool.values() if p.alive and p.score >= self.config.min_score]
            if region:
                candidates = [p for p in candidates if (p.region or "").lower() == region.lower()]
        if not candidates:
            raise ProxyUnavailableError(f"no available proxy (region={region})")
        weights = [max(p.score, 1) for p in candidates]
        chosen = random.choices(candidates, weights=weights, k=1)[0]
        return chosen.proxy

    async def _get_redis(self, region: str | None) -> str:
        from collections.abc import Awaitable
        from typing import cast

        from redis.asyncio import Redis

        r: Redis = self._redis  # type: ignore[assignment]
        if region:
            raw = await cast(Awaitable[set[bytes]], r.smembers(f"chameleon:proxies:{region}"))
        else:
            raw = await cast(Awaitable[set[bytes]], r.smembers("chameleon:proxies"))
        proxies = {p.decode() if isinstance(p, bytes) else p for p in raw}
        if not proxies:
            raise ProxyUnavailableError("redis proxy pool empty")
        scored: list[tuple[str, float]] = []
        for proxy in proxies:
            score = await r.zscore("chameleon:proxy_scores", proxy)
            s = score if score is not None else float(self.config.default_score)
            if s >= self.config.min_score:
                scored.append((proxy, s))
        if not scored:
            raise ProxyUnavailableError("redis proxy pool exhausted")
        return random.choices([p for p, _ in scored], weights=[max(s, 1) for _, s in scored], k=1)[0]

    async def mark_failed(self, proxy: str, delta: int = -10) -> None:
        log.info("proxy_marked_failed", proxy=proxy, delta=delta)
        if self.config.pool_type == "redis":
            from redis.asyncio import Redis

            r: Redis = self._redis  # type: ignore[assignment]
            await r.zincrby("chameleon:proxy_scores", delta, proxy)
            return
        info = self._pool.get(proxy)
        if info is not None:
            info.score = max(info.score + delta, 0)
            if info.score < self.config.min_score:
                info.alive = False

    async def mark_success(self, proxy: str, delta: int = 2) -> None:
        if self.config.pool_type == "redis":
            from redis.asyncio import Redis

            r: Redis = self._redis  # type: ignore[assignment]
            await r.zincrby("chameleon:proxy_scores", delta, proxy)
            return
        info = self._pool.get(proxy)
        if info is not None:
            info.score = min(info.score + delta, 100)
            info.alive = True

    async def health_check_once(self) -> None:
        """全量探活一轮。"""
        async with self._lock:
            proxies = list(self._pool.values())
        for info in proxies:
            alive, latency = await self._checker(info.proxy)
            info.alive = alive
            info.response_time_ms = int(latency)
            info.last_checked = datetime.now(UTC)
            if not alive:
                info.score = max(info.score - 20, 0)
                log.warning("proxy_dead", proxy=info.proxy)

    async def health_check_loop(self, interval: int | None = None) -> None:
        """后台定时探活。"""
        interval = interval or self.config.health_check_interval
        while True:
            await self.health_check_once()
            await asyncio.sleep(interval)

    async def close(self) -> None:
        if self.config.pool_type == "redis" and self._redis is not None:
            from redis.asyncio import Redis

            r: Redis = self._redis  # type: ignore[assignment]
            await r.aclose()
