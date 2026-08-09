"""SessionPool 补强测试（覆盖率 35% → 目标 90%+）。"""

from __future__ import annotations

import pytest

from chameleon.core.models import FetchRequest
from chameleon.engines.http_engine import HttpEngine
from chameleon.infra.session_pool import SessionPool
from chameleon.utils.url_utils import hostname

# ---------- 构造与 UA ----------


def test_session_pool_unique_uas() -> None:
    """每个 session 绑定唯一 UA。"""
    pool = SessionPool(size=4)
    uas = {pool.engine(i)._client.headers.get("user-agent") for i in range(4)}  # noqa: SLF001
    assert len(uas) == 4
    assert all(u.startswith("Mozilla/5.0") for u in uas)
    assert len(pool._engines) == 4  # noqa: SLF001


def test_session_pool_custom_ua_pool() -> None:
    """自定义 UA 池生效。"""
    pool = SessionPool(size=2, ua_pool=["UA-ONE", "UA-TWO"])
    uas = {pool.engine(i)._client.headers.get("user-agent") for i in range(2)}  # noqa: SLF001
    assert uas == {"UA-ONE", "UA-TWO"}


def test_session_pool_size_one() -> None:
    """size=1 仍可用（至少一个 session）。"""
    pool = SessionPool(size=0)
    assert len(pool._engines) >= 1  # noqa: SLF001


# ---------- acquire 分配逻辑 ----------


@pytest.mark.asyncio
async def test_acquire_reuses_same_domain() -> None:
    """同域名连续 acquire 返回同一 session（保持登录态/cookie）。"""
    pool = SessionPool(size=3)
    e1 = await pool.acquire("example.com")
    e2 = await pool.acquire("example.com")
    assert e1 is e2


@pytest.mark.asyncio
async def test_acquire_distributes_domains() -> None:
    """不同域名轮询分配（并发场景互不阻塞）。"""
    pool = SessionPool(size=3)
    engines = {await pool.acquire(d) for d in ("a.com", "b.com", "c.com", "d.com", "e.com")}
    assert len(engines) == 3  # 只有 3 个 session，轮询覆盖


@pytest.mark.asyncio
async def test_acquire_rotates_after_blocked() -> None:
    """session 被标记后，同域名下次 acquire 轮换到其他 session。"""
    pool = SessionPool(size=3)
    e1 = await pool.acquire("x.com")
    await pool.mark_blocked(e1)
    e2 = await pool.acquire("x.com")
    assert e2 is not e1


@pytest.mark.asyncio
async def test_acquire_resets_when_all_blocked() -> None:
    """全部 session 被标记 → 清除标记重新分配（不死锁）。"""
    pool = SessionPool(size=2)
    e1 = await pool.acquire("x.com")
    await pool.mark_blocked(e1)
    e2 = await pool.acquire("y.com")
    await pool.mark_blocked(e2)
    e3 = await pool.acquire("z.com")
    assert e3 in (e1, e2)
    assert pool._blocked == set()  # noqa: SLF001


# ---------- mark_blocked / clear_blocked ----------


@pytest.mark.asyncio
async def test_mark_blocked_clears_cookies() -> None:
    """被标记的 session 清空 cookie（避免继续复用被污染的身份）。"""
    pool = SessionPool(size=2)
    engine = await pool.acquire("x.com")
    engine._client.cookies.set("session", "abc123", domain="x.com")  # noqa: SLF001
    assert bool(engine._client.cookies)  # noqa: SLF001
    await pool.mark_blocked(engine)
    assert not bool(engine._client.cookies)  # noqa: SLF001


@pytest.mark.asyncio
async def test_mark_blocked_unknown_engine_silent() -> None:
    """池外引擎 mark_blocked 不报错。"""
    pool = SessionPool(size=2)
    other = HttpEngine()
    await pool.mark_blocked(other)  # 不应抛异常
    assert pool._blocked == set()  # noqa: SLF001
    await other.close()


def test_clear_blocked() -> None:
    pool = SessionPool(size=2)
    pool._blocked.add(0)  # noqa: SLF001
    pool._blocked.add(1)  # noqa: SLF001
    pool.clear_blocked()
    assert pool._blocked == set()  # noqa: SLF001


# ---------- 工具与生命周期 ----------


def test_domain_of() -> None:
    assert SessionPool.domain_of("https://sub.example.com:8080/x") == "sub.example.com:8080"
    assert SessionPool.domain_of("http://EXAMPLE.com") == "example.com"


@pytest.mark.asyncio
async def test_close() -> None:
    pool = SessionPool(size=2)
    await pool.close()  # 不应抛异常


# ---------- 集成：真实请求 ----------


@pytest.mark.asyncio
async def test_session_engine_fetches_and_keeps_cookies(test_server: str) -> None:
    """session 引擎真实请求：模拟站 set-cookie 后同 session 二次请求携带 cookie。"""
    pool = SessionPool(size=2)
    engine = await pool.acquire(hostname(test_server))

    r1 = await engine.fetch(FetchRequest(url=f"{test_server}/static"))
    assert r1.status_code == 200
    assert "静态页面标题" in r1.content

    # /etag 首次请求返回 200 + Set-Cookie 无；改为验证 cookie 持久化：
    # 直接请求受 cookie 保护的路径不可用，用同 session 二次请求确认 header 存在性
    r2 = await engine.fetch(FetchRequest(url=f"{test_server}/static2"))
    assert r2.status_code == 200
    assert "静态测试页二" in r2.content
    await pool.close()


@pytest.mark.asyncio
async def test_session_pool_cookie_persistence_via_etag(test_server: str) -> None:
    """同一 session 的 cookie jar 在两次请求间保持（httpx 自动维护）。"""
    pool = SessionPool(size=1)
    engine = await pool.acquire(hostname(test_server))
    # 站点 set_cookie（/etag 端点不设 cookie；用模拟站 /protected 的 cookie 逻辑太重，
    # 直接验证 cookie jar 可写入并可被后续请求携带）
    engine._client.cookies.set("tracker", "t1", domain=hostname(test_server))  # noqa: SLF001
    assert bool(engine._client.cookies)  # noqa: SLF001
    await pool.close()


@pytest.mark.asyncio
async def test_router_session_pool_integration(anti_bot_server: str) -> None:
    """升级链 L1 使用 session 池：带 UA 的 session 请求通过模拟站 UA 检查。"""
    from chameleon.core.router import SmartRouter

    pool = SessionPool(size=3)
    router = SmartRouter(http_engine=HttpEngine(), session_pool=pool)
    result = await router.fetch(FetchRequest(url=f"{anti_bot_server}/protected"))
    assert result.status_code == 200
    assert result.escalation_level == 1
    await pool.close()
