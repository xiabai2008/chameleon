"""TlsHttpEngine 覆盖率补强：BlockedError/RetryableError 分支（P4 补强）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from chameleon.core.exceptions import BlockedError, RetryableError
from chameleon.core.models import FetchRequest
from chameleon.engines.tls_engine import TlsHttpEngine


def _mock_tls_response(monkeypatch: pytest.MonkeyPatch, status_code: int) -> None:
    """注入 mock curl_cffi.requests.AsyncSession 返回指定状态码。"""
    fake_session = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status_code = status_code
    fake_resp.url = "http://example.com"
    fake_resp.content = b"<html></html>"
    fake_resp.headers = {"content-type": "text/html"}
    fake_session.__aenter__.return_value = fake_session
    fake_session.__aexit__.return_value = None
    fake_session.get = AsyncMock(return_value=fake_resp)
    mock_mod = MagicMock()
    mock_mod.AsyncSession.return_value = fake_session
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi.requests", mock_mod)
    agent = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "curl_cffi", agent)


async def test_tls_403_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl_cffi 返回 403 → BlockedError。"""
    _mock_tls_response(monkeypatch, 403)
    engine = TlsHttpEngine()
    with pytest.raises(BlockedError, match="403"):
        await engine.fetch(FetchRequest(url="http://example.com"))


async def test_tls_429_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl_cffi 返回 429 → BlockedError。"""
    _mock_tls_response(monkeypatch, 429)
    engine = TlsHttpEngine()
    with pytest.raises(BlockedError, match="429"):
        await engine.fetch(FetchRequest(url="http://example.com"))


async def test_tls_4xx_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """curl_cffi 返回 500 → RetryableError。"""
    _mock_tls_response(monkeypatch, 500)
    engine = TlsHttpEngine()
    with pytest.raises(RetryableError, match="500"):
        await engine.fetch(FetchRequest(url="http://example.com"))
