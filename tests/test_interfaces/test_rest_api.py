"""REST API 集成测试（P6-5）。"""

from __future__ import annotations

import httpx
import pytest

from chameleon.interfaces.rest_api import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_scrape_endpoint(test_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/scrape", json={"url": f"{test_server}/static"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["content"]["markdown"]
        assert data["metadata"]["status_code"] == 200


@pytest.mark.asyncio
async def test_scrape_endpoint_rejects_bad_url(test_server: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/scrape", json={"url": "not-a-url"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_extract_endpoint(test_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    schema = {
        "type": "object",
        "properties": {"title": {"type": "string", "css": "h1"}},
        "required": ["title"],
    }
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/extract", json={"url": f"{test_server}/products", "schema": schema})
        assert resp.status_code == 200
        data = resp.json()
        assert data["extracted"]["title"] == "全部产品"


@pytest.mark.asyncio
async def test_map_endpoint(test_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/map", json={"url": f"{test_server}/site/a"})
        assert resp.status_code == 200
        data = resp.json()
        assert any("/site/" in u for u in data["links"])


@pytest.mark.asyncio
async def test_crawl_job_flow(test_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/crawl", json={"url": f"{test_server}/site/a", "max_pages": 4, "max_depth": 2})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        import asyncio

        status = None
        for _ in range(200):
            r = await client.get(f"/api/v1/jobs/{job_id}")
            status = r.json()
            if status["status"] in ("done", "failed"):
                break
            await asyncio.sleep(0.05)
        assert status is not None
        assert status["status"] == "done"
        assert status["pages_crawled"] >= 2


@pytest.mark.asyncio
async def test_job_not_found() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/jobs/nonexistent")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/search", json={"query": "python", "max_results": 3})
        assert resp.status_code == 200
        assert "results" in resp.json()
