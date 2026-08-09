"""Firecrawl Provider：官方 API 对接（方案 P8-9）。"""

from __future__ import annotations

import httpx

from chameleon.core.models import ScrapeResult
from chameleon.interfaces.providers.base import BaseProvider, ProviderError, provider_result

DEFAULT_BASE_URL = "https://api.firecrawl.dev"


class FirecrawlProvider(BaseProvider):
    """Firecrawl API 客户端：scrape/search/crawl 全部走官方端点。

    文档：https://docs.firecrawl.dev/api-reference
    """

    name = "provider:firecrawl"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 60.0) -> None:
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    async def scrape(self, url: str, *, output_format: str = "markdown") -> ScrapeResult | None:
        if output_format not in ("markdown", "html"):
            return None
        try:
            resp = await self._client.post(
                f"{self._base}/v1/scrape",
                json={"url": url, "formats": [output_format], "onlyMainContent": True},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"firecrawl scrape failed: {exc}") from exc
        if resp.status_code == 401:
            raise ProviderError("firecrawl api key invalid")
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("success"):
            return None
        content = (data.get("data") or {}).get(output_format)
        if not content:
            return None
        return provider_result(url, str(content), self.name)

    async def search(self, query: str, *, max_results: int = 5) -> list[dict[str, str]] | None:
        try:
            resp = await self._client.post(
                f"{self._base}/v1/search",
                json={"query": query, "limit": max_results},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"firecrawl search failed: {exc}") from exc
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("success"):
            return None
        results: list[dict[str, str]] = []
        for item in (data.get("data") or [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("description", ""),
            })
        return results

    async def crawl(self, url: str, *, max_pages: int = 50, max_depth: int = 3) -> list[ScrapeResult] | None:
        try:
            resp = await self._client.post(
                f"{self._base}/v1/crawl",
                json={"url": url, "limit": max_pages, "maxDepth": max_depth},
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"firecrawl crawl failed: {exc}") from exc
        if resp.status_code not in (200, 201):
            return None
        job = resp.json().get("data") or {}
        job_id = job.get("id")
        if not job_id:
            return None
        # 异步任务：轮询结果
        for _ in range(30):
            try:
                status = await self._client.get(f"{self._base}/v1/crawl/{job_id}")
            except httpx.HTTPError:
                break
            payload = status.json().get("data") or {}
            if payload.get("status") in ("completed", "failed"):
                break
            import asyncio

            await asyncio.sleep(2)
        pages: list[ScrapeResult] = []
        for page in (payload.get("pages") or []) if "payload" in locals() else []:
            md = page.get("markdown")
            if md:
                pages.append(provider_result(page.get("url", url), str(md), self.name))
        return pages or None

    async def close(self) -> None:
        await self._client.aclose()
