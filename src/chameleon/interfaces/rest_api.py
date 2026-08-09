"""REST API：FastAPI，端点与 MCP 工具一一对应（方案 6.2）。"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chameleon.core.config import Settings
from chameleon.core.models import ScrapeRequest
from chameleon.interfaces.sdk import Chameleon
from chameleon.interfaces.security import SSRFGuard

app = FastAPI(title="Chameleon API", version="0.1.0", description="AI Agent 爬虫服务")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_service: Chameleon | None = None
_settings: Settings | None = None
_guard: SSRFGuard | None = None
_rate_buckets: dict[str, list[float]] = defaultdict(list)


def get_service() -> Chameleon:
    global _service
    if _service is None:
        _settings = Settings()
        _service = Chameleon(_settings)
    return _service


def get_guard() -> SSRFGuard:
    global _guard
    if _guard is None:
        _guard = SSRFGuard()
    return _guard


def _check_rate_limit(key: str) -> None:
    settings = Settings()
    limit = settings.security.rate_limit_per_minute
    now = time.monotonic()
    bucket = _rate_buckets[key]
    bucket[:] = [t for t in bucket if now - t < 60]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    bucket.append(now)


async def _require_auth(x_api_key: str | None = Header(default=None)) -> None:
    settings = Settings()
    if not settings.security.api_key:
        return  # 未配置密钥则开放（本地）
    if x_api_key != settings.security.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")
    _check_rate_limit(x_api_key or "anonymous")


class CrawlRequest(BaseModel):
    url: str
    max_pages: int = Field(default=50, ge=1, le=1000)
    max_depth: int = Field(default=3, ge=1, le=10)
    strategy: str = "adaptive"


class SearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=20)
    language: str = "zh"


@app.post("/api/v1/scrape", dependencies=[Depends(_require_auth)])
async def api_scrape(req: ScrapeRequest) -> dict[str, Any]:
    await get_guard().assert_safe(str(req.url))
    result = await get_service().scrape(
        str(req.url),
        mode=req.mode,
        output_format=req.output_format,
        schema=req.json_schema,
        extract_prompt=req.extract_prompt,
        wait_for=req.wait_for,
        proxy_region=req.proxy_region,
        timeout_seconds=req.timeout,
        max_output_tokens=req.max_output_tokens,
    )
    return result.model_dump()


@app.post("/api/v1/crawl", dependencies=[Depends(_require_auth)])
async def api_crawl(req: CrawlRequest) -> dict[str, Any]:
    await get_guard().assert_safe(req.url)
    job_id = await get_service().crawl(req.url, max_pages=req.max_pages, max_depth=req.max_depth, strategy=req.strategy)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/v1/map", dependencies=[Depends(_require_auth)])
async def api_map(req: CrawlRequest) -> dict[str, Any]:
    await get_guard().assert_safe(req.url)
    return await get_service().map_site(req.url)


@app.post("/api/v1/extract", dependencies=[Depends(_require_auth)])
async def api_extract(req: ScrapeRequest) -> dict[str, Any]:
    await get_guard().assert_safe(str(req.url))
    result = await get_service().extract(str(req.url), req.json_schema or {})
    return {"status": result.status.value, "extracted": result.extracted, "error": result.error}


@app.post("/api/v1/search", dependencies=[Depends(_require_auth)])
async def api_search(req: SearchRequest) -> dict[str, Any]:
    results = await get_service().search_web(req.query, max_results=req.max_results, language=req.language)
    return {"query": req.query, "results": results}


@app.post("/api/v1/batch", dependencies=[Depends(_require_auth)])
async def api_batch(urls: list[str]) -> dict[str, Any]:
    results = await get_service().batch_scrape(urls)
    return {"count": len(results), "results": [r.model_dump() for r in results]}


@app.post("/api/v1/screenshot", dependencies=[Depends(_require_auth)])
async def api_screenshot(url: str, full_page: bool = False) -> dict[str, Any]:
    await get_guard().assert_safe(url)
    data_uri = await get_service().get_screenshot(url, full_page=full_page)
    return {"url": url, "screenshot_base64": data_uri}


@app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(_require_auth)])
async def api_job_status(job_id: str) -> dict[str, Any]:
    job = await get_service().get_job_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump()


@app.delete("/api/v1/jobs/{job_id}", dependencies=[Depends(_require_auth)])
async def api_job_cancel(job_id: str) -> dict[str, Any]:
    cancelled = await get_service().scheduler.cancel(job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "cancelled": True}


@app.websocket("/api/v1/jobs/{job_id}/ws")
async def ws_job_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    try:
        last_pages = -1
        while True:
            job = await get_service().get_job_status(job_id)
            if job is None:
                await websocket.send_json({"job_id": job_id, "status": "not_found"})
                break
            if job.pages_crawled != last_pages or job.status.value in ("done", "failed", "cancelled"):
                last_pages = job.pages_crawled
                await websocket.send_json({"job_id": job_id, "status": job.status.value, "pages": job.pages_crawled})
            if job.status.value in ("done", "failed", "cancelled"):
                break
            await websocket.receive_text()  # 客户端心跳
    except WebSocketDisconnect:
        pass


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
