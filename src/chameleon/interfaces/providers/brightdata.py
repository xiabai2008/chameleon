"""Bright Data Provider：Web Unlocker 代理形式对接（方案 P8-9）。"""

from __future__ import annotations

import httpx

from chameleon.core.models import ScrapeResult
from chameleon.interfaces.providers.base import BaseProvider, ProviderError, provider_result

DEFAULT_HOST = "brd.superproxy.io"
DEFAULT_PORT = 33335


class BrightDataProvider(BaseProvider):
    """Bright Data Web Unlocker：以住宅代理 + 解锁层形式转发请求。

    自有引擎搞不定的站点（强反爬）可经此兜底。需要客户号与 zone 密码。
    """

    name = "provider:brightdata"

    def __init__(
        self,
        customer: str,
        zone: str = "web_unlocker",
        password: str = "",
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 60.0,
    ) -> None:
        self._customer = customer
        self._zone = zone
        self._password = password
        self._host = host
        self._port = port
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    def proxy_url(self) -> str:
        """生成 Web Unlocker 代理 URL（客户号 + zone 作为用户名/密码）。"""
        user = f"brd-customer-{self._customer}-zone-{self._zone}"
        return f"http://{user}:{self._password}@{self._host}:{self._port}"

    async def scrape(self, url: str, *, output_format: str = "markdown") -> ScrapeResult | None:
        proxy = self.proxy_url()
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True, proxy=proxy) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            raise ProviderError(f"brightdata unlock failed: {exc}") from exc
        if resp.status_code != 200:
            return None
        from chameleon.pipeline.converter import Converter

        markdown = Converter().to_markdown(resp.text, url) if output_format == "markdown" else resp.text
        return provider_result(url, markdown, self.name)

    async def close(self) -> None:
        await self._client.aclose()
