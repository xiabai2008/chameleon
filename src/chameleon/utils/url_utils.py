"""URL 工具：规范化、域名判断、相对链接解析。"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "spm"}


def normalize_url(url: str, *, strip_tracking: bool = True) -> str:
    """URL 规范化：小写 scheme/host、去 fragment、去默认端口、可选去跟踪参数。"""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path
    query = parsed.query
    if strip_tracking and query:
        pairs = [p for p in query.split("&") if p and p.split("=", 1)[0].lower() not in TRACKING_PARAMS]
        query = "&".join(pairs)
    return urlunparse((scheme, host, path, parsed.params, query, ""))


def resolve_url(base: str, link: str) -> str | None:
    """把相对链接解析为绝对 URL；无效链接返回 None。"""
    joined = urljoin(base, link.strip())
    parsed = urlparse(joined)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return joined


def hostname(url: str) -> str:
    """提取主机名（含端口输入也安全），无 scheme 时自动补全。"""
    if "://" not in url:
        url = f"//{url}"
    return (urlparse(url).hostname or "").lower()


def is_same_domain(url_a: str, url_b: str) -> bool:
    return hostname(url_a) == hostname(url_b)


def is_subdomain(sub: str, domain: str) -> bool:
    """sub 是否是 domain 的子域（含相等）。"""
    sub = hostname(sub)
    domain = hostname(domain)
    return sub == domain or sub.endswith(f".{domain}")


def is_http(url: str) -> bool:
    return urlparse(url).scheme.lower() in ("http", "https")


def get_netloc(url: str) -> str:
    return urlparse(url).netloc
