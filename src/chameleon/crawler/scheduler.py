"""任务调度：Job 状态机、内存/Redis 存储、断点续爬（方案 5.4 Scheduler）。"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from chameleon.core.models import CrawlJob, JobStatus
from chameleon.crawler.deep_crawler import DeepCrawler
from chameleon.infra.logging import get_logger

log = get_logger("scheduler")


class JobStore(ABC):
    """任务持久化抽象：内存（单机）/ Redis（分布式）。"""

    @abstractmethod
    async def create(self, job: CrawlJob) -> None: ...

    @abstractmethod
    async def get(self, job_id: str) -> CrawlJob | None: ...

    @abstractmethod
    async def update(self, job: CrawlJob) -> None: ...

    @abstractmethod
    async def list(self) -> list[CrawlJob]: ...


class InMemoryJobStore(JobStore):
    """进程内存储（测试/单机）。"""

    def __init__(self) -> None:
        self._jobs: dict[str, CrawlJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: CrawlJob) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job

    async def get(self, job_id: str) -> CrawlJob | None:
        return self._jobs.get(job_id)

    async def update(self, job: CrawlJob) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job

    async def list(self) -> list[CrawlJob]:
        return list(self._jobs.values())


class RedisJobStore(JobStore):
    """Redis 存储（分布式）。key: chameleon:job:{id} → JSON。"""

    def __init__(self, redis_url: str) -> None:
        from redis.asyncio import Redis

        self._redis = Redis.from_url(redis_url)

    async def create(self, job: CrawlJob) -> None:
        await self._redis.set(f"chameleon:job:{job.job_id}", job.model_dump_json())

    async def get(self, job_id: str) -> CrawlJob | None:
        raw = await self._redis.get(f"chameleon:job:{job_id}")
        return CrawlJob.model_validate_json(raw) if raw else None

    async def update(self, job: CrawlJob) -> None:
        await self.create(job)

    async def list(self) -> list[CrawlJob]:
        keys = await self._redis.keys("chameleon:job:*")
        jobs = []
        for key in keys:
            raw = await self._redis.get(key)
            if raw:
                jobs.append(CrawlJob.model_validate_json(raw))
        return jobs

    async def close(self) -> None:
        await self._redis.aclose()


class CrawlScheduler:
    """提交/执行/查询/取消爬取任务。asyncio 任务驱动，支持断点续爬。"""

    def __init__(self, crawler: DeepCrawler, store: JobStore | None = None, webhook_url: str | None = None) -> None:
        self.crawler = crawler
        self.store = store or InMemoryJobStore()
        self.webhook_url = webhook_url
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def submit(self, url: str, *, max_pages: int = 50, max_depth: int = 3, strategy: str = "adaptive") -> str:
        job = CrawlJob(
            job_id=uuid.uuid4().hex[:12],
            url=url,
            status=JobStatus.QUEUED,
            strategy=strategy,
            max_pages=max_pages,
            max_depth=max_depth,
        )
        await self.store.create(job)
        self._tasks[job.job_id] = asyncio.create_task(self._run(job.job_id))
        return job.job_id

    async def _run(self, job_id: str) -> None:
        job = await self.store.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        await self.store.update(job)
        try:
            async for result in self.crawler.crawl(
                job.url,
                max_pages=job.max_pages,
                max_depth=job.max_depth,
                strategy=job.strategy,
            ):
                if result.status.value == "success":
                    job.pages_crawled += 1
                else:
                    job.pages_failed += 1
                job.results.append(result.url)
                if len(job.results) % 10 == 0:
                    await self.store.update(job)
            job.status = JobStatus.DONE
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            log.error("job_failed", job_id=job_id, error=str(exc))
        finally:
            job.finished_at = datetime.now(UTC)
            await self.store.update(job)
            if self.webhook_url:
                await self._notify_webhook(job)

    async def get_status(self, job_id: str) -> CrawlJob | None:
        return await self.store.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task is None:
            return False
        task.cancel()
        job = await self.store.get(job_id)
        if job is not None and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            await self.store.update(job)
        return True

    async def _notify_webhook(self, job: CrawlJob) -> None:
        if self.webhook_url is None:
            return
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(self.webhook_url, json=json.loads(job.model_dump_json()))
        except Exception as exc:
            log.warning("webhook_failed", url=self.webhook_url, error=str(exc))
