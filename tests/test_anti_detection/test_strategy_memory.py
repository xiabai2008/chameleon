"""策略学习接入升级链（P8-4 集成）测试。"""

from __future__ import annotations

import pytest

from chameleon.anti_detection.proxy_manager import ProxyManager
from chameleon.anti_detection.strategy_memory import StrategyMemory
from chameleon.core.config import ProxyConfig
from chameleon.core.exceptions import BlockedError, NotReachableError
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.core.router import SmartRouter
from chameleon.engines.base import BaseEngine


def _ok_result() -> FetchResult:
    return FetchResult(url="http://x", status_code=200, content="x" * 600 + "有效内容" * 20)


class _CountEngine(BaseEngine):
    """按序列返回结果/抛异常，记录每次调用的请求头。"""

    name = EngineType.HTTP

    def __init__(self, *results: FetchResult | Exception) -> None:
        self.results = list(results)
        self.calls: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request)
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        pass


def _fake_proxy() -> ProxyManager:
    async def checker(_proxy: str) -> tuple[bool, float]:
        return True, 100.0

    return ProxyManager(ProxyConfig(enabled=True, static_list=["http://fake:8080"]), checker=checker)


def _router_with(engine: _CountEngine, memory: StrategyMemory | None = None) -> SmartRouter:
    return SmartRouter(http_engine=engine, memory=memory, proxy_manager=_fake_proxy())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_memory_skips_proven_invalid_levels() -> None:
    """首次 L0/L1 失败、L2 成功 → 记忆 level 2；二次直接从 L2 起跳。"""
    engine = _CountEngine(
        BlockedError("403", status_code=403),
        BlockedError("403", status_code=403),
        _ok_result(),
        _ok_result(),  # 第二次 fetch 从 L2 开始
    )
    memory = StrategyMemory()
    router = _router_with(engine, memory)

    first = await router.fetch(FetchRequest(url="http://example.com/page"))
    assert first.escalation_level == 2
    assert memory.best_level("http://example.com/page") == 2
    assert len(engine.calls) == 3

    second = await router.fetch(FetchRequest(url="http://example.com/other"))
    assert second.escalation_level == 2
    # 记忆起跳：第二次只调用 1 次（L2），L0/L1 不再尝试
    assert len(engine.calls) == 4
    assert engine.calls[3].headers.get("User-Agent")  # L2 使用伪装头


@pytest.mark.asyncio
async def test_memory_upgrades_when_remembered_level_fails() -> None:
    """记忆层失败 → 向更高层升级成功 → 记忆更新为更高层。"""
    engine = _CountEngine(
        BlockedError("403", status_code=403),  # L1 失败
        _ok_result(),  # L2 成功
    )
    memory = StrategyMemory()
    memory.remember("http://example.com/page", 1)
    router = _router_with(engine, memory)

    result = await router.fetch(FetchRequest(url="http://example.com/page"))
    assert result.escalation_level == 2
    assert memory.best_level("http://example.com/page") == 2


@pytest.mark.asyncio
async def test_memory_cleared_on_total_failure() -> None:
    """记忆层也失败且无更高层可用 → 全部失败 → 记忆清除。"""
    engine = _CountEngine(BlockedError("403", status_code=403), BlockedError("403", status_code=403))
    memory = StrategyMemory()
    memory.remember("http://example.com/page", 1)
    router = _router_with(engine, memory)

    with pytest.raises((BlockedError, NotReachableError)):
        await router.fetch(FetchRequest(url="http://example.com/page"))
    assert memory.best_level("http://example.com/page") is None


@pytest.mark.asyncio
async def test_memory_ignored_in_static_mode() -> None:
    """static 模式不做记忆（L0 直达）。"""
    engine = _CountEngine(_ok_result())
    memory = StrategyMemory()
    memory.remember("http://example.com/page", 2)
    router = _router_with(engine, memory)

    result = await router.fetch(FetchRequest(url="http://example.com/page"), mode="static")
    assert result.escalation_level == 0
    assert memory.best_level("http://example.com/page") == 2  # 未被覆盖


@pytest.mark.asyncio
async def test_memory_off_when_not_configured() -> None:
    """未配置 memory 时行为与之前一致（从 L0 全链路）。"""
    engine = _CountEngine(
        BlockedError("403", status_code=403),
        _ok_result(),
    )
    router = _router_with(engine)  # 无 memory
    result = await router.fetch(FetchRequest(url="http://example.com/page"))
    assert result.escalation_level == 1
    assert len(engine.calls) == 2
