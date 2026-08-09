"""scheduler 补强测试（覆盖率 70% → 90%+）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chameleon.core.models import CrawlJob, JobStatus
from chameleon.crawler.scheduler import CrawlScheduler, InMemoryJobStore, RedisJobStore


class _FakeCrawler:
    """可控的假 DeepCrawler。"""

    def __init__(self, *, fail: bool = False, results: list[str] | None = None) -> None:
        self.fail = fail
        self.results = results or ["http://x/1", "http://x/2", "http://x/3"]

    async def crawl(self, url: str, **kwargs: Any) -> Any:
        if self.fail:
            raise RuntimeError("crawler exploded")
        from chameleon.core.exceptions import ScrapeStatus
        from chameleon.core.models import ScrapeMetadata, ScrapeResult

        for u in self.results:
            yield ScrapeResult(
                status=ScrapeStatus.SUCCESS,
                url=u,
                metadata=ScrapeMetadata(url=u, status_code=200),
            )


# ---------- InMemoryJobStore ----------


@pytest.mark.asyncio
async def test_in_memory_store_crud() -> None:
    store = InMemoryJobStore()
    job = CrawlJob(job_id="j1", url="http://x")
    await store.create(job)
    assert await store.get("j1") == job
    assert await store.get("missing") is None

    job.status = JobStatus.RUNNING
    await store.update(job)
    assert (await store.get("j1")).status == JobStatus.RUNNING  # type: ignore[union-attr]

    jobs = await store.list()
    assert len(jobs) == 1


# ---------- RedisJobStore ----------


class _FakeRedis:
    """内存版 redis 客户端（set/get/keys/delete 子集）。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def set(self, key: str, value: str) -> None:
        self._data[key] = value

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def keys(self, pattern: str) -> list[str]:
        prefix = pattern.split("*")[0]
        return [k for k in self._data if k.startswith(prefix)]

    async def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                count += 1
        return count

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_redis_store_crud() -> None:
    fake = _FakeRedis()
    store = RedisJobStore.__new__(RedisJobStore)
    store._redis = fake  # type: ignore[attr-defined]

    job = CrawlJob(job_id="r1", url="http://x", pages_crawled=5)
    await store.create(job)
    got = await store.get("r1")
    assert got is not None and got.url == "http://x" and got.pages_crawled == 5
    assert await store.get("missing") is None

    job.pages_crawled = 7
    await store.update(job)
    assert (await store.get("r1")).pages_crawled == 7  # type: ignore[union-attr]

    listed = await store.list()
    assert len(listed) == 1

    await store.close()


@pytest.mark.asyncio
async def test_redis_store_empty_list() -> None:
    store = RedisJobStore.__new__(RedisJobStore)
    store._redis = _FakeRedis()  # type: ignore[attr-defined]
    assert await store.list() == []


# ---------- CrawlScheduler ----------


@pytest.mark.asyncio
async def test_submit_and_complete() -> None:
    scheduler = CrawlScheduler(_FakeCrawler())  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x", max_pages=3, max_depth=1, strategy="bfs")
    job = await scheduler.get_status(job_id)
    assert job is not None
    assert job.status.value == "queued"
    assert job.strategy == "bfs"

    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job is not None
    assert job.status.value == "done"
    assert job.pages_crawled == 3
    assert job.pages_failed == 0
    assert len(job.results) == 3
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_submit_with_failure_results() -> None:
    class _MixedCrawler:
        async def crawl(self, url: str, **kwargs: Any) -> Any:
            from chameleon.core.exceptions import ScrapeStatus
            from chameleon.core.models import ScrapeMetadata, ScrapeResult

            for i in range(3):
                status = ScrapeStatus.SUCCESS if i < 2 else ScrapeStatus.ERROR
                yield ScrapeResult(
                    status=status,
                    url=f"http://x/{i}",
                    metadata=ScrapeMetadata(url=f"http://x/{i}", status_code=200),
                    error="boom" if i == 2 else None,
                )

    scheduler = CrawlScheduler(_MixedCrawler())  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job is not None and job.status.value == "done"
    assert job.pages_crawled == 2
    assert job.pages_failed == 1


@pytest.mark.asyncio
async def test_job_failed_path() -> None:
    scheduler = CrawlScheduler(_FakeCrawler(fail=True))  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job is not None
    assert job.status.value == "failed"
    assert job.error is not None
    assert "crawler exploded" in job.error


@pytest.mark.asyncio
async def test_cancel_running_job() -> None:
    scheduler = CrawlScheduler(_FakeCrawler())  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    assert await scheduler.cancel(job_id) is True
    job = await scheduler.get_status(job_id)
    assert job is not None and job.status.value == "cancelled"
    assert job.finished_at is not None


@pytest.mark.asyncio
async def test_cancel_unknown_job() -> None:
    scheduler = CrawlScheduler(_FakeCrawler())  # type: ignore[arg-type]
    assert await scheduler.cancel("nonexistent") is False


@pytest.mark.asyncio
async def test_get_status_unknown() -> None:
    scheduler = CrawlScheduler(_FakeCrawler())  # type: ignore[arg-type]
    assert await scheduler.get_status("nope") is None


# ---------- Webhook ----------


@pytest.mark.asyncio
async def test_webhook_no_url_skips() -> None:
    scheduler = CrawlScheduler(_FakeCrawler(), webhook_url=None)  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job is not None and job.status.value == "done"


@pytest.mark.asyncio
async def test_webhook_notified_on_done(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    payloads: list[dict[str, Any]] = []

    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            pass

        async def post(self, url: str, json: dict[str, Any]) -> Any:
            payloads.append(json)
            return None

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=_FakeClient))

    scheduler = CrawlScheduler(_FakeCrawler(), webhook_url="http://hook.local/end")  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert len(payloads) == 1
    assert payloads[0]["job_id"] == job_id
    assert payloads[0]["status"] == "done"


@pytest.mark.asyncio
async def test_webhook_failure_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    class _BrokenClient:
        def __init__(self, timeout: float) -> None:
            pass

        async def post(self, url: str, json: dict[str, Any]) -> Any:
            raise ConnectionError("webhook down")

        async def __aenter__(self) -> _BrokenClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(AsyncClient=_BrokenClient))

    scheduler = CrawlScheduler(_FakeCrawler(), webhook_url="http://hook.local/end")  # type: ignore[arg-type]
    job_id = await scheduler.submit("http://x")
    for _ in range(100):
        job = await scheduler.get_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job is not None and job.status.value == "done"  # webhook 异常被吞，任务仍完成


@pytest.mark.asyncio
async def test_run_with_missing_job() -> None:
    """store 中无此 job 时 _run 直接返回。"""
    store = InMemoryJobStore()
    scheduler = CrawlScheduler(_FakeCrawler(), store=store)  # type: ignore[arg-type]
    await scheduler._run("ghost-job")  # 不应抛异常
