"""cache 补强测试（覆盖率 67% → 90%+）。"""

from __future__ import annotations

import pytest

from chameleon.infra.cache import CacheLayer, TTLCache

# ---------- TTLCache ----------


def test_ttl_get_miss() -> None:
    cache = TTLCache(ttl=60)
    assert cache.get("missing") is None


def test_ttl_set_get() -> None:
    cache = TTLCache(ttl=60)
    cache.set("k", {"v": 1})
    assert cache.get("k") == {"v": 1}


def test_ttl_expiry() -> None:
    cache = TTLCache(ttl=0)  # 立即过期
    cache.set("k", "v")
    assert cache.get("k") is None


def test_ttl_expiry_by_time(monkeypatch: pytest.MonkeyPatch) -> None:
    import chameleon.infra.cache as mod

    fake_now = [100.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: fake_now[0])

    cache = TTLCache(ttl=30)
    cache.set("k", "v")
    assert cache.get("k") == "v"

    fake_now[0] = 130.1  # 过期
    assert cache.get("k") is None
    assert cache._store == {}  # 过期项被清理  # noqa: SLF001


def test_ttl_capacity_evicts_oldest() -> None:
    cache = TTLCache(ttl=60, capacity=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)
    assert cache.get("a") is None  # 最早的被淘汰
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache._store) == 2  # noqa: SLF001


def test_ttl_clear() -> None:
    cache = TTLCache(ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache._store == {}  # noqa: SLF001
    assert cache.get("a") is None


# ---------- CacheLayer（enabled） ----------


def test_cache_layer_raw_roundtrip() -> None:
    layer = CacheLayer()
    assert layer.get_raw("http://x") is None
    layer.set_raw("http://x", {"html": "<p>a</p>"})
    assert layer.get_raw("http://x") == {"html": "<p>a</p>"}


def test_cache_layer_markdown_roundtrip() -> None:
    layer = CacheLayer()
    assert layer.get_markdown("u|md") is None
    layer.set_markdown("u|md", "# Title")
    assert layer.get_markdown("u|md") == "# Title"


def test_cache_layer_markdown_type_mismatch() -> None:
    layer = CacheLayer()
    layer.markdown.set("k", {"not": "str"})  # noqa: SLF001
    assert layer.get_markdown("k") is None


def test_cache_layer_extracted_roundtrip() -> None:
    layer = CacheLayer()
    assert layer.get_extracted("u|schema") is None
    layer.set_extracted("u|schema", {"title": "t"})
    assert layer.get_extracted("u|schema") == {"title": "t"}


def test_cache_layer_extracted_type_mismatch() -> None:
    layer = CacheLayer()
    layer.extracted.set("k", "not-a-dict")  # noqa: SLF001
    assert layer.get_extracted("k") is None


def test_cache_layer_hit_records_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    layer = CacheLayer()
    hits: list[str] = []

    class _FakeMetrics:
        def cache_hit(self, layer_name: str) -> None:
            hits.append(layer_name)

    monkeypatch.setattr(layer, "_metrics", _FakeMetrics())
    layer._hit("raw")  # noqa: SLF001
    assert hits == ["raw"]


# ---------- CacheLayer（disabled） ----------


def test_cache_layer_disabled_returns_none() -> None:
    layer = CacheLayer(enabled=False)
    layer.set_raw("u", "x")
    layer.set_markdown("u", "md")
    layer.set_extracted("u", {"a": 1})
    assert layer.get_raw("u") is None
    assert layer.get_markdown("u") is None
    assert layer.get_extracted("u") is None
    # disabled 时不写入
    assert layer.raw._store == {}  # noqa: SLF001
    assert layer.markdown._store == {}  # noqa: SLF001
    assert layer.extracted._store == {}  # noqa: SLF001


def test_cache_layer_disabled_get_skips() -> None:
    layer = CacheLayer(enabled=False)
    layer.raw.set("u", "x")  # 直接塞入底层
    assert layer.get_raw("u") is None  # enabled=False 直接返回 None
