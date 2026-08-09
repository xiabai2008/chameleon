"""proxy_manager 补强测试（覆盖率 45% → 90%+）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from chameleon.anti_detection.proxy_manager import ProxyManager, default_proxy_checker
from chameleon.core.config import ProxyConfig
from chameleon.core.exceptions import ProxyUnavailableError

# ---------- default_proxy_checker ----------


@pytest.mark.asyncio
async def test_default_checker_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import chameleon.anti_detection.proxy_manager as mod

    class _Resp:
        status_code = 204

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def get(self, url: str) -> _Resp:
            return _Resp()

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeClient)
    alive, latency = await default_proxy_checker("http://p:8080", probe_url="http://probe.local")
    assert alive is True
    assert latency >= 0


@pytest.mark.asyncio
async def test_default_checker_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import chameleon.anti_detection.proxy_manager as mod

    class _FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        async def get(self, url: str) -> Any:
            raise ConnectionError("down")

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeClient)
    alive, latency = await default_proxy_checker("http://p:8080")
    assert (alive, latency) == (False, 0.0)


# ---------- add / 内存池 ----------


@pytest.mark.asyncio
async def test_add_new_and_existing() -> None:
    mgr = ProxyManager(ProxyConfig())
    await mgr.add("http://p1:8080", region="cn")
    assert mgr._pool["http://p1:8080"].region == "cn"  # noqa: SLF001
    assert mgr._pool["http://p1:8080"].score == 50  # noqa: SLF001
    await mgr.add("http://p1:8080", region="us")  # 已存在 → 跳过
    assert mgr._pool["http://p1:8080"].region == "cn"  # noqa: SLF001


@pytest.mark.asyncio
async def test_get_memory_region_filter() -> None:
    config = ProxyConfig(static_list=["http://cn1:8080", "http://us1:8080"])
    mgr = ProxyManager(config)
    mgr._pool["http://cn1:8080"].region = "cn"  # noqa: SLF001
    mgr._pool["http://us1:8080"].region = "us"  # noqa: SLF001
    for _ in range(10):
        assert await mgr.get(region="cn") == "http://cn1:8080"


@pytest.mark.asyncio
async def test_get_memory_no_candidates() -> None:
    config = ProxyConfig(static_list=["http://dead:8080"])
    mgr = ProxyManager(config)
    await mgr.mark_failed("http://dead:8080", delta=-50)
    with pytest.raises(ProxyUnavailableError):
        await mgr.get()


# ---------- 评分机制 ----------


@pytest.mark.asyncio
async def test_mark_failed_memory() -> None:
    mgr = ProxyManager(ProxyConfig(static_list=["http://p:8080"]))
    await mgr.mark_failed("http://p:8080", delta=-10)
    assert mgr._pool["http://p:8080"].score == 40  # noqa: SLF001
    await mgr.mark_failed("http://p:8080", delta=-30)
    assert mgr._pool["http://p:8080"].alive is False  # noqa: SLF001
    assert mgr._pool["http://p:8080"].score == 10  # noqa: SLF001


@pytest.mark.asyncio
async def test_mark_failed_floor_zero() -> None:
    mgr = ProxyManager(ProxyConfig(static_list=["http://p:8080"]))
    await mgr.mark_failed("http://p:8080", delta=-500)
    assert mgr._pool["http://p:8080"].score == 0  # noqa: SLF001


@pytest.mark.asyncio
async def test_mark_success_revives() -> None:
    mgr = ProxyManager(ProxyConfig(static_list=["http://p:8080"]))
    await mgr.mark_failed("http://p:8080", delta=-50)
    assert mgr._pool["http://p:8080"].alive is False  # noqa: SLF001
    await mgr.mark_success("http://p:8080", delta=5)
    assert mgr._pool["http://p:8080"].alive is True  # noqa: SLF001
    assert mgr._pool["http://p:8080"].score == 5  # noqa: SLF001


@pytest.mark.asyncio
async def test_mark_success_caps_at_100() -> None:
    mgr = ProxyManager(ProxyConfig(static_list=["http://p:8080"]))
    await mgr.mark_success("http://p:8080", delta=200)
    assert mgr._pool["http://p:8080"].score == 100  # noqa: SLF001


@pytest.mark.asyncio
async def test_mark_unknown_proxy_silent() -> None:
    mgr = ProxyManager(ProxyConfig())
    await mgr.mark_failed("http://ghost:8080")
    await mgr.mark_success("http://ghost:8080")
    assert mgr._pool == {}  # noqa: SLF001


# ---------- 健康检查 ----------


@pytest.mark.asyncio
async def test_health_check_once() -> None:
    async def checker(proxy: str) -> tuple[bool, float]:
        return proxy == "http://good:8080", 120.0

    mgr = ProxyManager(
        ProxyConfig(static_list=["http://good:8080", "http://bad:8080"]),
        checker=checker,
    )
    await mgr.health_check_once()
    good = mgr._pool["http://good:8080"]  # noqa: SLF001
    bad = mgr._pool["http://bad:8080"]  # noqa: SLF001
    assert good.alive is True
    assert good.response_time_ms == 120
    assert good.last_checked is not None
    assert bad.alive is False
    assert bad.score < 50  # 死亡代理降分


@pytest.mark.asyncio
async def test_health_check_loop_runs_and_stops() -> None:
    calls: list[str] = []

    async def checker(proxy: str) -> tuple[bool, float]:
        calls.append(proxy)
        return True, 10.0

    mgr = ProxyManager(ProxyConfig(static_list=["http://p:8080"]), checker=checker)
    task = asyncio.create_task(mgr.health_check_loop(interval=0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) >= 2  # 循环至少跑了两轮


# ---------- Redis 后端 ----------


class _FakeRedisPool:
    """redis.asyncio 子集（smembers/zscore/zincrby/aclose）。"""

    def __init__(self, proxies: set[str], scores: dict[str, float] | None = None) -> None:
        self.proxies = proxies
        self.scores = dict(scores or {})
        self.zincrby_calls: list[tuple[str, int, str]] = []

    async def smembers(self, key: str) -> set[str]:
        return set(self.proxies)

    async def zscore(self, key: str, proxy: str) -> float | None:
        return self.scores.get(proxy)

    async def zincrby(self, key: str, delta: int, proxy: str) -> None:
        self.scores[proxy] = self.scores.get(proxy, 50.0) + delta
        self.zincrby_calls.append((key, delta, proxy))

    async def aclose(self) -> None:
        pass


def _redis_manager(fake: _FakeRedisPool) -> ProxyManager:
    return ProxyManager(
        ProxyConfig(pool_type="redis", redis_url="redis://localhost:6379/0"),
        redis_client=fake,
    )


@pytest.mark.asyncio
async def test_redis_get_region() -> None:
    fake = _FakeRedisPool({"http://p1:8080", "http://p2:8080"})
    mgr = _redis_manager(fake)
    got = {await mgr.get(region="any") for _ in range(20)}
    assert got == {"http://p1:8080", "http://p2:8080"}


@pytest.mark.asyncio
async def test_redis_get_excludes_low_score() -> None:
    fake = _FakeRedisPool({"http://good:8080", "http://bad:8080"}, scores={"http://bad:8080": 10.0})
    mgr = _redis_manager(fake)
    for _ in range(10):
        assert await mgr.get() == "http://good:8080"


@pytest.mark.asyncio
async def test_redis_get_empty() -> None:
    mgr = _redis_manager(_FakeRedisPool(set()))
    with pytest.raises(ProxyUnavailableError):
        await mgr.get()


@pytest.mark.asyncio
async def test_redis_get_exhausted() -> None:
    fake = _FakeRedisPool({"http://low:8080"}, scores={"http://low:8080": 5.0})
    mgr = _redis_manager(fake)
    with pytest.raises(ProxyUnavailableError):
        await mgr.get()


@pytest.mark.asyncio
async def test_redis_mark_failed() -> None:
    fake = _FakeRedisPool({"http://p:8080"})
    mgr = _redis_manager(fake)
    await mgr.mark_failed("http://p:8080", delta=-10)
    assert fake.scores["http://p:8080"] == 40.0


@pytest.mark.asyncio
async def test_redis_mark_success() -> None:
    fake = _FakeRedisPool({"http://p:8080"}, scores={"http://p:8080": 40.0})
    mgr = _redis_manager(fake)
    await mgr.mark_success("http://p:8080", delta=5)
    assert fake.scores["http://p:8080"] == 45.0


@pytest.mark.asyncio
async def test_redis_close() -> None:
    fake = _FakeRedisPool(set())
    mgr = _redis_manager(fake)
    await mgr.close()  # aclose 不抛


@pytest.mark.asyncio
async def test_redis_from_url_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """未传 redis_client 时用 Redis.from_url 构造。"""
    from_redis_calls: list[str] = []

    class _FakeRedisClass:
        @classmethod
        def from_url(cls, url: str) -> str:
            from_redis_calls.append(url)
            return "fake-redis"

    monkeypatch.setattr("redis.asyncio.Redis.from_url", _FakeRedisClass.from_url)
    mgr = ProxyManager(ProxyConfig(pool_type="redis", redis_url="redis://x:6379/0"))
    assert from_redis_calls == ["redis://x:6379/0"]
    assert mgr._redis == "fake-redis"  # noqa: SLF001
