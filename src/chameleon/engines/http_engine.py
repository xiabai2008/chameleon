"""HTTP 引擎：httpx async，编码检测、超时、异常映射、跨 loop 安全。"""

from __future__ import annotations

import asyncio
import time

import httpx

from chameleon.core.exceptions import BlockedError, NotReachableError, RetryableError
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.engines.base import BaseEngine
from chameleon.utils.encoding import decode_html

DEFAULT_TIMEOUT = 15.0


class HttpEngine(BaseEngine):
    """静态页采集引擎（httpx）。

    stealth_mode=False 时使用标准 httpx；P4 将提供 curl_cffi 的 TLS 伪装变体。
    """

    name = EngineType.HTTP

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT, client: httpx.AsyncClient | None = None) -> None:
        self._timeout = timeout
        self._client = client or self._new_client()
        self._client_loop: asyncio.AbstractEventLoop | None = None
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}
        self._proxy_loops: dict[str, asyncio.AbstractEventLoop] = {}

    def _new_client(self, *, proxy: str | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            http2=True,
            headers={"Accept-Encoding": "gzip, deflate, br"},
            proxy=proxy,
        )

    def _ensure_loop(self) -> None:
        """httpx client 连接池绑定创建时的 loop；跨 loop 复用会报 'Event loop is closed'。
        检测到 loop 变化时重建 client。"""
        current = asyncio.get_running_loop()
        if self._client_loop is not current:
            if self._client_loop is not None:
                self._client = self._new_client()
            self._client_loop = current
        for proxy, loop in list(self._proxy_loops.items()):
            if loop is not current:
                self._proxy_clients.pop(proxy, None)
                self._proxy_loops.pop(proxy, None)

    def _client_for(self, proxy: str | None) -> httpx.AsyncClient:
        self._ensure_loop()
        if proxy is None:
            return self._client
        client = self._proxy_clients.get(proxy)
        if client is None:
            client = self._new_client(proxy=proxy)
            self._proxy_clients[proxy] = client
            self._proxy_loops[proxy] = asyncio.get_running_loop()
        return client

    async def fetch(self, request: FetchRequest) -> FetchResult:
        started = time.perf_counter()
        client = self._client_for(request.proxy)
        # httpx.Headers 大小写不敏感：request.headers 能正确覆盖 client 默认头（如 user-agent）
        headers = httpx.Headers(client.headers)
        for key, value in request.headers.items():
            headers[key] = value
        try:
            resp = await client.get(
                request.url,
                headers=headers,
                cookies={c.get("name", ""): c.get("value", "") for c in request.cookies} or None,
            )
        except httpx.ConnectTimeout as exc:
            raise NotReachableError(f"connect timeout: {request.url}") from exc
        except httpx.TimeoutException as exc:
            raise RetryableError(f"timeout: {request.url}") from exc
        except httpx.TransportError as exc:
            raise NotReachableError(f"transport error for {request.url}: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        content = decode_html(resp.content, resp.headers)
        result = FetchResult(
            url=request.url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            content=content,
            headers={k: v for k, v in resp.headers.items()},
            engine=self.name,
            proxy_used=request.proxy,
            response_time_ms=elapsed_ms,
        )
        if resp.status_code == 403 or resp.status_code == 429:
            raise BlockedError(f"blocked with status {resp.status_code}", status_code=resp.status_code)
        if resp.status_code >= 400:
            raise RetryableError(f"http {resp.status_code} for {request.url}")
        return result

    async def clear_cookies(self) -> None:
        self._client.cookies.clear()

    async def close(self) -> None:
        await self._client.aclose()
        for client in self._proxy_clients.values():
            await client.aclose()
