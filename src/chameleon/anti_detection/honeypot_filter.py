"""蜜罐过滤：只采集视觉可见的链接，避开 display:none 陷阱（方案 5.2 HoneypotFilter）。"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0|width\s*:\s*0|height\s*:\s*0|"
    r"font-size\s*:\s*0|position\s*:\s*absolute;\s*[^}]*left\s*:\s*-\d+",
    re.IGNORECASE,
)
_EMPTY_HREF = {"", "#", "javascript:void(0)", "javascript:void(0);", "javascript:;"}


class _LinkParser(HTMLParser):
    """解析 a 标签，携带可见性上下文。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, dict[str, str]]] = []  # (href, text, attrs)
        self._current_href: str | None = None
        self._current_attrs: dict[str, str] = {}
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        if tag == "a":
            self._current_href = attr_dict.get("href", "").strip()
            self._current_attrs = attr_dict
            self._current_text = []
        elif self._current_href is not None and tag in {"img"}:
            src = attr_dict.get("src", "")
            if src:
                self._current_text.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            self.links.append((self._current_href, " ".join(self._current_text).strip(), self._current_attrs))
            self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)


def is_hidden_by_css(attrs: dict[str, str]) -> bool:
    """从 style/aria 属性判断元素是否不可见。"""
    if attrs.get("aria-hidden", "").lower() == "true":
        return True
    return bool(_HIDDEN_STYLE_RE.search(attrs.get("style", "")))


class HoneypotFilter:
    """过滤蜜罐链接：HTTP 模式基于 HTML 属性，浏览器模式基于真实渲染可见性。"""

    def filter_links(self, html: str, base_url: str, *, min_text: int = 0) -> list[str]:
        """解析 HTML 中视觉可见的链接，返回绝对 URL 列表。"""
        parser = _LinkParser()
        parser.feed(html)
        result: list[str] = []
        for href, text, attrs in parser.links:
            if href.lower() in _EMPTY_HREF:
                continue
            if href.startswith("#"):
                continue
            if is_hidden_by_css(attrs):
                continue
            if not text.strip():
                continue
            if min_text and len(text) < min_text:
                continue
            joined = urljoin(base_url, href)
            parsed = urlparse(joined)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                continue
            result.append(joined)
        return result

    @staticmethod
    async def filter_links_visible(page: object) -> list[str]:
        """浏览器模式：通过 JS 收集渲染后可见的链接。"""
        from typing import cast

        from playwright.async_api import Page

        p: Page = page  # type: ignore[assignment]
        links = await p.evaluate(
            """
            () => {
              const links = new Set();
              document.querySelectorAll('a[href]').forEach(a => {
                const style = window.getComputedStyle(a);
                if (style.display === 'none' || style.visibility === 'hidden' ||
                    a.getAttribute('aria-hidden') === 'true') {
                  return;
                }
                const rect = a.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                links.add(a.href);
              });
              return Array.from(links);
            }
            """
        )
        return cast(list[str], links)
