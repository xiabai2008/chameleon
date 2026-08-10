"""CLI 覆盖率补强 — map/crawl/search/screenshot/diagnose/proxy/jobs 命令 + 内部分支。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import typer
from typer.testing import CliRunner

from chameleon.interfaces.cli import _exit_for, _print_result, app

runner = CliRunner()


# ── helpers ──


class FakeScrapeResult:
    """模拟 ScrapeResult.model_dump() 行为。"""

    def __init__(self, **kwargs):  # noqa: ANN003
        self.__dict__.update(kwargs)

    def model_dump(self) -> dict:
        return self.__dict__


def _make_async_return(ret):  # noqa: ANN202
    """创建闭包安全的异步 mock 工厂。"""

    async def _fn(*args, **kwargs):  # noqa: ANN002, ANN003
        return ret

    return _fn


def _mock_svc(monkeypatch: pytest.MonkeyPatch, **methods):  # noqa: ANN202
    """替换 CLI 的 _get_service()，返回带 mock 方法的 Chameleon。"""
    svc = MagicMock()
    for name, val in methods.items():
        setattr(svc, name, AsyncMock(side_effect=_make_async_return(val)))
    monkeypatch.setattr("chameleon.interfaces.cli._get_service", lambda: svc)
    return svc


# ── _print_result 分支 ──


def test_print_result_markdown_no_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """success + content.markdown → 打印 Markdown 对象。"""
    from rich.markdown import Markdown

    calls: list = []
    monkeypatch.setattr("chameleon.interfaces.cli.console.print", lambda *a, **kw: calls.extend(a))
    _print_result(
        FakeScrapeResult(status="success", content={"markdown": "# hello"}, extracted=None),
        as_json=False,
    )
    assert any(isinstance(obj, Markdown) for obj in calls)


def test_print_result_extracted_no_md(monkeypatch: pytest.MonkeyPatch) -> None:
    """content 无 markdown 但 extracted 有数据 → 打印 JSON（覆盖 L45）。"""
    calls: list[str] = []
    monkeypatch.setattr("chameleon.interfaces.cli.console.print", lambda *a, **kw: calls.append(str(a)))
    _print_result(
        FakeScrapeResult(status="success", content={}, extracted={"title": "Hi"}),
        as_json=False,
    )
    assert any("Hi" in c for c in calls)


def test_print_result_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 success 状态 → 打印错误 + 建议。"""
    calls: list[str] = []
    monkeypatch.setattr("chameleon.interfaces.cli.console.print", lambda *a, **kw: calls.append(str(a)))
    _print_result(
        FakeScrapeResult(status="error", content={}, error="timeout", suggested_action="retry"),
        as_json=False,
    )
    assert any("timeout" in c for c in calls)


# ── _exit_for 分支 ──


def test_exit_for_captcha_required() -> None:
    """captcha_required → typer.Exit(3)（覆盖 L51）。"""
    with pytest.raises(typer.Exit) as exc:
        _exit_for(FakeScrapeResult(status="captcha_required", content={}))
    assert exc.value.exit_code == 3


def test_exit_for_blocked() -> None:
    """error → typer.Exit(2)。"""
    with pytest.raises(typer.Exit) as exc:
        _exit_for(FakeScrapeResult(status="error", content={}))
    assert exc.value.exit_code == 2


# ── CLI 命令（mock service） ──


def test_crawl_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """crawl 输出 job_id。"""
    _mock_svc(monkeypatch, crawl="job-xyz")
    result = runner.invoke(app, ["crawl", "http://example.com", "--max-pages", "10", "--strategy", "bfs"])
    assert result.exit_code == 0
    assert "job-xyz" in result.output


def test_map_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """map 输出站点 URL 列表。"""
    _mock_svc(monkeypatch, map_site=["http://a.com", "http://b.com"])
    result = runner.invoke(app, ["map", "http://example.com"])
    assert result.exit_code == 0


def test_map_sitemap_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """map --sitemap-only。"""
    _mock_svc(monkeypatch, map_site=["http://solo.com"])
    result = runner.invoke(app, ["map", "http://example.com", "--sitemap-only"])
    assert result.exit_code == 0


def test_search_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """search 输出结果列表。"""
    _mock_svc(monkeypatch, search_web=[
        {"title": "Top Result", "url": "http://r.com", "snippet": "desc text"}
    ])
    result = runner.invoke(app, ["search", "python", "--max-results", "3", "--language", "en"])
    assert result.exit_code == 0
    assert "Top Result" in result.output
    assert "desc text" in result.output


def test_screenshot_command(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """screenshot 写入 PNG 文件（覆盖 L136-142）。"""
    _mock_svc(monkeypatch, get_screenshot="data:image/png;base64,AAAA")
    out = str(tmp_path / "test.png")
    result = runner.invoke(app, ["screenshot", "http://example.com", "-o", out])
    assert result.exit_code == 0
    assert "test.png" in result.output


def test_diagnose_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """diagnose 输出站点诊断 JSON（覆盖 L148-149）。"""
    _mock_svc(monkeypatch, diagnose_site={"bare_status": 200, "escalation_level": 0})
    result = runner.invoke(app, ["diagnose", "http://example.com"])
    assert result.exit_code == 0


def test_proxy_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """proxy 输出代理检测结果（覆盖 L155-156）。"""
    _mock_svc(monkeypatch, check_proxy={"alive": True, "latency_ms": 100})
    result = runner.invoke(app, ["proxy", "http://proxy:8080"])
    assert result.exit_code == 0


def test_jobs_with_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """jobs <job_id> 输出任务详情。"""
    job = MagicMock()
    job.job_id = "j1"
    job.status.value = "done"
    job.pages_crawled = 10
    job.url = "http://a.com"
    job.model_dump.return_value = {"job_id": "j1", "status": "done", "pages_crawled": 10, "url": "http://a.com"}
    _mock_svc(monkeypatch, get_job_status=job)
    result = runner.invoke(app, ["jobs", "j1"])
    assert result.exit_code == 0
    assert "j1" in result.output


def test_jobs_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """jobs <不存在的 id> → 退出码 1。"""
    _mock_svc(monkeypatch, get_job_status=None)
    result = runner.invoke(app, ["jobs", "no-such-job"])
    assert result.exit_code == 1


def test_jobs_list_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """jobs 无参数 → 列出全部任务（覆盖 L162-171）。"""
    job = MagicMock()
    job.job_id = "j1"
    job.status.value = "running"
    job.pages_crawled = 5
    job.url = "http://example.com"
    svc = _mock_svc(monkeypatch)
    svc.scheduler = MagicMock()
    svc.scheduler.store = MagicMock()
    svc.scheduler.store.list = AsyncMock(return_value=[job])
    result = runner.invoke(app, ["jobs"])
    assert result.exit_code == 0
    assert "j1" in result.output


def test_scrape_with_schema_file(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """scrape --schema 加载文件并解析 JSON（覆盖 L69-70）。"""
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(
        '{"type": "object", "properties": {"title": {"type": "string", "css": "h1"}}}',
        encoding="utf-8",
    )
    _mock_svc(monkeypatch, scrape=FakeScrapeResult(status="success", content={"markdown": "# x"}, extracted=None))
    result = runner.invoke(app, ["scrape", "http://example.com", "--schema", str(schema_file), "--json"])
    assert result.exit_code == 0
