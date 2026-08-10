"""Metrics 覆盖率补强：HTTP 导出、duration/escalation/代理/队列/缓存指标。"""

from __future__ import annotations

import threading

import pytest

from chameleon.infra.metrics import Metrics


def test_singleton() -> None:
    """Metrics 单例两次获取返回同一实例。"""
    a = Metrics()
    b = Metrics()
    assert a is b


def test_record_request() -> None:
    """record_request 计数不抛异常（Prometheus Counter）。"""
    Metrics().record_request("http", "success")
    Metrics().record_request("browser", "blocked")


def test_observe_duration() -> None:
    """observe_duration 写入 Histogram 不抛异常。"""
    Metrics().observe_duration("http", 1.5)
    Metrics().observe_duration("browser", 3.2)


def test_observe_escalation() -> None:
    """observe_escalation 写入分层 Histogram 不抛异常。"""
    Metrics().observe_escalation(0)
    Metrics().observe_escalation(6)


def test_set_proxy_alive() -> None:
    """set_proxy_alive 写入 Gauge 不抛异常。"""
    Metrics().set_proxy_alive(5)
    Metrics().set_proxy_alive(0)


def test_set_queue_depth() -> None:
    """set_queue_depth 写入 Gauge 不抛异常。"""
    Metrics().set_queue_depth(10)
    Metrics().set_queue_depth(0)


def test_cache_hit() -> None:
    """cache_hit 写入 Counter（带 layer 标签）不抛异常。"""
    Metrics().cache_hit("memory")
    Metrics().cache_hit("redis")


def test_start_http_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """start_http_server 启动 daemon 线程。"""
    # 重置 singleton 状态
    monkeypatch.setattr(Metrics, "_server", None)
    # 防止真正启动 HTTP 服务
    monkeypatch.setattr("chameleon.infra.metrics.start_http_server", lambda port, addr="": None)

    m = Metrics()
    m.start_http_server(9100)

    assert Metrics._server is not None
    assert Metrics._server.daemon is True
    assert isinstance(Metrics._server, threading.Thread)
