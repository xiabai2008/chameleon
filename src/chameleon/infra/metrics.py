"""监控指标：Prometheus 采集（方案 7-3）。"""

from __future__ import annotations

import threading
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, start_http_server

_REQUESTS = Counter("chameleon_requests_total", "采集请求总数", ["engine", "status"])
_DURATION = Histogram("chameleon_scrape_duration_seconds", "采集耗时", ["engine"])
_ESCALATION = Histogram("chameleon_escalation_level", "最终升级层级", buckets=(0, 1, 2, 3, 4, 5, 6))
_PROXY_ALIVE = Gauge("chameleon_proxy_alive", "存活代理数")
_QUEUE_DEPTH = Gauge("chameleon_queue_depth", "任务队列深度")
_CACHE_HITS = Counter("chameleon_cache_hits_total", "缓存命中数", ["layer"])


class Metrics:
    """指标单例：跨模块埋点，未启动 HTTP 导出时仅计数。"""

    _instance: Metrics | None = None
    _server: Any = None

    def __new__(cls) -> Metrics:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def start_http_server(self, port: int = 9100) -> None:
        if Metrics._server is None:
            Metrics._server = threading.Thread(target=start_http_server, args=(port,), daemon=True)
            Metrics._server.start()

    def record_request(self, engine: str, status: str) -> None:
        _REQUESTS.labels(engine=engine, status=status).inc()

    def observe_duration(self, engine: str, seconds: float) -> None:
        _DURATION.labels(engine=engine).observe(seconds)

    def observe_escalation(self, level: int) -> None:
        _ESCALATION.observe(level)

    def set_proxy_alive(self, count: int) -> None:
        _PROXY_ALIVE.set(count)

    def set_queue_depth(self, depth: int) -> None:
        _QUEUE_DEPTH.set(depth)

    def cache_hit(self, layer: str) -> None:
        _CACHE_HITS.labels(layer=layer).inc()
