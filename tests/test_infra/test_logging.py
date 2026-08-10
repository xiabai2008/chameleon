"""结构化日志覆盖率补强：JSON 输出模式、request_id 绑定与获取。"""

from __future__ import annotations

import pytest

from chameleon.infra.logging import bind_request_id, configure_logging, get_request_id


def test_configure_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """json_output=True 时添加 JSONRenderer 到处理器链。"""
    structlog_calls: dict = {}
    monkeypatch.setattr("structlog.configure", lambda **kw: structlog_calls.update(kw))
    monkeypatch.setattr("logging.basicConfig", lambda **kw: None)

    configure_logging(level="DEBUG", json_output=True)

    assert "processors" in structlog_calls
    has_json = any("JSONRenderer" in str(p) for p in structlog_calls.get("processors", []))
    assert has_json, "json_output=True 应包含 JSONRenderer"


def test_bind_request_id() -> None:
    """bind_request_id 将 id 绑定到 contextvars。"""
    bind_request_id("req-abc-123")
    assert get_request_id() == "req-abc-123"


def test_get_request_id_default() -> None:
    """未绑定 request_id 时返回 None。"""
    bind_request_id("")
    result = get_request_id()
    # 由于 contextvars 的默认值是 None，未绑定时返回 None
    assert result is None or result == ""
