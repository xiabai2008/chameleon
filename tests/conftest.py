"""测试配置与公共 fixtures。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest


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
