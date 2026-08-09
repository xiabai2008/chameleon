"""缓存分层：URL 级 → Markdown 级 → 提取级（方案 16.1.8 + P7-5）。"""

from __future__ import annotations

import threading
import time
from typing import Any

from chameleon.infra.metrics import Metrics


class TTLCache:
    """线程安全 TTL 缓存。"""

    def __init__(self, ttl: float = 300.0, capacity: int = 1000) -> None:
        self.ttl = ttl
        self.capacity = capacity
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if time.monotonic() > expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._store) >= self.capacity:
                oldest = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest, None)
            self._store[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class CacheLayer:
    """三级缓存：raw(URL) → markdown → extracted。命中记录指标。"""

    def __init__(
        self,
        *,
        raw_ttl: float = 600.0,
        markdown_ttl: float = 3600.0,
        extract_ttl: float = 7200.0,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.raw = TTLCache(ttl=raw_ttl)
        self.markdown = TTLCache(ttl=markdown_ttl)
        self.extracted = TTLCache(ttl=extract_ttl)
        self._metrics = Metrics()

    def _hit(self, layer: str) -> bool:
        self._metrics.cache_hit(layer)
        return True

    def get_raw(self, url: str) -> Any | None:
        if not self.enabled:
            return None
        value = self.raw.get(url)
        return value if value is not None else None

    def set_raw(self, url: str, result: Any) -> None:
        if self.enabled:
            self.raw.set(url, result)

    def get_markdown(self, key: str) -> str | None:
        if not self.enabled:
            return None
        value = self.markdown.get(key)
        return value if isinstance(value, str) else None

    def set_markdown(self, key: str, md: str) -> None:
        if self.enabled:
            self.markdown.set(key, md)

    def get_extracted(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        value = self.extracted.get(key)
        return value if isinstance(value, dict) else None

    def set_extracted(self, key: str, data: dict[str, Any]) -> None:
        if self.enabled:
            self.extracted.set(key, data)
