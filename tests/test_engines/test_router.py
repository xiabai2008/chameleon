"""引擎与路由器测试（P1）。"""

from __future__ import annotations

import pytest

from chameleon.core.content_validator import ContentValidator
from chameleon.core.exceptions import BlockedError, NotReachableError
from chameleon.core.models import EngineType, FetchRequest, ScrapeStatus
from chameleon.core.router import SmartRouter
from chameleon.engines.browser_engine import BrowserEngine
from chameleon.engines.http_engine import HttpEngine


@pytest.mark.asyncio
async def test_http_engine_static_page(test_server: str) -> None:
    engine = HttpEngine()
    result = await engine.fetch(FetchRequest(url=f"{test_server}/static"))
    assert result.status_code == 200
    assert "静态页面标题" in result.content
    assert result.engine == EngineType.HTTP
    assert result.response_time_ms >= 0
    await engine.close()


@pytest.mark.asyncio
async def test_http_engine_gbk_encoding(test_server: str) -> None:
    engine = HttpEngine()
    result = await engine.fetch(FetchRequest(url=f"{test_server}/gbk"))
    assert "中文编码测试页面内容" in result.content
    await engine.close()


@pytest.mark.asyncio
async def test_http_engine_redirect_followed(test_server: str) -> None:
    engine = HttpEngine()
    result = await engine.fetch(FetchRequest(url=f"{test_server}/redirect"))
    assert result.final_url == f"{test_server}/static"
    assert "静态页面标题" in result.content
    await engine.close()


@pytest.mark.asyncio
async def test_http_engine_403_raises_blocked(test_server: str) -> None:
    engine = HttpEngine()
    with pytest.raises(BlockedError):
        await engine.fetch(FetchRequest(url=f"{test_server}/blocked"))
    await engine.close()


@pytest.mark.asyncio
async def test_http_engine_429_raises_blocked(test_server: str) -> None:
    engine = HttpEngine()
    with pytest.raises(BlockedError):
        await engine.fetch(FetchRequest(url=f"{test_server}/rate-limited"))
    await engine.close()


@pytest.mark.asyncio
async def test_http_engine_unreachable() -> None:
    engine = HttpEngine(timeout=1.0)
    with pytest.raises(NotReachableError):
        await engine.fetch(FetchRequest(url="http://127.0.0.1:1/nope"))
    await engine.close()


def test_content_validator_rules() -> None:
    v = ContentValidator(min_content_length=500)
    from chameleon.core.models import FetchResult

    assert v.is_valid(FetchResult(url="x", status_code=200, content="a" * 600)) == (True, None)
    assert v.is_valid(FetchResult(url="x", status_code=403, content="a" * 600)) == (False, "blocked_status_403")
    assert v.is_valid(FetchResult(url="x", status_code=200, content="short")) == (False, "content_too_short")
    assert v.is_valid(FetchResult(url="x", status_code=200, content="a" * 600 + "请输入验证码")) == (
        False,
        "anti_bot_marker:请输入验证码",
    )


@pytest.mark.asyncio
async def test_router_static_page_uses_http(test_server: str) -> None:
    engine = HttpEngine()
    router = SmartRouter(http_engine=engine)
    result = await router.fetch(FetchRequest(url=f"{test_server}/static"))
    assert result.engine == EngineType.HTTP
    assert result.escalation_level == 0
    await engine.close()


@pytest.mark.asyncio
async def test_router_short_content_escalates_to_browser(test_server: str) -> None:
    http = HttpEngine()
    browser = BrowserEngine(pool_size=1, headless=True)
    router = SmartRouter(http_engine=http, browser_engine=browser)
    result = await router.fetch(FetchRequest(url=f"{test_server}/spa"))
    assert result.engine == EngineType.BROWSER
    assert "SPA 动态标题" in result.content
    await http.close()
    await browser.close()


@pytest.mark.asyncio
async def test_router_mode_static_keeps_http(test_server: str) -> None:
    http = HttpEngine()
    browser = BrowserEngine(pool_size=1, headless=True)
    router = SmartRouter(http_engine=http, browser_engine=browser)
    result = await router.fetch(FetchRequest(url=f"{test_server}/spa"), mode="static")
    assert result.engine == EngineType.HTTP
    await http.close()
    await browser.close()


@pytest.mark.asyncio
async def test_router_force_browser(test_server: str) -> None:
    http = HttpEngine()
    browser = BrowserEngine(pool_size=1, headless=True)
    router = SmartRouter(http_engine=http, browser_engine=browser)
    result = await router.fetch(FetchRequest(url=f"{test_server}/static"), force_browser=True)
    assert result.engine == EngineType.BROWSER
    await http.close()
    await browser.close()


@pytest.mark.asyncio
async def test_router_scrape_result_status(test_server: str) -> None:
    http = HttpEngine()
    router = SmartRouter(http_engine=http)
    ok = await router.scrape(f"{test_server}/static")
    assert ok.status == ScrapeStatus.SUCCESS
    assert ok.metadata.status_code == 200
    blocked = await router.scrape(f"{test_server}/blocked")
    assert blocked.status == ScrapeStatus.RATE_LIMITED
    assert blocked.suggested_action is not None
    await http.close()
