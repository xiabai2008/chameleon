"""HttpEngine 覆盖率补强：代理路径/超时/4xx/关闭（方案 P1.1 引擎扩展测试）。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from chameleon.core.exceptions import RetryableError
from chameleon.core.models import FetchRequest
from chameleon.engines.http_engine import HttpEngine


async def test_timeout_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """httpx.ReadTimeout → RetryableError（非 ConnectTimeout 的超时）。"""
    engine = HttpEngine(timeout=0.1)

    async def fake_get(*args: object, **kwargs: object) -> object:
        raise httpx.ReadTimeout("read timeout")

    monkeypatch.setattr(engine._client, "get", fake_get)

    with pytest.raises(RetryableError, match="timeout"):
        await engine.fetch(FetchRequest(url="http://example.com"))


async def test_4xx_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 403/429 的 4xx/5xx → RetryableError。"""
    engine = HttpEngine()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.url = "http://example.com"
    mock_resp.content = b"internal error"
    mock_resp.headers = httpx.Headers({"content-type": "text/html"})

    async def fake_get(*args: object, **kwargs: object) -> MagicMock:
        return mock_resp

    monkeypatch.setattr(engine._client, "get", fake_get)

    with pytest.raises(RetryableError, match="500"):
        await engine.fetch(FetchRequest(url="http://example.com"))


async def test_proxy_client_creation() -> None:
    """_client_for(proxy) 创建并缓存代理客户端。"""
    engine = HttpEngine()
    proxy = "http://proxy:8080"
    client = engine._client_for(proxy)  # noqa: SLF001
    assert proxy in engine._proxy_clients  # noqa: SLF001
    # 再次请求应命中缓存
    assert client is engine._client_for(proxy)  # noqa: SLF001


async def test_close_proxy_clients() -> None:
    """close() 同时关闭代理客户端。"""
    engine = HttpEngine()
    proxy = "http://proxy:8080"
    engine._client_for(proxy)  # noqa: SLF001
    assert proxy in engine._proxy_clients  # noqa: SLF001
    await engine.close()
    # 客户端已关闭，close 不会异常


async def test_ensure_loop_stale_proxy_cleanup() -> None:
    """跨 loop 时清理过期的代理客户端。"""
    engine = HttpEngine()
    stale_loop = asyncio.new_event_loop()
    engine._proxy_clients["http://proxy:8080"] = MagicMock()  # noqa: SLF001
    engine._proxy_loops["http://proxy:8080"] = stale_loop  # noqa: SLF001

    # _ensure_loop 检测到 loop 不匹配，清理代理条目
    engine._client_for(None)  # noqa: SLF001
    assert "http://proxy:8080" not in engine._proxy_clients  # noqa: SLF001
    stale_loop.close()
