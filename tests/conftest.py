"""测试配置与公共 fixtures。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from tests.fixtures.anti_bot_site import create_anti_bot_app
from tests.fixtures.site import create_test_app

TEST_PORT = 8765
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"
ANTI_BOT_PORT = 8766
ANTI_BOT_URL = f"http://127.0.0.1:{ANTI_BOT_PORT}"


class _ServerThread(threading.Thread):
    def __init__(self, app: FastAPI, port: int) -> None:
        super().__init__(daemon=True)
        self._config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", ws="wsproto")
        self._server = uvicorn.Server(self._config)

    def run(self) -> None:
        asyncio.run(self._server.serve())


@pytest.fixture(scope="session")
def test_server() -> AsyncIterator[str]:
    """会话级测试站点服务器，返回 BASE_URL。"""
    thread = _ServerThread(create_test_app(), TEST_PORT)
    thread.start()
    asyncio.run(_server_wait_ready(TEST_PORT))
    yield BASE_URL


@pytest.fixture(scope="session")
def anti_bot_server() -> AsyncIterator[str]:
    """反爬模拟站，返回 ANTI_BOT_URL。"""
    thread = _ServerThread(create_anti_bot_app(), ANTI_BOT_PORT)
    thread.start()
    asyncio.run(_server_wait_ready(ANTI_BOT_PORT))
    yield ANTI_BOT_URL


async def _server_wait_ready(port: int) -> None:
    async with httpx.AsyncClient(timeout=0.5) as client:
        for _ in range(100):
            try:
                await client.get(f"http://127.0.0.1:{port}/short")
                return
            except Exception:
                await asyncio.sleep(0.05)
    raise RuntimeError("test server did not start")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """pytest-asyncio 使用独立事件循环，避免跨测试污染。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def _reset_contextvars() -> Iterator[None]:
    from chameleon.infra.logging import _request_id

    yield
    _request_id.set(None)
