"""HTML → Markdown 转换 + token 预算裁剪（方案 5.3 + Crawl4AI Fit Markdown 借鉴）。"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from markdownify import markdownify as _md

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


class Converter:
    """HTML → 干净的 GitHub 风格 Markdown。"""

    def __init__(self) -> None:
        self.options = {
            "heading_style": "ATX",
            "bullets": "-",
            "strong_em_symbol": "**",
            "strip": ["script", "style", "noscript", "iframe", "template", "form"],
            "convert_as_inline": False,
            "escape_asterisks": False,
        }

    def to_markdown(self, html: str, base_url: str | None = None) -> str:
        md = _md(
            html,
            heading_style="ATX",
            bullets="-",
            strong_em_symbol="**",
            strip=["script", "style", "noscript", "iframe", "template", "form"],
            escape_asterisks=False,
        )
        md = re.sub(r"\n{3,}", "\n\n", md)
        md = md.strip()
        if base_url:
            md = self._resolve_relative(md, base_url)
        return md

    @staticmethod
    def _resolve_relative(md: str, base_url: str) -> str:
        def repl(match: re.Match[str]) -> str:
            text, url = match.group(1), match.group(2)
            if url.startswith(("http://", "https://", "mailto:", "#", "data:", "javascript:")):
                return match.group(0)
            return f"[{text}]({urljoin(base_url, url)})"

        return _LINK_RE.sub(repl, md)


def estimate_tokens(text: str) -> int:
    """近似 token 估算：CJK 字符按 1 token/字符，其余按 4 字符/ token。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f")
    other = len(text) - cjk
    return max(cjk + other // 4, 1)


class FitMarkdown:
    """按 token 预算裁剪 Markdown：保留标题/首段等高信息密度内容（参考 Crawl4AI Fit Markdown）。"""

    def __init__(self, default_max_tokens: int = 8000) -> None:
        self.default_max_tokens = default_max_tokens

    def fit(self, markdown: str, max_tokens: int | None = None) -> str:
        budget = max_tokens or self.default_max_tokens
        if budget <= 0 or estimate_tokens(markdown) <= budget:
            return markdown

        blocks = markdown.split("\n")
        kept: list[str] = []
        used = 0
        for block in blocks:
            block_cost = estimate_tokens(block)
            is_heading = block.startswith(("#", "-", "*", ">", "|")) or block.strip() == ""
            if used + block_cost > budget:
                if is_heading and used + block_cost <= budget * 1.2:
                    kept.append(block)
                    used += block_cost
                    continue
                break
            kept.append(block)
            used += block_cost

        if len(kept) < len(blocks):
            kept.append("\n> ⚠️ 内容已按 token 预算截断（展示开头部分）")
        return "\n".join(kept).strip()
