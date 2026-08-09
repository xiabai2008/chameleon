"""CLI 命令行工具：typer，退出码语义化（方案 6.3）。"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markdown import Markdown

from chameleon.interfaces.sdk import Chameleon

app = typer.Typer(name="chameleon", help="AI Agent 爬虫工具：分层对抗、自适应降级、Agent 友好输出")
console = Console()
_service: Chameleon | None = None

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_BLOCKED = 2
EXIT_CAPTCHA = 3


def _get_service() -> Chameleon:
    global _service
    if _service is None:
        _service = Chameleon()
    return _service


def _print_result(result: object, as_json: bool) -> None:
    data: dict[str, Any] = result.model_dump() if hasattr(result, "model_dump") else {}
    if as_json:
        console.print(json.dumps(data, ensure_ascii=False, indent=2, default=str), soft_wrap=True)
        return
    status = data.get("status")
    if status != "success":
        console.print(f"[red]状态: {status}[/red] 错误: {data.get('error')} 建议: {data.get('suggested_action')}")
        return
    md = data.get("content", {}).get("markdown")
    if md:
        console.print(Markdown(md))
    if data.get("extracted"):
        console.print(json.dumps(data["extracted"], ensure_ascii=False, indent=2))


def _exit_for(result: object) -> None:
    status = result.model_dump().get("status") if hasattr(result, "model_dump") else None
    if status == "captcha_required":
        raise typer.Exit(EXIT_CAPTCHA)
    if status != "success":
        raise typer.Exit(EXIT_BLOCKED)


@app.command()
def scrape(
    url: str,
    output_format: Annotated[str, typer.Option("-o", "--output", help="markdown|json|html")] = "markdown",
    mode: Annotated[str, typer.Option("--mode", help="auto|static|dynamic")] = "auto",
    schema: Annotated[str | None, typer.Option("--schema", help="JSON Schema 文件路径")] = None,
    prompt: Annotated[str | None, typer.Option("--prompt", help="自然语言提取描述")] = None,
    wait_for: Annotated[str | None, typer.Option("--wait-for", help="等待 CSS 选择器")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="输出 JSON")] = False,
) -> None:
    """采集单个 URL。"""
    schema_data = None
    if schema:
        with open(schema, encoding="utf-8") as f:
            schema_data = json.loads(f.read())
    result = asyncio.run(
        _get_service().scrape(url, mode=mode, output_format=output_format, schema=schema_data, extract_prompt=prompt, wait_for=wait_for)
    )
    _print_result(result, as_json)
    _exit_for(result)


@app.command()
def crawl(
    url: str,
    max_pages: Annotated[int, typer.Option("--max-pages")] = 50,
    max_depth: Annotated[int, typer.Option("--max-depth")] = 3,
    strategy: Annotated[str, typer.Option("--strategy", help="bfs|dfs|adaptive")] = "adaptive",
) -> None:
    """深度爬取整站。"""
    job_id = asyncio.run(_get_service().crawl(url, max_pages=max_pages, max_depth=max_depth, strategy=strategy))
    console.print(f"任务已提交: {job_id}")


@app.command()
def map(
    url: str,
    sitemap_only: Annotated[bool, typer.Option("--sitemap-only")] = False,
) -> None:
    """发现站点 URL。"""
    result = asyncio.run(_get_service().map_site(url, sitemap_only=sitemap_only))
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def extract(
    url: str,
    schema: Annotated[str, typer.Option("--schema", help="JSON Schema 文件路径")],
    strategy: Annotated[str, typer.Option("--strategy", help="css|xpath|llm|auto")] = "auto",
) -> None:
    """结构化提取。"""
    with open(schema, encoding="utf-8") as f:
        schema_data = json.loads(f.read())
    result = asyncio.run(_get_service().extract(url, schema_data, strategy=strategy))
    _print_result(result, as_json=True)
    _exit_for(result)


@app.command()
def search(
    query: str,
    max_results: Annotated[int, typer.Option("--max-results")] = 5,
    language: Annotated[str, typer.Option("--language")] = "zh",
) -> None:
    """搜索互联网。"""
    results = asyncio.run(_get_service().search_web(query, max_results=max_results, language=language))
    for item in results:
        console.print(f"[bold]{item['title']}[/bold]")
        console.print(f"  {item['url']}")
        if item.get("snippet"):
            console.print(f"  {item['snippet']}")


@app.command()
def screenshot(
    url: str,
    output: Annotated[str, typer.Option("-o", "--output", help="PNG 输出路径")] = "screenshot.png",
    full_page: Annotated[bool, typer.Option("--full-page")] = False,
) -> None:
    """获取网页截图。"""
    import base64

    data_uri = asyncio.run(_get_service().get_screenshot(url, full_page=full_page))
    raw = base64.b64decode(data_uri.split(",", 1)[1])
    with open(output, "wb") as f:
        f.write(raw)
    console.print(f"截图已保存: {output}")


@app.command()
def diagnose(url: str) -> None:
    """诊断站点反爬能力。"""
    result = asyncio.run(_get_service().diagnose_site(url))
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def proxy(url: str) -> None:
    """检测代理可用性。"""
    result = asyncio.run(_get_service().check_proxy(url))
    console.print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def jobs(job_id: Annotated[str | None, typer.Argument()] = None) -> None:
    """查询任务状态。"""
    if job_id:
        job = asyncio.run(_get_service().get_job_status(job_id))
        if job is None:
            console.print(f"[red]任务不存在: {job_id}[/red]")
            raise typer.Exit(EXIT_FAILURE)
        console.print(json.dumps(job.model_dump(), ensure_ascii=False, indent=2))
    else:
        jobs_data = asyncio.run(_get_service().scheduler.store.list())
        for job in jobs_data:
            console.print(f"{job.job_id}  {job.status.value}  {job.pages_crawled} 页  {job.url}")


if __name__ == "__main__":
    app()
