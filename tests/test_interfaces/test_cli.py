"""CLI 集成测试（P6-7）。

注意：CLI 通过 asyncio.run 驱动共享的 Chameleon 单例，跨测试复用会因
事件循环切换导致 httpx client 失效，因此所有命令测试合并为一个用例。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from chameleon.interfaces.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_ssrf(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION", "false")
    yield


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "scrape" in result.output
    assert "crawl" in result.output


def test_cli_scrape_blocked_exit_code() -> None:
    """目标不可达时退出码非 0。"""
    result = runner.invoke(app, ["scrape", "http://127.0.0.1:1/nope"])
    assert result.exit_code != 0


def test_cli_commands(cli_server: str, tmp_path: pytest.TempPathFactory) -> None:
    """scrape(标记/markdown/json) + extract 全流程（共享单次 service 生命周期）。"""

    # 1. scrape markdown
    result = runner.invoke(app, ["scrape", f"{cli_server}/static", "-o", "markdown"])
    assert result.exit_code == 0, result.output
    assert "静态页面标题" in result.output

    # 2. scrape json（含缓存命中路径）
    result = runner.invoke(app, ["scrape", f"{cli_server}/static", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "success"

    # 3. extract（schema 文件）
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(
        '{"type": "object", "properties": {"title": {"type": "string", "css": "h1"}}, "required": ["title"]}',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["extract", f"{cli_server}/products", "--schema", str(schema_file)])
    assert result.exit_code == 0, result.output
    assert "全部产品" in result.output
