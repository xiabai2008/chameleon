"""增强功能（P8）测试：API 逆向、策略学习、指纹随机化。"""

from __future__ import annotations

import pytest

from chameleon.anti_detection.fingerprint import FingerprintRandomizer
from chameleon.anti_detection.strategy_memory import StrategyMemory
from chameleon.core.models import FetchRequest
from chameleon.engines.api_engine import ApiDiscovery, ApiEngine


def test_fingerprint_randomizer_generates_distinct_scripts() -> None:
    scripts = FingerprintRandomizer.script_many(5)
    assert len(scripts) == 5
    assert len({s for s in scripts}) > 1  # 变体不同
    for script in scripts:
        assert "HTMLCanvasElement" in script
        assert "getParameter" in script


def test_strategy_memory_remember_and_retrieve() -> None:
    mem = StrategyMemory()
    assert mem.best_level("https://example.com/x") is None
    mem.remember("https://example.com/x", 4)
    assert mem.best_level("https://example.com/y") == 4  # 同域名共享
    assert mem.best_level("https://other.com/") is None


def test_strategy_memory_ttl_expiry() -> None:
    mem = StrategyMemory(ttl_seconds=0)
    mem.remember("https://example.com/x", 2)
    assert mem.best_level("https://example.com/x") is None


def test_api_discovery_filters() -> None:
    entries = [
        {"method": "GET", "url": "https://example.com/api/products", "type": "fetch"},
        {"method": "GET", "url": "https://example.com/main.js", "type": "script"},
        {"method": "GET", "url": "https://cdn.other.com/api/x", "type": "xhr"},
        {"method": "GET", "url": "https://example.com/logo.png", "type": "image"},
    ]
    candidates = ApiDiscovery.filter_api_entries(entries, "example.com")
    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://example.com/api/products"


@pytest.mark.asyncio
async def test_api_engine_json_endpoint(test_server: str) -> None:
    from chameleon.engines.http_engine import HttpEngine

    http = HttpEngine()
    api = ApiEngine(http)
    data = await api.call_json(f"{test_server}/json")
    assert data == {"name": "test", "items": [{"id": 1}, {"id": 2}]}
    await http.close()


@pytest.mark.asyncio
async def test_api_engine_rejects_non_json(test_server: str) -> None:
    from chameleon.core.exceptions import RetryableError
    from chameleon.engines.http_engine import HttpEngine

    http = HttpEngine()
    api = ApiEngine(http)
    with pytest.raises(RetryableError):
        await api.fetch(FetchRequest(url=f"{test_server}/static"))
    await http.close()


@pytest.mark.asyncio
async def test_sdk_call_api_and_analyze(test_server: str) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    data = await service.call_api(f"{test_server}/json")
    assert data["name"] == "test"
    endpoints = await service.analyze_api_endpoints(f"{test_server}/static")
    assert isinstance(endpoints, list)
    await service.close()
