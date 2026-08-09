"""第三方服务 Provider 抽象层（方案 P8-9）：自有引擎失败时兜底。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from chameleon.core.models import ScrapeResult


class BaseProvider(ABC):
    """第三方爬虫/搜索服务适配器基类。"""

    name: str = "base"

    @abstractmethod
    async def scrape(self, url: str, *, output_format: str = "markdown") -> ScrapeResult | None:
        """抓取单页。失败/不支持返回 None（调用方继续走自有引擎）。"""

    async def crawl(self, url: str, *, max_pages: int = 50, max_depth: int = 3) -> list[ScrapeResult] | None:
        """整站爬取。默认不支持。"""
        return None

    async def search(self, query: str, *, max_results: int = 5) -> list[dict[str, str]] | None:
        """搜索。默认不支持。"""
        return None

    async def close(self) -> None:
        """释放资源。默认无操作。"""
        return None


def provider_result(url: str, markdown: str, provider_name: str) -> ScrapeResult:
    """把第三方返回的 Markdown 包装为统一 ScrapeResult。"""
    from datetime import UTC, datetime

    from chameleon.core.exceptions import ScrapeStatus
    from chameleon.core.models import ContentOutput, ScrapeMetadata

    return ScrapeResult(
        status=ScrapeStatus.SUCCESS,
        url=url,
        content=ContentOutput(markdown=markdown),
        metadata=ScrapeMetadata(
            url=url,
            engine=provider_name,
            content_length=len(markdown),
            timestamp=datetime.now(UTC),
            crawled_at=datetime.now(UTC),
        ),
        error=None,
    )


class ProviderError(Exception):
    """第三方服务调用失败（网络/鉴权/限流）。"""
