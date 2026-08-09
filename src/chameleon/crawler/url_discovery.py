"""URL 发现：a 标签提取 + sitemap.xml 解析（方案 5.4）。"""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterable
from urllib.parse import urljoin

import httpx

from chameleon.anti_detection.honeypot_filter import HoneypotFilter
from chameleon.utils.url_utils import normalize_url

_SITEMAP_LOC_RE = re.compile(r"<loc[^>]*>(.*?)</loc>", re.IGNORECASE | re.DOTALL)
_SITEMAP_INDEX_RE = re.compile(r"<sitemap[^>]*>.*?</sitemap>", re.IGNORECASE | re.DOTALL)


def discover_links(html: str, base_url: str) -> list[str]:
    """从 HTML 提取去重后的绝对链接（蜜罐过滤）。"""
    honeypot = HoneypotFilter()
    links = honeypot.filter_links(html, base_url)
    return dedupe(normalize_url(urljoin(base_url, link)) for link in links)


def dedupe(links: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(link)
    return result


async def discover_sitemap(client: httpx.AsyncClient, url: str, max_pages: int = 5000) -> list[str]:
    """解析 sitemap.xml / sitemap index（支持 gzip 与子 sitemap）。"""
    results: list[str] = []
    queue = [url]
    seen_indexes: set[str] = set()

    while queue and len(results) < max_pages:
        current = queue.pop(0)
        if current in seen_indexes:
            continue
        seen_indexes.add(current)
        resp = await client.get(current, follow_redirects=True)
        if resp.status_code != 200:
            continue
        content = _maybe_gunzip(resp.content)
        text = content.decode("utf-8", errors="ignore")

        locs = _SITEMAP_LOC_RE.findall(text)
        if not locs:
            continue
        is_index = "<sitemapindex" in text.lower() or ("<sitemap" in text.lower() and not any("<urlset" in t for t in text.lower()[:2000].splitlines()))
        for loc in locs:
            loc = loc.strip().strip("<>").strip()
            if not loc:
                continue
            if is_index:
                queue.append(loc)
            else:
                results.append(loc)
    return results[:max_pages]


def _maybe_gunzip(content: bytes) -> bytes:
    if content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except Exception:
            return content
    return content


def sitemap_url_for(base_url: str) -> str:
    """常见 sitemap 候选地址。"""
    return urljoin(base_url, "/sitemap.xml")


def discover_from_html_all(urls: list[str], html_by_url: dict[str, str]) -> list[str]:
    """批量页面中发现的全部链接（去重）。"""
    all_links: set[str] = set()
    for url, html in html_by_url.items():
        all_links.update(discover_links(html, url))
    return sorted(all_links)
