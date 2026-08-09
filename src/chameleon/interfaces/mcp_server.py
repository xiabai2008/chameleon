"""MCP Server：12 个工具，stdio + Streamable HTTP 双传输（方案 6.1/16.2）。"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from chameleon.interfaces.sdk import Chameleon
from chameleon.interfaces.security import SSRFGuard

DEFAULT_BROWSER_LIMIT = 30

mcp = FastMCP("chameleon")
_service: Chameleon | None = None
_guard: SSRFGuard | None = None


def _get_service() -> Chameleon:
    global _service
    if _service is None:
        _service = Chameleon()
    return _service


def _get_guard() -> SSRFGuard:
    global _guard
    if _guard is None:
        _guard = SSRFGuard()
    return _guard


def _safe_output(result: Any) -> dict[str, Any]:
    """统一输出：ScrapeResult → dict（截断超长内容）。"""
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if isinstance(data, dict) and data.get("content") and isinstance(data["content"], dict):
        md = data["content"].get("markdown")
        if md and len(md) > 12000:
            data["content"]["markdown"] = md[:12000] + "\n...(已截断)"
            data["truncated"] = True
    return data


@mcp.tool()
async def scrape_url(
    url: str,
    mode: str = "auto",
    output_format: str = "markdown",
    schema: dict[str, Any] | None = None,
    extract_prompt: str | None = None,
    wait_for: str | None = None,
    proxy_region: str | None = None,
) -> dict[str, Any]:
    """采集单个 URL 并转为 Markdown/JSON。当用户给出具体网址或询问某页面内容时使用。
    不要用于：搜索互联网（用 search_web）。"""
    await _get_guard().assert_safe(url)
    result = await _get_service().scrape(
        url,
        mode=mode,
        output_format=output_format,
        schema=schema,
        extract_prompt=extract_prompt,
        wait_for=wait_for,
        proxy_region=proxy_region,
    )
    return _safe_output(result)


@mcp.tool()
async def crawl_site(
    url: str,
    max_pages: int = 50,
    max_depth: int = 3,
    strategy: str = "adaptive",
) -> dict[str, Any]:
    """深度爬取整个网站，返回 job_id。当用户要求采集整个网站或栏目时使用。"""
    await _get_guard().assert_safe(url)
    job_id = await _get_service().crawl(url, max_pages=max_pages, max_depth=max_depth, strategy=strategy)
    return {"job_id": job_id, "status": "queued"}


@mcp.tool()
async def map_site(url: str, sitemap_only: bool = False) -> dict[str, Any]:
    """快速发现网站所有 URL（不抓取内容）。"""
    await _get_guard().assert_safe(url)
    return await _get_service().map_site(url, sitemap_only=sitemap_only)


@mcp.tool()
async def extract_data(
    url: str,
    schema: dict[str, Any],
    strategy: str = "auto",
) -> dict[str, Any]:
    """基于 JSON Schema 从网页提取结构化数据。当用户要求特定字段（价格/标题/日期等）时使用。"""
    await _get_guard().assert_safe(url)
    result = await _get_service().extract(url, schema, strategy=strategy)
    data = _safe_output(result)
    return {"extracted": data.get("extracted"), "status": data.get("status"), "error": data.get("error")}


@mcp.tool()
async def search_web(query: str, max_results: int = 5, language: str = "zh") -> dict[str, Any]:
    """搜索互联网并返回结果页面的 Markdown。当用户询问实时信息/最新内容时使用。"""
    results = await _get_service().search_web(query, max_results=max_results, language=language)
    return {"query": query, "results": results}


@mcp.tool()
async def batch_scrape(urls: list[str], output_format: str = "markdown", concurrency: int = 4) -> dict[str, Any]:
    """批量采集多个 URL。当用户给出多个网址时使用。"""
    results = await _get_service().batch_scrape(urls, concurrency=concurrency, output_format=output_format)
    return {"count": len(results), "results": [_safe_output(r) for r in results]}


@mcp.tool()
async def get_screenshot(url: str, full_page: bool = False) -> dict[str, Any]:
    """获取网页截图（base64 PNG）。当用户想看页面外观/布局时使用。"""
    await _get_guard().assert_safe(url)
    data_uri = await _get_service().get_screenshot(url, full_page=full_page)
    return {"url": url, "screenshot_base64": data_uri}


@mcp.tool()
async def diagnose_site(url: str) -> dict[str, Any]:
    """诊断网站反爬能力和推荐策略。首次接触新站点时使用。"""
    await _get_guard().assert_safe(url)
    return await _get_service().diagnose_site(url)


@mcp.tool()
async def check_proxy(proxy_url: str) -> dict[str, Any]:
    """检测代理 IP 的可用性和出口信息。"""
    return await _get_service().check_proxy(proxy_url)


@mcp.tool()
async def get_job_status(job_id: str) -> dict[str, Any]:
    """查询异步爬取任务状态。"""
    job = await _get_service().get_job_status(job_id)
    if job is None:
        return {"job_id": job_id, "status": "not_found"}
    return job.model_dump()


@mcp.tool()
async def get_robots_txt(url: str) -> dict[str, Any]:
    """获取网站的 robots.txt 规则。"""
    await _get_guard().assert_safe(url)
    text = await _get_service().get_robots_txt(url)
    return {"url": url, "robots_txt": text}


@mcp.tool()
async def get_network_log(url: str, filter_type: str = "xhr") -> dict[str, Any]:
    """获取页面网络请求日志（用于 API 发现）。filter_type: xhr|fetch|all"""
    await _get_guard().assert_safe(url)
    entries = await _get_service().get_network_log(url, filter_type=filter_type)
    return {"url": url, "entries": entries}


def run_stdio() -> None:
    """本地模式：stdio 传输。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
