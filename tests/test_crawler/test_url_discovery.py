"""URL discovery 覆盖率补强 — sitemap 解析、gzip 解压、批量链接发现。"""

from __future__ import annotations

import gzip

import httpx
import pytest

from chameleon.crawler.url_discovery import (
    _maybe_gunzip,
    discover_from_html_all,
    discover_sitemap,
)

# ── _maybe_gunzip ──


def test_maybe_gunzip_plain_content() -> None:
    """非 gzip 内容原样返回。"""
    assert _maybe_gunzip(b"<html>hello</html>") == b"<html>hello</html>"


def test_maybe_gunzip_gzip_content() -> None:
    """gzip 内容正确解压。"""
    original = b"decoded content"
    assert _maybe_gunzip(gzip.compress(original)) == original


def test_maybe_gunzip_corrupted_gzip_fallback() -> None:
    """损坏的 gzip 流回退为原始字节（覆盖 except 分支）。"""
    corrupted = b"\x1f\x8bNOT_GZIP"
    assert _maybe_gunzip(corrupted) == corrupted


# ── discover_from_html_all ──


def test_discover_from_html_all_collects_and_dedupes() -> None:
    """跨页面收集链接并去重。"""
    urls = ["http://a.com/p1", "http://a.com/p2"]
    html_by_url = {
        "http://a.com/p1": '<a href="/next">Next</a><a href="http://b.com/ext">Ext</a>',
        "http://a.com/p2": '<a href="/next">Next again</a>',
    }
    result = discover_from_html_all(urls, html_by_url)
    assert "http://a.com/next" in result
    assert "http://b.com/ext" in result
    assert len(result) == 2  # "/next" 跨页面去重


# ── discover_sitemap ──

_REGULAR_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://site.com/page1</loc></url>
  <url><loc>https://site.com/page2</loc></url>
</urlset>"""

_SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://site.com/sitemap-a.xml</loc></sitemap>
  <sitemap><loc>https://site.com/sitemap-b.xml</loc></sitemap>
</sitemapindex>"""

_SITEMAP_SUB_A = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://site.com/p-a</loc></url>
  <url><loc>https://site.com/p-b</loc></url>
</urlset>"""


@pytest.mark.asyncio
async def test_discover_sitemap_regular(respx_mock) -> None:
    """正则 sitemap 返回 URL 列表。"""
    url = "https://site.com/sitemap.xml"
    respx_mock.get(url).mock(return_value=httpx.Response(200, content=_REGULAR_SITEMAP.encode()))
    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, url)
    assert urls == ["https://site.com/page1", "https://site.com/page2"]


@pytest.mark.asyncio
async def test_discover_sitemap_index(respx_mock) -> None:
    """sitemap index 递归解析子 sitemap（覆盖 is_index 分支 + seen_indexes 去重）。"""
    respx_mock.get("https://site.com/sitemap.xml").mock(
        return_value=httpx.Response(200, content=_SITEMAP_INDEX.encode())
    )
    respx_mock.get("https://site.com/sitemap-a.xml").mock(
        return_value=httpx.Response(200, content=_SITEMAP_SUB_A.encode())
    )
    respx_mock.get("https://site.com/sitemap-b.xml").mock(
        return_value=httpx.Response(200, content=b'<?xml version="1.0"?><urlset></urlset>')
    )
    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, "https://site.com/sitemap.xml")
    assert urls == ["https://site.com/p-a", "https://site.com/p-b"]


@pytest.mark.asyncio
async def test_discover_sitemap_gzipped(respx_mock) -> None:
    """gzip 压缩的 sitemap 自动解压后解析（覆盖 _maybe_gunzip 集成路径）。"""
    url = "https://site.com/sitemap.gz"
    respx_mock.get(url).mock(
        return_value=httpx.Response(200, content=gzip.compress(_REGULAR_SITEMAP.encode()))
    )
    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, url)
    assert len(urls) == 2


@pytest.mark.asyncio
async def test_discover_sitemap_empty_urlset(respx_mock) -> None:
    """空 urlset（无 <loc> 标签）返回空列表。"""
    url = "https://site.com/empty.xml"
    respx_mock.get(url).mock(
        return_value=httpx.Response(200, content=b'<?xml version="1.0"?><urlset></urlset>')
    )
    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, url)
    assert urls == []


@pytest.mark.asyncio
async def test_discover_sitemap_non_200(respx_mock) -> None:
    """非 200 响应返回空列表。"""
    url = "https://site.com/404.xml"
    respx_mock.get(url).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as client:
        urls = await discover_sitemap(client, url)
    assert urls == []
