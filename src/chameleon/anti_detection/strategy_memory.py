"""策略学习：按域名记忆成功层级，熟悉站点直接命中（方案 P8-4）。"""

from __future__ import annotations

import threading
import time

from chameleon.utils.url_utils import hostname


class StrategyMemory:
    """域名 → 成功升级层级 的记忆（LRU 风格 TTL）。"""

    def __init__(self, ttl_seconds: float = 86400.0, capacity: int = 5000) -> None:
        self.ttl = ttl_seconds
        self.capacity = capacity
        self._store: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def remember(self, url: str, level: int) -> None:
        domain = hostname(url)
        if not domain:
            return
        with self._lock:
            if len(self._store) >= self.capacity:
                oldest = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest, None)
            self._store[domain] = (time.monotonic(), level)

    def best_level(self, url: str) -> int | None:
        domain = hostname(url)
        with self._lock:
            item = self._store.get(domain)
            if item is None:
                return None
            ts, level = item
            if time.monotonic() - ts > self.ttl:
                self._store.pop(domain, None)
                return None
            return level

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
