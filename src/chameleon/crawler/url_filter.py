"""URL 过滤：同域限制、模式匹配、扩展名黑名单（方案 5.4 UrlFilter）。"""

from __future__ import annotations

import fnmatch
import re

from chameleon.utils.url_utils import hostname, normalize_url

BLACKLIST_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".avi", ".zip", ".rar", ".7z", ".gz", ".tar", ".exe", ".dmg",
    ".pdf", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx",
}

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class UrlFilter:
    """决定哪些 URL 值得爬取。规则可组合，全部通过才允许。"""

    def __init__(
        self,
        *,
        allow_domains: list[str] | None = None,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        blacklist_extensions: set[str] | None = None,
    ) -> None:
        self.allow_domains = [d.lower().lstrip(".") for d in (allow_domains or [])]
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.blacklist_extensions = blacklist_extensions or BLACKLIST_EXTENSIONS

    def allow(self, url: str) -> bool:
        url = normalize_url(url)
        if not url.startswith(("http://", "https://")):
            return False
        if _CONTROL_CHARS.search(url):
            return False
        host = hostname(url)
        if self.allow_domains and not any(host == d or host.endswith(f".{d}") for d in self.allow_domains):
            return False
        path = url.split("?", 1)[0].lower()
        for ext in self.blacklist_extensions:
            if path.endswith(ext):
                return False
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(url, pattern):
                return False
        return not self.include_patterns or any(fnmatch.fnmatch(url, p) for p in self.include_patterns)