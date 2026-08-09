"""HTML 清洗：去噪音标签 + readability 主内容提取（方案 5.3 Pipeline）。"""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

_NOISE_TAGS = {"script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside", "form", "button", "template"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_KEEP_TAGS = {"p", "div", "section", "article", "li", "ul", "ol", "table", "tr", "td", "th", "img", "a", "span", "br", "blockquote", "pre", "code", "figure", "figcaption", "strong", "em", "b", "i", "u", "h1", "h2", "h3", "h4", "h5", "h6", "title"}


class Cleaner:
    """把原始 HTML 清洗为主内容 HTML。

    - 主路径：readability 提取正文（多段落优先）
    - 回退路径：去除噪音标签后原样返回
    """

    def __init__(self, noise_tags: set[str] | None = None, use_readability: bool = True) -> None:
        self.noise_tags = noise_tags or _NOISE_TAGS
        self.use_readability = use_readability

    def clean(self, html: str) -> tuple[str | None, str]:
        """返回 (标题, 主内容 HTML)。失败时回退到简单清理。"""
        title = self._extract_title(html)
        if self.use_readability:
            try:
                from readability import Document  # type: ignore[import-untyped]

                doc = Document(html)
                main = doc.summary(html_partial=True)
                if len(main) > 200:
                    return title, main
            except Exception:
                pass
        return title, self._simple_clean(html)

    @staticmethod
    def _extract_title(html: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
        return None

    def _simple_clean(self, html: str) -> str:
        """去噪音标签 + 空标签折叠。"""
        tree = HTMLParser(html)
        for node in tree.css("script, style, noscript, iframe, svg, header, footer, nav, aside, form, button, template"):
            node.decompose()
        body = tree.body
        return (body.html if body is not None else tree.html) or ""

    @staticmethod
    def strip_noise_html(html: str) -> str:
        """去除 noise 标签（用于整体去噪但保留页头信息）。"""
        tree = HTMLParser(html)
        for node in tree.css("script, style, noscript, iframe, svg, header, footer, nav, aside, form, button, template"):
            node.decompose()
        return tree.html or ""
