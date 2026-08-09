"""反爬基础（P2）测试：身份伪装、代理池、蜜罐过滤、stealth、升级链。"""

from __future__ import annotations

import pytest

from chameleon.anti_detection.honeypot_filter import HoneypotFilter, is_hidden_by_css
from chameleon.anti_detection.identity_faker import IdentityFaker
from chameleon.anti_detection.proxy_manager import ProxyManager
from chameleon.anti_detection.stealth import StealthPlugin
from chameleon.core.config import ProxyConfig
from chameleon.core.exceptions import ProxyUnavailableError
from chameleon.core.models import FetchRequest
from chameleon.core.router import SmartRouter
from chameleon.engines.browser_engine import BrowserEngine
from chameleon.engines.http_engine import HttpEngine

# ---------- IdentityFaker ----------


def test_identity_faker_generates_distinct_headers() -> None:
    faker = IdentityFaker()
    batch = faker.generate_headers_many(count=8)
    uas = {h["User-Agent"] for h in batch}
    assert len(uas) == 8
    for headers in batch:
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"]
        assert headers["Sec-Fetch-Dest"] == "document"


def test_identity_faker_pick_ua_stable() -> None:
    faker = IdentityFaker()
    assert faker.pick_ua("example.com") == faker.pick_ua("example.com")
    assert faker.pick_ua("a.com") != faker.pick_ua("b.com") or len(faker._ua_pool) == 1  # noqa: SLF001


# ---------- ProxyManager ----------


@pytest.mark.asyncio
async def test_proxy_manager_weighted_selection() -> None:
    config = ProxyConfig(static_list=["http://p1:8080", "http://p2:8080", "http://p3:8080"])
    mgr = ProxyManager(config)
    got = {await mgr.get() for _ in range(10)}
    assert got <= {"http://p1:8080", "http://p2:8080", "http://p3:8080"}
    assert got  # 非空


@pytest.mark.asyncio
async def test_proxy_manager_excludes_failed() -> None:
    config = ProxyConfig(static_list=["http://bad:8080", "http://good:8080"])
    mgr = ProxyManager(config)
    await mgr.mark_failed("http://bad:8080", delta=-50)
    for _ in range(10):
        assert await mgr.get() == "http://good:8080"


@pytest.mark.asyncio
async def test_proxy_manager_unavailable() -> None:
    config = ProxyConfig(static_list=["http://dead:8080"])
    mgr = ProxyManager(config)
    await mgr.mark_failed("http://dead:8080", delta=-50)
    with pytest.raises(ProxyUnavailableError):
        await mgr.get()


# ---------- HoneypotFilter ----------


def test_honeypot_filter_removes_hidden_links() -> None:
    html = """<html><body>
    <a href="/visible" style="display:block">可见</a>
    <a href="/hidden-style" style="display:none">隐藏</a>
    <a href="/hidden-aria" aria-hidden="true">隐藏2</a>
    <a href="/empty" style=""> </a>
    <a href="javascript:void(0)">JS</a>
    <a href="#frag">锚点</a>
    </body></html>"""
    filter_ = HoneypotFilter()
    links = filter_.filter_links(html, "https://example.com/page")
    assert links == ["https://example.com/visible"]


def test_is_hidden_by_css() -> None:
    assert is_hidden_by_css({"style": "display:none;color:red"})
    assert is_hidden_by_css({"style": "visibility: hidden"})
    assert is_hidden_by_css({"aria-hidden": "true"})
    assert not is_hidden_by_css({"style": "display:block"})


# ---------- Stealth ----------


@pytest.mark.browser
@pytest.mark.asyncio
async def test_stealth_script_hides_webdriver() -> None:
    stealth = StealthPlugin()
    browser = BrowserEngine(pool_size=1, headless=True)
    browser.pool._stealth = stealth  # noqa: SLF001
    await browser.pool.start()
    async with browser.pool.borrow() as ctx:
        page = await ctx.new_page()
        await page.goto("about:blank")
        webdriver = await page.evaluate("navigator.webdriver")
        assert webdriver is None
        await page.close()
    await browser.close()


# ---------- 升级链 ----------


@pytest.mark.asyncio
async def test_router_escalates_with_identity_headers(anti_bot_server: str) -> None:
    """模拟站：裸请求 403 → 带完整头的请求成功（Level 1）。"""
    import httpx
    from tests.fixtures.anti_bot_site import simulator

    async with httpx.AsyncClient(timeout=0.5) as client:
        await client.get(f"{anti_bot_server}/reset")

    http = HttpEngine()
    faker = IdentityFaker()
    router = SmartRouter(http_engine=http, identity_faker=faker)
    result = await router.fetch(FetchRequest(url=f"{anti_bot_server}/protected"))
    assert result.status_code == 200
    assert result.escalation_level == 1
    assert "受保护内容" in result.content
    stats = simulator.snapshot()
    assert stats["blocked_bare"] >= 1  # 裸请求确实被 403
    await http.close()


@pytest.mark.asyncio
async def test_router_proxy_manager_integrated(anti_bot_server: str) -> None:
    """代理管理器正确接入升级链：静态目标走 L0，反爬目标走 L1。"""
    import httpx
    from tests.fixtures.anti_bot_site import simulator

    async with httpx.AsyncClient(timeout=0.5) as client:
        await client.get(f"{anti_bot_server}/reset")

    async def fake_checker(_proxy: str) -> tuple[bool, float]:
        return True, 100.0

    config = ProxyConfig(enabled=True, static_list=["http://fake-proxy:8080"])
    proxy_mgr = ProxyManager(config, checker=fake_checker)
    http = HttpEngine()
    faker = IdentityFaker()
    router = SmartRouter(http_engine=http, identity_faker=faker, proxy_manager=proxy_mgr)

    result = await router.fetch(FetchRequest(url=f"{anti_bot_server}/protected"))
    assert result.status_code == 200
    assert result.escalation_level == 1
    stats = simulator.snapshot()
    assert stats["blocked_bare"] >= 1

    proxy = await proxy_mgr.get()
    assert proxy == "http://fake-proxy:8080"
    await http.close()
