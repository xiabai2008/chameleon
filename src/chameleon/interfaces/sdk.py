"""Chameleon 服务门面：所有接口（MCP/REST/CLI）共享的唯一入口（方案 6.1 SDK）。"""

from __future__ import annotations

import asyncio
from typing import Any

from chameleon.anti_detection.captcha_solver import CaptchaRouter
from chameleon.anti_detection.identity_faker import IdentityFaker
from chameleon.anti_detection.proxy_manager import ProxyManager
from chameleon.core.config import Settings
from chameleon.core.exceptions import ChameleonError
from chameleon.core.models import CrawlJob, FetchRequest, ScrapeResult
from chameleon.core.router import SmartRouter
from chameleon.crawler.deep_crawler import DeepCrawler
from chameleon.crawler.robots import RobotsTxt
from chameleon.crawler.scheduler import CrawlScheduler
from chameleon.engines.browser_engine import BrowserEngine
from chameleon.engines.http_engine import HttpEngine
from chameleon.engines.tls_engine import TlsHttpEngine
from chameleon.infra.logging import bind_request_id, configure_logging, get_logger
from chameleon.pipeline.extractors.llm_extractor import LLMExtractor, OpenAIClient
from chameleon.pipeline.pipeline import Pipeline
from chameleon.utils.url_utils import hostname

log = get_logger("service")


class Chameleon:
    """统一服务入口。

    - scrape/extract/batch: 单页采集
    - crawl/map: 整站采集与 URL 发现
    - search/screenshot/network_log/diagnose: 辅助工具
    - get_job_status: 任务状态
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        configure_logging(level=self.settings.log_level, json_output=self.settings.log_json)
        self._build_engines()

    def _build_engines(self) -> None:
        self.http_engine = HttpEngine(timeout=self.settings.engine.http_timeout)
        self.tls_engine = TlsHttpEngine(timeout=self.settings.engine.http_timeout)
        self.browser_engine = BrowserEngine(
            pool_size=self.settings.engine.browser_pool_size,
            headless=self.settings.engine.browser_headless,
            timeout=self.settings.engine.browser_timeout,
        )
        self.identity = IdentityFaker()
        self.captcha = CaptchaRouter(self.settings.captcha)
        self.proxy_manager = ProxyManager(self.settings.proxy)
        self.llm: LLMExtractor | None = None

        self.router = SmartRouter(
            self.http_engine,
            browser_engine=self.browser_engine,
            tls_engine=self.tls_engine,
            captcha_router=self.captcha,
            identity_faker=self.identity,
            proxy_manager=self.proxy_manager,
            max_retries=self.settings.engine.max_retries,
        )
        self.pipeline = Pipeline(llm=self.llm, default_max_tokens=8000)
        self.robots = RobotsTxt()
        self.crawler = DeepCrawler(
            self.router,
            self.pipeline,
            robots=self.robots,
            respect_robots=self.settings.crawl.respect_robots,
        )
        self.scheduler = CrawlScheduler(self.crawler)

    def configure_llm(self, base_url: str, api_key: str, model: str) -> None:
        """启用 LLM 语义提取 / Hybrid 模式。"""
        self.llm = LLMExtractor(client=OpenAIClient(base_url, api_key, model))
        self.pipeline.llm = self.llm

    async def scrape(
        self,
        url: str,
        *,
        mode: str = "auto",
        output_format: str = "markdown",
        schema: dict[str, Any] | None = None,
        extract_prompt: str | None = None,
        strategy: str = "auto",
        wait_for: str | None = None,
        proxy_region: str | None = None,
        stealth_level: str = "medium",
        timeout_seconds: float | None = None,
        max_output_tokens: int = 8000,
        request_id: str | None = None,
    ) -> ScrapeResult:
        bind_request_id(request_id)
        if proxy_region:
            await self.proxy_manager.add(f"region:{proxy_region}", region=proxy_region)  # 区域标记占位
        raw = await self.router.fetch(
            FetchRequest(
                url=url,
                wait_for=wait_for,
                timeout=timeout_seconds,
                headers=self.identity.generate_headers(url),
            ),
            mode=mode,
        )
        selected_strategy = "llm" if extract_prompt else strategy
        return await self.pipeline.process(
            raw,
            output_format=output_format,
            schema=schema,
            extract_prompt=extract_prompt,
            strategy=selected_strategy,
            max_output_tokens=max_output_tokens,
        )

    async def extract(self, url: str, schema: dict[str, Any], *, strategy: str = "auto") -> ScrapeResult:
        return await self.scrape(url, schema=schema, strategy=strategy, output_format="json")

    async def crawl(self, url: str, *, max_pages: int = 50, max_depth: int = 3, strategy: str = "adaptive") -> str:
        return await self.scheduler.submit(url, max_pages=max_pages, max_depth=max_depth, strategy=strategy)

    async def map_site(self, url: str, *, sitemap_only: bool = False) -> dict[str, Any]:
        """发现站点 URL（不抓取内容）。"""
        seed = url.rstrip("/")
        from chameleon.crawler.url_discovery import discover_sitemap, sitemap_url_for

        urls: list[str] = []
        if not sitemap_only:
            try:
                raw = await self.router.fetch(FetchRequest(url=seed))
                from chameleon.crawler.url_discovery import discover_links

                urls = discover_links(raw.content, seed)
                urls = [u for u in urls if hostname(u) == hostname(seed) or u.startswith(f"{seed}")]
            except ChameleonError as exc:
                log.warning("map_initial_fetch_failed", url=url, error=str(exc))
        sitemap_urls: list[str] = []
        try:
            sitemap_urls = await discover_sitemap(self.http_engine._client_for(None), sitemap_url_for(seed))  # noqa: SLF001
        except Exception:
            sitemap_urls = []
        return {"url": url, "links": sorted(set(urls)), "sitemap": sitemap_urls}
    async def batch_scrape(self, urls: list[str], *, concurrency: int = 4, output_format: str = "markdown") -> list[ScrapeResult]:
        semaphore = asyncio.Semaphore(max(concurrency, 1))

        async def one(u: str) -> ScrapeResult:
            async with semaphore:
                return await self.scrape(u, output_format=output_format)

        return await asyncio.gather(*[one(u) for u in urls])

    async def get_screenshot(self, url: str, *, full_page: bool = False) -> str:
        """返回 base64 PNG data URI。"""
        import base64 as b64


        browser = self.browser_engine
        async with browser.pool.borrow() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=45000)
                shot = await page.screenshot(full_page=full_page)
            finally:
                await page.close()
        return f"data:image/png;base64,{b64.b64encode(shot).decode()}"

    async def search_web(self, query: str, *, max_results: int = 5, language: str = "zh") -> list[dict[str, str]]:
        """必应搜索：解析结果标题/链接/摘要（P8 将扩展多引擎）。"""
        import urllib.parse

        from selectolax.parser import HTMLParser

        base = "https://www.bing.com/search"
        params = {"q": query, "count": max_results, "mkt": "zh-CN" if language == "zh" else "en-US"}
        url = f"{base}?{urllib.parse.urlencode(params)}"
        try:
            raw = await self.router.fetch(
                FetchRequest(url=url, headers=self.identity.generate_headers(url)),
                mode="static",
            )
        except ChameleonError as exc:
            log.warning("search_failed", query=query, error=str(exc))
            return []
        results: list[dict[str, str]] = []
        try:
            tree = HTMLParser(raw.content)
            for li in tree.css("li.b_algo")[:max_results]:
                title_node = li.css_first("h2 a")
                snippet = li.css_first(".b_caption p")
                if title_node is None:
                    continue
                results.append({
                    "title": title_node.text(strip=True),
                    "url": title_node.attributes.get("href") or "",
                    "snippet": snippet.text(strip=True) if snippet else "",
                })
        except Exception:
            pass
        return results

    async def get_network_log(self, url: str, *, filter_type: str = "xhr") -> list[dict[str, Any]]:
        """浏览器网络请求日志（CDP 拦截），用于内部 API 发现。"""
        browser = self.browser_engine
        entries: list[dict[str, Any]] = []
        async with browser.pool.borrow() as ctx:
            page = await ctx.new_page()
            try:
                async def on_request(req: Any) -> None:
                    rtype = req.resource_type
                    if filter_type == "xhr" and rtype not in ("xhr", "fetch"):
                        return
                    if filter_type == "all":
                        pass
                    elif rtype not in ("xhr", "fetch"):
                        return
                    entries.append({
                        "method": req.method,
                        "url": str(req.url),
                        "type": rtype,
                    })

                page.on("request", on_request)
                await page.goto(url, wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(1000)
            finally:
                await page.close()
        return entries[:200]

    async def get_robots_txt(self, url: str) -> str:
        from chameleon.crawler.robots import RobotsTxt

        robots = RobotsTxt()
        base = f"{'https' if url.startswith('https') else 'http'}://{hostname(url)}"
        resp = await robots._client.get(f"{base}/robots.txt")  # noqa: SLF001
        await robots.close()
        return resp.text

    async def get_job_status(self, job_id: str) -> CrawlJob | None:
        return await self.scheduler.get_status(job_id)

    async def check_proxy(self, proxy_url: str) -> dict[str, Any]:
        from chameleon.anti_detection.proxy_manager import default_proxy_checker

        alive, latency = await default_proxy_checker(proxy_url)
        ip = ""
        if alive:
            try:
                import httpx

                async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
                    resp = await client.get("https://api.ipify.org?format=json")
                    if resp.status_code == 200:
                        ip = resp.json().get("ip", "")
            except Exception:
                pass
        return {"proxy": proxy_url, "alive": alive, "latency_ms": int(latency), "exit_ip": ip}

    async def diagnose_site(self, url: str) -> dict[str, Any]:
        """站点反爬画像：探测 UA 敏感度、验证码、JS 依赖。"""
        probes: dict[str, Any] = {}
        try:
            bare = await self.http_engine.fetch(FetchRequest(url=url))
            probes["bare_status"] = bare.status_code
            probes["bare_valid"] = self.router.validator.is_valid(bare)[0]
        except ChameleonError as exc:
            probes["bare_status"] = getattr(exc, "status_code", None)
            probes["bare_error"] = str(exc)
        faked = await self.router.fetch(FetchRequest(url=url, headers=self.identity.generate_headers(url)), mode="auto")
        probes["faked_engine"] = faked.engine.value
        probes["faked_status"] = faked.status_code
        probes["escalation_level"] = faked.escalation_level
        probes["captcha"] = self.captcha.detect(faked.content)
        probes["js_shell"] = self.router.validator.is_js_shell(faked)
        probes["content_length"] = len(faked.content)
        return {"url": url, **probes}

    async def close(self) -> None:
        await self.http_engine.close()
        await self.tls_engine.close()
        await self.browser_engine.close()
        if self.proxy_manager is not None:
            await self.proxy_manager.close()
        await self.robots.close()
