"""Agent 接口（P6）测试：SDK 门面、MCP 工具、CLI。"""

from __future__ import annotations

import pytest

from chameleon.interfaces.security import SSRFError, SSRFGuard, is_internal_hostname, validate_url


def test_validate_url() -> None:
    assert validate_url("https://example.com/path")
    assert validate_url("http://example.com")
    assert not validate_url("ftp://example.com")
    assert not validate_url("not a url")
    assert not validate_url("example.com")


def test_is_internal_hostname() -> None:
    assert is_internal_hostname("127.0.0.1")
    assert is_internal_hostname("10.0.0.5")
    assert is_internal_hostname("192.168.1.1")
    assert is_internal_hostname("localhost")
    assert is_internal_hostname("172.16.3.4")
    assert not is_internal_hostname("example.com")
    assert not is_internal_hostname("8.8.8.8")


@pytest.mark.asyncio
async def test_ssrf_guard_blocks_internal() -> None:
    guard = SSRFGuard()
    with pytest.raises(SSRFError):
        await guard.assert_safe("http://127.0.0.1:8000/admin")
    with pytest.raises(SSRFError):
        await guard.assert_safe("http://localhost/secret")
    await guard.assert_safe("https://example.com/page")  # 不应抛错（DNS 不解析才安全，此处仅格式）


def test_ssrf_guard_disable() -> None:
    from chameleon.core.config import SecurityConfig

    guard = SSRFGuard(SecurityConfig(enable_ssrf_protection=False))
    import asyncio

    asyncio.run(guard.assert_safe("http://127.0.0.1/x"))  # 不抛错


# ---------- SDK 门面 ----------


@pytest.mark.asyncio
async def test_sdk_scrape_markdown(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    result = await service.scrape(f"{test_server}/static")
    assert result.status.value == "success"
    assert result.content is not None
    assert result.content.markdown
    assert "静态页面标题" in (result.content.markdown or "")
    assert result.metadata.status_code == 200
    await service.close()


@pytest.mark.asyncio
async def test_sdk_scrape_with_schema(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "css": "h1"},
            "items": {
                "type": "array",
                "css": "ul.products",
                "items": {
                    "type": "object",
                    "css": "li.product",
                    "properties": {"name": {"type": "string", "css": "h2.name"}},
                },
            },
        },
    }
    service = Chameleon()
    result = await service.extract(f"{test_server}/products", schema)
    assert result.extracted is not None
    assert len(result.extracted["items"]) == 5
    await service.close()


@pytest.mark.asyncio
async def test_sdk_batch_scrape(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    results = await service.batch_scrape([f"{test_server}/static", f"{test_server}/static2"], concurrency=2)
    assert len(results) == 2
    assert all(r.status.value == "success" for r in results)
    await service.close()


@pytest.mark.asyncio
async def test_sdk_crawl_job(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    job_id = await service.crawl(f"{test_server}/site/a", max_pages=5, max_depth=3, strategy="bfs")
    job = None
    for _ in range(200):
        job = await service.get_job_status(job_id)
        if job is not None and job.status.value in ("done", "failed"):
            break
        import asyncio

        await asyncio.sleep(0.05)
    assert job is not None
    assert job.status.value == "done"
    assert job.pages_crawled >= 3
    await service.close()


@pytest.mark.asyncio
async def test_sdk_map_site(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    result = await service.map_site(f"{test_server}/site/a")
    assert any("/site/" in u for u in result["links"])
    await service.close()


@pytest.mark.asyncio
async def test_sdk_diagnose(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    diag = await service.diagnose_site(f"{test_server}/static")
    assert diag["bare_status"] == 200
    assert diag["escalation_level"] == 0
    await service.close()


# ---------- MCP ----------


def test_mcp_tool_registration() -> None:
    from chameleon.interfaces.mcp_server import mcp

    tools = mcp._tool_manager._tools  # noqa: SLF001
    expected = {
        "scrape_url", "crawl_site", "map_site", "extract_data", "search_web",
        "batch_scrape", "get_screenshot", "diagnose_site", "check_proxy",
        "get_job_status", "get_robots_txt", "get_network_log",
    }
    assert expected <= set(tools.keys())
