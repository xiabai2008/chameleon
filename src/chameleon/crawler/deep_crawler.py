"""深度爬取引擎：BFS/DFS/Adaptive 策略、去重、增量采集（方案 5.4）。"""

from __future__ import annotations

import heapq
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from chameleon.core.models import FetchRequest, ScrapeResult
from chameleon.core.router import SmartRouter
from chameleon.crawler.rate_limiter import RateLimiter
from chameleon.crawler.robots import RobotsTxt
from chameleon.crawler.url_filter import UrlFilter
from chameleon.infra.logging import get_logger
from chameleon.pipeline.deduplicator import Deduplicator
from chameleon.pipeline.pipeline import Pipeline
from chameleon.utils.url_utils import hostname, normalize_url

log = get_logger("deep_crawler")

_MAX_ATTEMPTS = 2


class DeepCrawler:
    """整站采集：种子 URL 出发，按策略遍历同域页面。

    特性：每域名限速、URL/内容去重、深度限制、robots 遵守、增量 ETag。
    """

    def __init__(
        self,
        router: SmartRouter,
        pipeline: Pipeline,
        *,
        url_filter: UrlFilter | None = None,
        rate_limiter: RateLimiter | None = None,
        robots: RobotsTxt | None = None,
        deduplicator: Deduplicator | None = None,
        respect_robots: bool = True,
        incremental: bool = True,
    ) -> None:
        self.router = router
        self.pipeline = pipeline
        self.url_filter = url_filter or UrlFilter()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.robots = robots or RobotsTxt()
        self.deduplicator = deduplicator
        self.respect_robots = respect_robots
        self.incremental = incremental
        self._etags: dict[str, str] = {}

    def _strategy_queue(self, strategy: str, seed: str) -> Any:
        """BFS（deque）/ DFS（list 栈）/ Adaptive（heapq 优先队列）。"""
        if strategy == "dfs":
            return [(seed, 0)]
        if strategy == "adaptive":
            return []  # heapq 元素 (depth, url)
        return deque([(seed, 0)])

    def _strategy_push(self, strategy: str, queue: Any, url: str, depth: int) -> None:
        if strategy == "dfs":
            queue.append((url, depth))
        elif strategy == "adaptive":
            heapq.heappush(queue, (depth, url))
        else:
            queue.append((url, depth))

    async def crawl(
        self,
        start_url: str,
        *,
        max_pages: int = 50,
        max_depth: int = 3,
        strategy: str = "adaptive",
        output_format: str = "markdown",
    ) -> AsyncIterator[ScrapeResult]:
        """按策略遍历，逐个产出 ScrapeResult（流式）。"""
        seed = normalize_url(start_url)
        self.url_filter.allow_domains = self.url_filter.allow_domains or [hostname(seed)]
        queue: Any = self._strategy_queue(strategy, seed)
        visited: set[str] = set()
        seen_queued: set[str] = set()
        crawled = 0
        attempts: dict[str, int] = {}

        while crawled < max_pages and len(queue) > 0:
            url, depth = self._queue_pop(queue, strategy)
            if url in visited:
                continue
            if depth > max_depth:
                continue
            if not self.url_filter.allow(url):
                continue
            if self.respect_robots and not await self.robots.is_allowed(url):
                log.info("robots_disallowed", url=url)
                visited.add(url)
                continue
            seen_queued.add(url)

            async with self.rate_limiter as limiter:
                await limiter.acquire(hostname(url))
                try:
                    raw = await self.router.fetch(FetchRequest(url=url))
                    result = await self.pipeline.process(raw, output_format=output_format)
                except Exception as exc:
                    attempts[url] = attempts.get(url, 0) + 1
                    log.warning("crawl_failed", url=url, error=str(exc), attempt=attempts[url])
                    if attempts[url] < _MAX_ATTEMPTS:
                        seen_queued.discard(url)
                        self._strategy_push(strategy, queue, url, depth + 1)
                    visited.add(url)
                    continue

            visited.add(url)
            crawled += 1
            if self.incremental:
                self._remember_etag(raw.headers)
            # 链接发现始终执行（即使内容判重，页面链接也要继续遍历）
            for link in result.links:
                if link in visited or link in seen_queued:
                    continue
                if depth + 1 > max_depth:
                    continue
                if not self.url_filter.allow(link):
                    continue
                seen_queued.add(link)
                self._strategy_push(strategy, queue, link, depth + 1)
            # 内容去重仅控制输出
            content_text = result.content.markdown if result.content else ""
            if self.deduplicator is not None and self.deduplicator.add(content_text or url):
                log.info("content_duplicate_skipped", url=url)
                continue
            yield result

    @staticmethod
    def _queue_pop(queue: Any, strategy: str) -> tuple[str, int]:
        if strategy == "dfs":
            dfs_item: tuple[str, int] = queue.pop()
            return dfs_item
        if strategy == "adaptive":
            heap_item: tuple[int, str] = heapq.heappop(queue)
            return heap_item[1], heap_item[0]
        bfs_item: tuple[str, int] = queue.popleft()
        return bfs_item

    def _remember_etag(self, headers: dict[str, str]) -> None:
        etag = headers.get("etag")
        if etag:
            self._etags[etag] = etag

    async def close(self) -> None:
        await self.robots.close()
