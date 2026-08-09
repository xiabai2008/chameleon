"""编码检测：response.text 不可信，综合响应头/元信息/内容探测。"""

from __future__ import annotations

import re
from collections.abc import Mapping

import charset_normalizer

_HTTP_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([\w-]+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(r"<meta[^>]+charset\s*=\s*[\"']?([\w-]+)", re.IGNORECASE)


def _charset_from_headers(headers: Mapping[str, str]) -> str | None:
    content_type = headers.get("content-type") or headers.get("Content-Type")
    if not content_type:
        return None
    match = _HTTP_CHARSET_RE.search(content_type)
    return match.group(1).lower() if match else None


def _charset_from_meta(html_head: str) -> str | None:
    match = _META_CHARSET_RE.search(html_head[:2048])
    return match.group(1).lower() if match else None


def decode_html(raw: bytes, headers: Mapping[str, str] | None = None, default: str = "utf-8") -> str:
    """按 响应头 > meta 标签 > 内容探测 > 默认 的顺序解码 HTML。"""
    if not raw:
        return ""
    headers = headers or {}

    declared = _charset_from_headers(headers) or _charset_from_meta(raw[:2048].decode("ascii", errors="ignore"))
    if declared:
        try:
            return raw.decode(declared, errors="strict")
        except (LookupError, UnicodeDecodeError):
            pass

    best = charset_normalizer.from_bytes(raw).best()
    if best is not None:
        return str(best)

    return raw.decode(default, errors="replace")


def normalize_newlines(text: str) -> str:
    """统一换行符。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")
