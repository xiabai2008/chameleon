"""TLS 指纹伪装引擎：curl_cffi impersonate 浏览器 JA3/JA4 指纹（方案 4-2 Level 3）。"""

from __future__ import annotations

import time

from chameleon.core.exceptions import BlockedError, NotReachableError, RetryableError
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.engines.base import BaseEngine
from chameleon.utils.encoding import decode_html

DEFAULT_IMPERSONATE = "chrome124"


class TlsHttpEngine(BaseEngine):
    """curl_cffi 引擎：TLS 指纹伪装 + HTTP/2，兼容 requests 生态。"""

    name = EngineType.HTTP_STEALTH

    def __init__(self, impersonate: str = DEFAULT_IMPERSONATE, timeout: float = 15.0) -> None:
        self.impersonate = impersonate
        self._timeout = timeout

    async def fetch(self, request: FetchRequest) -> FetchResult:
        from curl_cffi.requests import AsyncSession

        started = time.perf_counter()
        headers = dict(request.headers)
        try:
            async with AsyncSession(impersonate=self.impersonate, timeout=self._timeout) as session:
                resp = await session.get(request.url, headers=headers or None, proxies={"http": request.proxy, "https": request.proxy} if request.proxy else None)
        except Exception as exc:
            raise NotReachableError(f"tls engine failed for {request.url}: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        content = decode_html(resp.content, dict(resp.headers))
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

    async def close(self) -> None:
        pass
