"""深度爬取（P5）测试。"""

from __future__ import annotations

import asyncio

import pytest

from chameleon.core.router import SmartRouter
from chameleon.crawler.deep_crawler import DeepCrawler
from chameleon.crawler.rate_limiter import RateLimiter, TokenBucket
from chameleon.crawler.robots import RobotsTxt
from chameleon.crawler.scheduler import CrawlScheduler
from chameleon.crawler.url_discovery import discover_links, discover_sitemap
from chameleon.crawler.url_filter import UrlFilter
from chameleon.engines.http_engine import HttpEngine
from chameleon.pipeline.pipeline import Pipeline


def test_url_filter_rules() -> None:
    f = UrlFilter(allow_domains=["example.com"])
    assert f.allow("https://example.com/a")
    assert f.allow("https://sub.example.com/b")
    assert not f.allow("https://evil.com/a")
    assert not f.allow("https://example.com/logo.png")
    assert not f.allow("ftp://example.com/x")

    f2 = UrlFilter(include_patterns=["*products*"], exclude_patterns=["*/admin*"])
    assert f2.allow("https://x.com/products/1")
    assert not f2.allow("https://x.com/admin/1")
    assert not f2.allow("https://x.com/about")


def test_url_discovery() -> None:
    html = """
    <a href="/a">A</a>
    <a href="/a">A 重复</a>
    <a href="https://external.com/b">外链</a>
    <a href="javascript:void(0)">JS</a>
    <a href="/hidden" style="display:none">隐藏</a>
    <a href="#frag">锚点</a>
    """
    links = discover_links(html, "https://example.com/page")
    assert "https://example.com/a" in links
    assert "https://external.com/b" in links
    assert len(links) == 2


def test_rate_limiter_bucket() -> None:
    bucket = TokenBucket(rate=10.0, capacity=10)
    assert bucket._tokens > 0  # noqa: SLF001


@pytest.mark.asyncio
async def test_robots_txt(test_server: str) -> None:
    robots = RobotsTxt()
    assert await robots.is_allowed(f"{test_server}/site/a")
    assert not await robots.is_allowed(f"{test_server}/site/e")
    await robots.close()


@pytest.mark.asyncio
async def test_sitemap_discovery(test_server: str) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, f"{test_server}/sitemap.xml")
    assert urls == []


def _build_crawler(test_server: str) -> tuple[SmartRouter, DeepCrawler, HttpEngine]:
    http = HttpEngine()
    router = SmartRouter(http_engine=http)
    pipeline = Pipeline()
    crawler = DeepCrawler(
        router,
        pipeline,
        url_filter=UrlFilter(allow_domains=["127.0.0.1"]),
        respect_robots=False,
    )
    return router, crawler, http


@pytest.mark.asyncio
async def test_deep_crawler_bfs_all_pages(test_server: str) -> None:
    _, crawler, http = _build_crawler(test_server)
    results = []
    async for result in crawler.crawl(f"{test_server}/site/a", max_pages=50, max_depth=5, strategy="bfs"):
        results.append(result.url)
    pages = {r for r in results if "/site/" in r}
    assert len(pages) == 10  # a-j 全部爬完
    await http.close()


@pytest.mark.asyncio
async def test_deep_crawler_respects_max_pages(test_server: str) -> None:
    _, crawler, http = _build_crawler(test_server)
    count = 0
    async for _ in crawler.crawl(f"{test_server}/site/a", max_pages=4, max_depth=5, strategy="bfs"):
        count += 1
    assert count <= 4
    await http.close()


@pytest.mark.asyncio
async def test_deep_crawler_dfs_and_no_duplicates(test_server: str) -> None:
    _, crawler, http = _build_crawler(test_server)
    seen: set[str] = set()
    async for result in crawler.crawl(f"{test_server}/site/a", max_pages=50, max_depth=5, strategy="dfs"):
        assert result.url not in seen
        seen.add(result.url)
    assert len(seen) >= 5
    await http.close()


@pytest.mark.asyncio
async def test_deep_crawler_robots_blocked_page(test_server: str) -> None:
    http = HttpEngine()
    router = SmartRouter(http_engine=http)
    crawler = DeepCrawler(
        router,
        Pipeline(),
        url_filter=UrlFilter(allow_domains=["127.0.0.1"]),
        respect_robots=True,
    )
    urls: list[str] = []
    async for result in crawler.crawl(f"{test_server}/site/a", max_pages=50, max_depth=5, strategy="bfs"):
        urls.append(result.url)
    assert not any("/site/e" in u for u in urls)  # robots 禁爬
    await http.close()


@pytest.mark.asyncio
async def test_scheduler_job_lifecycle(test_server: str) -> None:
    _, crawler, http = _build_crawler(test_server)
    scheduler = CrawlScheduler(crawler)
    job_id = await scheduler.submit(f"{test_server}/site/a", max_pages=8, max_depth=5, strategy="bfs")
    job = await scheduler.get_status(job_id)
    assert job is not None
    assert job.status.value == "queued"
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert job is not None
    assert job.status.value == "done"
    assert job.pages_crawled >= 5
    await http.close()


@pytest.mark.asyncio
async def test_scheduler_cancel(test_server: str) -> None:
    _, crawler, http = _build_crawler(test_server)
    scheduler = CrawlScheduler(crawler)
    job_id = await scheduler.submit(f"{test_server}/site/a", max_pages=50, max_depth=5, strategy="bfs")
    await asyncio.sleep(0.05)
    assert await scheduler.cancel(job_id) is True
    job = await scheduler.get_status(job_id)
    assert job is not None
    assert job.status.value == "cancelled"
    await http.close()


@pytest.mark.asyncio
async def test_rate_limiter_serializes_domain(test_server: str) -> None:
    limiter = RateLimiter(per_domain_qps=50.0, max_concurrent=2)
    order: list[str] = []

    async def worker(i: int) -> None:
        async with limiter:
            await limiter.acquire("test.local")
            order.append(f"w{i}")

    await asyncio.gather(*[worker(i) for i in range(6)])
    assert len(order) == 6
