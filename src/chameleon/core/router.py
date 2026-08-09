"""智能路由器：按内容质量自动选择/升级采集策略（方案 5.1）。"""

from __future__ import annotations

import asyncio
import random
import time

from chameleon.core.content_validator import ContentValidator
from chameleon.core.exceptions import ChameleonError, NotReachableError, ScrapeStatus
from chameleon.core.models import (
    FetchRequest,
    FetchResult,
    ScrapeMetadata,
    ScrapeResult,
)
from chameleon.engines.base import BaseEngine
from chameleon.infra.logging import get_logger

log = get_logger("router")

_FAIL_REASONS = {"blocked_status_403", "blocked_status_429", "content_too_short", "anti_bot_marker"}


def _is_escalatable(reason: str | None) -> bool:
    return reason in _FAIL_REASONS


class SmartRouter:
    """决策链：HTTP（裸）→ HTTP（stealth，P2 接入）→ Browser。

    escalation_level 对应方案 6 级升级链中的"最高到达层级"：
    Level 0: HTTP 裸请求
    Level 4: Browser 渲染
    （P2/P4 将补齐 Level 1-3、5-6）
    """

    def __init__(
        self,
        http_engine: BaseEngine,
        browser_engine: BaseEngine | None = None,
        *,
        validator: ContentValidator | None = None,
        max_retries: int = 3,
    ) -> None:
        self.http_engine = http_engine
        self.browser_engine = browser_engine
        self.validator = validator or ContentValidator()
        self.max_retries = max_retries

    async def fetch(self, request: FetchRequest, *, mode: str = "auto", force_browser: bool = False) -> FetchResult:
        """执行带升级链的采集，返回最终 FetchResult。

        mode: auto（自动决策）| static（仅 HTTP）| dynamic（仅 Browser）
        """
        if force_browser or mode == "dynamic":
            if self.browser_engine is None:
                raise NotReachableError("browser engine not configured")
            return await self.browser_engine.fetch(request)

        result = await self._fetch_with_retry(self.http_engine, request)
        valid, reason = self.validator.is_valid(result)
        should_escalate = False
        if valid:
            should_escalate = self.validator.is_js_shell(result)
            if should_escalate:
                reason = "js_shell"
        else:
            should_escalate = _is_escalatable(reason)

        if should_escalate and mode == "auto" and self.browser_engine is not None:
            log.info("escalating_to_browser", url=request.url, reason=reason)
            browser_result = await self._fetch_with_retry(self.browser_engine, request)
            browser_result = self._apply_escalation_metadata(browser_result, 4)
            return browser_result

        result = self._apply_escalation_metadata(result, 0)
        return result

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

    @staticmethod
    def _apply_escalation_metadata(result: FetchResult, level: int) -> FetchResult:
        result.escalation_level = level
        result.retries = 0
        return result
