"""浏览器引擎：Playwright + context 池，SPA/动态页采集。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from chameleon.anti_detection.behavior_simulator import BehaviorSimulator
from chameleon.anti_detection.stealth import StealthPlugin
from chameleon.core.exceptions import BlockedError, NotReachableError
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.engines.base import BaseEngine

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class BrowserContextPool:
    """预创建 N 个隔离 context 供并发任务借用/归还。"""

    def __init__(self, pool_size: int = 2, headless: bool = True, *, stealth: StealthPlugin | None = None) -> None:
        self._size = pool_size
        self._headless = headless
        self._stealth = stealth
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._semaphore = asyncio.Semaphore(self._size)
        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(
            headless=self._headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        for _ in range(self._size):
            context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=DEFAULT_USER_AGENT,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            if self._stealth is not None:
                await self._stealth.apply(context)
            self._contexts.append(context)

    @asynccontextmanager
    async def borrow(self) -> AsyncIterator[BrowserContext]:
        """借用 context，归还后重新使用。首次调用自动启动。"""
        if self._semaphore is None:
            await self.start()
        assert self._semaphore is not None, "pool not started"
        await self._semaphore.acquire()
        ctx = self._contexts.pop(0)
        try:
            yield ctx
        finally:
            self._contexts.append(ctx)
            self._semaphore.release()

    async def stop(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        self._contexts = []
        self._semaphore = None


class BrowserEngine(BaseEngine):
    """Playwright 渲染引擎，带 context 池、wait_for、行为模拟、无限滚动、Shadow DOM 穿透。"""

    name = EngineType.BROWSER

    def __init__(
        self,
        pool_size: int = 2,
        headless: bool = True,
        timeout: float = 45.0,
        *,
        behavior: BehaviorSimulator | None = None,
        infinite_scroll: bool = False,
        extract_shadow: bool = False,
    ) -> None:
        self.pool = BrowserContextPool(pool_size=pool_size, headless=headless)
        self.stealth = StealthPlugin(enabled=True)
        self.behavior = behavior
        self.infinite_scroll = infinite_scroll
        self.extract_shadow = extract_shadow
        self._timeout = timeout

    async def _scroll_to_load_more(self, page: Page) -> None:
        """无限滚动：增量滚动直到内容不再增长（内容指纹去重）。"""
        last_length = 0
        for _ in range(15):
            current = await page.evaluate("document.body.innerHTML.length")
            if current <= last_length:
                break
            last_length = current
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(600)

    async def _content_with_shadow(self, page: Page) -> str:
        """page.content() + Shadow DOM / iframe 文本穿透拼接。"""
        main = await page.content()
        shadow_texts: list[str] = await page.evaluate(
            """
            () => {
              const results = [];
              const collect = (root) => {
                const shadowHosts = root.querySelectorAll('*');
                shadowHosts.forEach(el => {
                  if (el.shadowRoot) {
                    results.push(el.shadowRoot.textContent || '');
                    collect(el.shadowRoot);
                  }
                });
              };
              collect(document);
              return results;
            }
            """
        )
        iframe_texts: list[str] = []
        for frame in page.frames:
            if frame != page.main_frame:
                try:
                    iframe_texts.append(await frame.evaluate("() => document.body ? document.body.innerText : ''"))
                except Exception:
                    continue
        extra = "\n".join(t for t in [*shadow_texts, *iframe_texts] if t.strip())
        return main + ("\n<!-- shadow/iframe content -->\n" + extra if extra else "")

    async def _goto(self, ctx: BrowserContext, request: FetchRequest) -> FetchResult:
        page: Page = await ctx.new_page()
        started = time.perf_counter()
        final_url = request.url
        status_code: int | None = None
        try:
            resp = await page.goto(
                request.url,
                wait_until="domcontentloaded",
                timeout=int(request.timeout or self._timeout) * 1000,
            )
            if request.wait_for:
                await page.wait_for_selector(request.wait_for, timeout=30000)
            else:
                await page.wait_for_timeout(500)
            if self.infinite_scroll:
                await self._scroll_to_load_more(page)
            if self.behavior is not None:
                await self.behavior.human_scroll(page)
                await self.behavior.human_mouse_trail(page)
            final_url = page.url
            status_code = resp.status if resp is not None else None
            content = await self._content_with_shadow(page) if self.extract_shadow else await page.content()
        except Exception as exc:
            raise NotReachableError(f"browser goto failed for {request.url}: {exc}") from exc
        finally:
            await page.close()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        result = FetchResult(
            url=request.url,
            final_url=final_url,
            status_code=status_code,
            content=content,
            engine=self.name,
            proxy_used=request.proxy,
            response_time_ms=elapsed_ms,
        )
        if status_code == 403 or status_code == 429:
            raise BlockedError(f"browser blocked with status {status_code}", status_code=status_code)
        return result

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if request.proxy:
            async with self.pool.borrow() as ctx:
                return await self._goto_with_proxy(ctx, request)
        async with self.pool.borrow() as ctx:
            return await self._goto(ctx, request)

    async def _goto_with_proxy(self, ctx: BrowserContext, request: FetchRequest) -> FetchResult:
        """代理场景：为本次请求创建带代理配置的独立 context。"""
        browser = ctx.browser
        assert browser is not None
        new_ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=DEFAULT_USER_AGENT,
            proxy={"server": request.proxy} if request.proxy else None,
        )
        try:
            return await self._goto(new_ctx, request)
        finally:
            await new_ctx.close()

    async def close(self) -> None:
        await self.pool.stop()
