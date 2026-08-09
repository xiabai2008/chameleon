"""MCP Server 补强测试（覆盖率 45% → 70%+）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import chameleon.interfaces.mcp_server as mcp_mod
from chameleon.core.config import SecurityConfig
from chameleon.core.exceptions import ScrapeStatus
from chameleon.core.models import ScrapeMetadata, ScrapeResult
from chameleon.interfaces.security import SSRFGuard


@pytest.fixture(autouse=True)
def _no_ssrf() -> None:
    """测试使用本地服务器，绕过 SSRF 保护（测试内直接替换 guard）。"""
    mcp_mod._guard = SSRFGuard(SecurityConfig(enable_ssrf_protection=False))
    yield
    mcp_mod._guard = None


def _tool(name: str) -> Any:
    return mcp_mod.mcp._tool_manager._tools[name]  # noqa: SLF001


# ---------- _safe_output ----------


def test_safe_output_plain_dict() -> None:
    assert mcp_mod._safe_output({"a": 1}) == {"a": 1}


def test_safe_output_truncates_long_markdown() -> None:
    result = ScrapeResult(
        status=ScrapeStatus.SUCCESS,
        url="http://x",
        content={"markdown": "a" * 20000},
        metadata=ScrapeMetadata(url="http://x"),
    )
    data = mcp_mod._safe_output(result)
    assert data["truncated"] is True
    assert len(data["content"]["markdown"]) <= 12000 + 20


def test_safe_output_short_markdown_untouched() -> None:
    result = ScrapeResult(
        status=ScrapeStatus.SUCCESS,
        url="http://x",
        content={"markdown": "short"},
        metadata=ScrapeMetadata(url="http://x"),
    )
    data = mcp_mod._safe_output(result)
    assert "truncated" not in data


# ---------- 核心工具（真实本地服务器） ----------


@pytest.mark.asyncio
async def test_scrape_url_tool(test_server: str) -> None:
    result = await _tool("scrape_url").fn(url=f"{test_server}/static")
    assert result["status"] == "success"
    assert "静态页面标题" in result["content"]["markdown"]


@pytest.mark.asyncio
async def test_scrape_url_with_schema(test_server: str) -> None:
    result = await _tool("scrape_url").fn(
        url=f"{test_server}/products",
        schema={"type": "object", "properties": {"title": {"type": "string", "css": "h1"}}},
    )
    assert result["extracted"]["title"] == "全部产品"


@pytest.mark.asyncio
async def test_crawl_site_and_status(test_server: str) -> None:
    resp = await _tool("crawl_site").fn(url=f"{test_server}/site/a", max_pages=3, max_depth=2, strategy="bfs")
    assert resp["status"] == "queued"
    job_id = resp["job_id"]

    for _ in range(200):
        job = await _tool("get_job_status").fn(job_id=job_id)
        if job["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.02)
    assert job["status"] == "done"
    assert job["pages_crawled"] >= 2


@pytest.mark.asyncio
async def test_get_job_status_not_found() -> None:
    assert (await _tool("get_job_status").fn(job_id="ghost"))["status"] == "not_found"


@pytest.mark.asyncio
async def test_map_site_tool(test_server: str) -> None:
    result = await _tool("map_site").fn(url=f"{test_server}/site/a")
    assert any("/site/" in u for u in result["links"])


@pytest.mark.asyncio
async def test_extract_data_tool(test_server: str) -> None:
    result = await _tool("extract_data").fn(
        url=f"{test_server}/products",
        schema={"type": "object", "properties": {"title": {"type": "string", "css": "h1"}}, "required": ["title"]},
    )
    assert result["extracted"]["title"] == "全部产品"


@pytest.mark.asyncio
async def test_diagnose_site_tool(test_server: str) -> None:
    result = await _tool("diagnose_site").fn(url=f"{test_server}/static")
    assert result["bare_status"] == 200
    assert "escalation_level" in result


@pytest.mark.asyncio
async def test_get_robots_txt_tool(test_server: str) -> None:
    result = await _tool("get_robots_txt").fn(url=f"{test_server}/")
    assert "User-agent" in result["robots_txt"]


# ---------- 辅助工具（mock service，避免重网络） ----------


@pytest.mark.asyncio
async def test_search_web_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(query: str, *, max_results: int, language: str) -> list[dict[str, str]]:
        return [{"title": f"结果 {query}", "url": "http://x/1", "snippet": "s"}]

    monkeypatch.setattr(mcp_mod._get_service(), "search_web", fake_search)
    result = await _tool("search_web").fn(query="python", max_results=3)
    assert result["results"][0]["title"] == "结果 python"


@pytest.mark.asyncio
async def test_batch_scrape_tool(test_server: str) -> None:
    result = await _tool("batch_scrape").fn(urls=[f"{test_server}/static", f"{test_server}/static2"])
    assert result["count"] == 2
    assert all(r["status"] == "success" for r in result["results"])


@pytest.mark.asyncio
async def test_get_screenshot_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot(url: str, *, full_page: bool) -> str:
        return "data:image/png;base64,QUJD"

    monkeypatch.setattr(mcp_mod._get_service(), "get_screenshot", fake_shot)
    result = await _tool("get_screenshot").fn(url="https://example.com")
    assert result["screenshot_base64"].startswith("data:image/png")


@pytest.mark.asyncio
async def test_get_network_log_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_log(url: str, *, filter_type: str) -> list[dict[str, Any]]:
        return [{"method": "GET", "url": "http://x/api", "type": "xhr"}]

    monkeypatch.setattr(mcp_mod._get_service(), "get_network_log", fake_log)
    result = await _tool("get_network_log").fn(url="https://example.com", filter_type="xhr")
    assert result["entries"][0]["url"] == "http://x/api"


@pytest.mark.asyncio
async def test_check_proxy_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_check(proxy_url: str) -> dict[str, Any]:
        return {"proxy": proxy_url, "alive": True, "latency_ms": 50, "exit_ip": "1.2.3.4"}

    monkeypatch.setattr(mcp_mod._get_service(), "check_proxy", fake_check)
    result = await _tool("check_proxy").fn(proxy_url="http://p:8080")
    assert result["alive"] is True


# ---------- SSRF 拦截 ----------


@pytest.mark.asyncio
async def test_scrape_url_ssrf_blocked() -> None:
    mcp_mod._guard = SSRFGuard()  # 恢复默认（开启保护）
    from chameleon.interfaces.security import SSRFError

    with pytest.raises(SSRFError):
        await _tool("scrape_url").fn(url="http://127.0.0.1:8080/admin")
