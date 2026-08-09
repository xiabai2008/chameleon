"""配置系统测试：yaml 加载与 env 覆盖优先级。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chameleon.core.config import ProxyConfig, Settings


def test_settings_load_from_yaml(tmp_path: Path) -> None:
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(
        "log_level: DEBUG\nproxy:\n  enabled: true\n  static_list: ['http://1.2.3.4:8080']\n",
        encoding="utf-8",
    )
    os.environ["CHAMELEON_CONFIG"] = str(yaml_file)
    try:
        s = Settings()
    finally:
        os.environ.pop("CHAMELEON_CONFIG", None)
    assert s.log_level == "DEBUG"
    assert s.proxy.enabled is True
    assert s.proxy.static_list == ["http://1.2.3.4:8080"]


def test_env_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text("log_level: WARNING\n", encoding="utf-8")
    monkeypatch.setenv("CHAMELEON_CONFIG", str(yaml_file))
    monkeypatch.setenv("CHAMELEON_LOG_LEVEL", "CRITICAL")
    s = Settings()
    assert s.log_level == "CRITICAL"


def test_proxy_config_defaults() -> None:
    p = ProxyConfig()
    assert p.pool_type == "static"
    assert p.min_score == 30
    assert p.default_score == 50
    assert p.static_list == []
