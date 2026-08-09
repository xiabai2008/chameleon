"""智能路由器：按内容质量自动选择/升级采集策略（方案 5.1 + 7 升级链）。"""

from __future__ import annotations

import asyncio
import random
import time

from chameleon.anti_detection.captcha_solver import CaptchaRouter
from chameleon.anti_detection.identity_faker import IdentityFaker
from chameleon.anti_detection.proxy_manager import ProxyManager
from chameleon.anti_detection.strategy_memory import StrategyMemory
from chameleon.core.content_validator import ContentValidator
from chameleon.core.exceptions import (
    BlockedError,
    CaptchaRequiredError,
    ChameleonError,
    NotReachableError,
    ScrapeStatus,
)
from chameleon.core.models import (
    EngineType,
    FetchRequest,
    FetchResult,
    ScrapeMetadata,
    ScrapeResult,
)
from chameleon.engines.base import BaseEngine
from chameleon.engines.http_engine import HttpEngine
from chameleon.engines.tls_engine import TlsHttpEngine
from chameleon.infra.logging import get_logger
from chameleon.infra.metrics import Metrics
from chameleon.infra.session_pool import SessionPool
from chameleon.utils.url_utils import hostname

log = get_logger("router")
_metrics = Metrics()

_ESCALATABLE_REASONS = {"blocked_status_403", "blocked_status_429", "content_too_short", "anti_bot_marker"}


class SmartRouter:
    """决策链（方案 7 的 6 级升级链）：

    L0: HTTP 裸请求
    L1: HTTP + 自定义 UA + 完整请求头
    L2: HTTP + UA 轮换 + 代理 + 完整请求头
    L3: TLS 指纹模拟（curl_cffi）+ 代理
    L4: Browser + stealth
    L5: Browser + 行为模拟（引擎侧配置）
    L6: 验证码检测/处理（CaptchaRouter）
    """

    def __init__(
        self,
        http_engine: HttpEngine,
        browser_engine: BaseEngine | None = None,
        *,
        tls_engine: TlsHttpEngine | None = None,
        captcha_router: CaptchaRouter | None = None,
        memory: StrategyMemory | None = None,
        validator: ContentValidator | None = None,
        identity_faker: IdentityFaker | None = None,
        proxy_manager: ProxyManager | None = None,
        session_pool: SessionPool | None = None,
        max_retries: int = 3,
    ) -> None:
        self.http_engine = http_engine
        self.browser_engine = browser_engine
        self.tls_engine = tls_engine
        self.captcha_router = captcha_router
        self.memory = memory
        self.validator = validator or ContentValidator()
        self.identity = identity_faker or IdentityFaker()
        self.proxy_manager = proxy_manager
        self.session_pool = session_pool
        self.max_retries = max_retries

    async def fetch(self, request: FetchRequest, *, mode: str = "auto", force_browser: bool = False) -> FetchResult:
        """执行带升级链的采集，返回最终 FetchResult。

        mode: auto（逐级升级）| static（仅 HTTP 裸请求）| dynamic（仅 Browser）
        策略学习：auto 模式下从记忆的成功层级起跳（跳过已验证无效的低层级）。
        """
        if force_browser or mode == "dynamic":
            return await self._require_browser().fetch(request)

        if mode == "static":
            # static 语义：仅 HTTP 裸请求（带重试），不做内容质量升级
            result = await self._fetch_with_retry(self.http_engine, request)
            result.escalation_level = 0
            return result

        start_level = self.memory.best_level(request.url) if self.memory is not None else None
        if start_level:
            log.info("memory_hit", url=request.url, start_level=start_level)
        steps = self._build_steps(request, mode, start_level=start_level or 0)
        last_result: FetchResult | None = None
        last_reason: str | None = None
        for level, label, step_request in steps:
            result, ok, reason = await self._try_step(level, label, step_request)
            last_result, last_reason = result, reason
            if ok:
                if self.memory is not None and mode == "auto":
                    self.memory.remember(request.url, level)
                return result
            log.info("step_failed", url=request.url, level=level, label=label, reason=reason)

        assert last_result is not None
        # 全部失败：清除策略记忆（下次从全链路重新探测）
        if self.memory is not None and mode == "auto":
            self.memory.forget(request.url)
        # 最后一步是被反爬拦截（403/429）时，报告为 BlockedError 而非不可达
        if last_result.status_code in (403, 429):
            raise BlockedError(
                f"blocked for {request.url} (status {last_result.status_code})",
                status_code=last_result.status_code,
            )
        raise NotReachableError(
            f"all strategies failed for {request.url} (last reason: {last_reason})"
        )

    def _build_steps(
        self, request: FetchRequest, mode: str, *, start_level: int = 0
    ) -> list[tuple[int, str, FetchRequest]]:
        if mode == "static":
            return [(0, "bare", request)]
        steps: list[tuple[int, str, FetchRequest]] = [(0, "bare", request)]
        faked_headers = {**request.headers, **self.identity.generate_headers(request.url)}
        faked = request.model_copy(update={"headers": faked_headers})
        steps.append((1, "faked_headers", faked))
        if self.proxy_manager is not None:
            steps.append((2, "proxy+ua", faked))
        if self.tls_engine is not None:
            steps.append((3, "tls", faked))
        if self.browser_engine is not None:
            steps.append((4, "browser", request))
        if start_level > 0:
            # 策略学习：跳过历史已验证无效的低层级
            steps = [s for s in steps if s[0] >= start_level]
            if not steps:  # 起始层引擎未配置时回退全链路
                log.info("memory_step_unavailable", url=request.url, start_level=start_level)
                steps = [(0, "bare", request), (1, "faked_headers", faked)]
        return steps

    async def _try_step(
        self, level: int, label: str, request: FetchRequest
    ) -> tuple[FetchResult, bool, str | None]:
        engine: BaseEngine = self.http_engine
        try:
            if level == 0:
                result = await self._fetch_with_retry(engine, request)
            elif level == 1:
                engine = await self._session_for(request)
                result = await self._fetch_with_retry(engine, request)
            elif level == 2:
                engine = await self._session_for(request)
                proxy = await self._acquire_proxy()
                if proxy is None:
                    return FetchResult(url=request.url, engine=EngineType.HTTP, error="no proxy"), False, "no_proxy"
                result = await self._fetch_with_retry(engine, request.model_copy(update={"proxy": proxy}))
                if result.proxy_used:
                    await self._mark_proxy_success(proxy)
            elif level == 3:
                if self.tls_engine is None:
                    return FetchResult(url=request.url, engine=EngineType.HTTP_STEALTH, error="no tls engine"), False, "no_tls"
                engine = self.tls_engine
                proxy = await self._acquire_proxy()
                tls_request = request.model_copy(update={"proxy": proxy}) if proxy else request
                result = await self._fetch_with_retry(engine, tls_request)
                if proxy:
                    await self._mark_proxy_success(proxy)
            else:
                engine = self._require_browser()
                result = await self._fetch_with_retry(engine, request)
        except ChameleonError as exc:
            if level == 2 and request.proxy:
                await self._mark_proxy_failed(request.proxy)
            if level >= 1 and self.session_pool is not None and isinstance(engine, HttpEngine):
                await self.session_pool.mark_blocked(engine)
            return (
                FetchResult(
                    url=request.url,
                    engine=engine.name,
                    error=str(exc),
                    status_code=getattr(exc, "status_code", None),
                ),
                False,
                exc.suggested_action,
            )

        valid, reason = self.validator.is_valid(result)
        # 304 Not Modified：内容未变化（增量采集），直接返回不再升级
        if result.status_code == 304:
            result.escalation_level = level
            return result, True, None
        _metrics.observe_escalation(level)
        _metrics.record_request(engine=engine.name, status="ok" if valid else "invalid")
        # 验证码检测（L6）：内容含验证码特征 → 尝试解决，失败上报
        if self.captcha_router is not None:
            captcha_type = self.captcha_router.detect(result.content)
            if captcha_type is not None:
                solved, ctype, _text = await self.captcha_router.solve(result.content)
                if not solved:
                    raise CaptchaRequiredError(f"captcha triggered: {ctype}")
                reason = "captcha_solved_retry"
                return result, False, reason
        js_shell = valid and self.validator.is_js_shell(result)
        if valid and not js_shell:
            result.escalation_level = level
            return result, True, None
        if js_shell and level < 4 and self.browser_engine is not None:
            reason = "js_shell"
        return result, False, reason or "invalid"

    async def _session_for(self, request: FetchRequest) -> BaseEngine:
        if self.session_pool is None:
            return self.http_engine
        return await self.session_pool.acquire(hostname(request.url))

    async def _acquire_proxy(self) -> str | None:
        if self.proxy_manager is None:
            return None
        try:
            return await self.proxy_manager.get()
        except ChameleonError:
            return None

    async def _mark_proxy_failed(self, proxy: str) -> None:
        if self.proxy_manager is not None:
            await self.proxy_manager.mark_failed(proxy)

    async def _mark_proxy_success(self, proxy: str) -> None:
        if self.proxy_manager is not None:
            await self.proxy_manager.mark_success(proxy)

    def _require_browser(self) -> BaseEngine:
        if self.browser_engine is None:
            raise NotReachableError("browser engine not configured")
        return self.browser_engine

    async def scrape(
        self,
        url: str,
        *,
        mode: str = "auto",
        wait_for: str | None = None,
        proxy: str | None = None,
        timeout_seconds: float | None = None,
    ) -> ScrapeResult:
        """高层入口：fetch + 组装统一 ScrapeResult。"""
        request = FetchRequest(url=url, wait_for=wait_for, proxy=proxy, timeout=timeout_seconds)
        started = time.perf_counter()
        try:
            result = await self.fetch(request, mode=mode)
        except ChameleonError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            metadata = ScrapeMetadata(
                url=url, engine=self.http_engine.name, response_time_ms=elapsed_ms, retries=self.max_retries
            )
            return ScrapeResult(
                status=exc.status,
                url=url,
                metadata=metadata,
                error=str(exc),
                suggested_action=exc.suggested_action,
            )
        except Exception as exc:  # 未知异常兜底
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return ScrapeResult(
                status=ScrapeStatus.ERROR,
                url=url,
                metadata=ScrapeMetadata(url=url, engine=self.http_engine.name, response_time_ms=elapsed_ms),
                error=f"unexpected: {exc}",
                suggested_action="retry",
            )

        return ScrapeResult(
            status=ScrapeStatus.SUCCESS,
            url=url,
            metadata=ScrapeMetadata(
                url=url,
                final_url=result.final_url,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                content_length=len(result.content),
                engine=result.engine,
                escalation_level=result.escalation_level,
                proxy_used=result.proxy_used,
                retries=result.retries,
            ),
            content={"raw_html": result.content},
            links=[],
            images=[],
        )

    async def _fetch_with_retry(self, engine: BaseEngine, request: FetchRequest) -> FetchResult:
        """指数退避重试：抖动/5xx 重试，403/429 直接冒泡（交给升级链）。"""
        last_error: ChameleonError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await engine.fetch(request)
            except ChameleonError as exc:
                if exc.status in (ScrapeStatus.RATE_LIMITED, ScrapeStatus.CAPTCHA_REQUIRED):
                    raise
                last_error = exc
                if attempt < self.max_retries:
                    backoff = 0.5 * (2**attempt) + random.uniform(0, 0.5)
                    log.info("retry", url=request.url, attempt=attempt, error=str(exc), backoff=round(backoff, 2))
                    await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error
