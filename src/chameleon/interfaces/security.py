"""安全防护：SSRF 校验、URL 白名单（方案 16.2.5）。"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from chameleon.core.config import SecurityConfig
from chameleon.core.exceptions import ChameleonError

_PRIVATE_PREFIXES = (
    "127.",
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
    "169.254.",
    "0.",
    "localhost",
)


class SSRFError(ChameleonError):
    """目标地址疑似内网/私网，已拦截。"""

    suggested_action = "check_url_scope"


def validate_url(url: str) -> bool:
    """URL 格式校验：http/https + 有效 host。"""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def is_internal_hostname(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    if not host:
        return True
    if host == "localhost":
        return True
    if host.startswith(_PRIVATE_PREFIXES):
        return True
    # IP 字面量检查（含 IPv6）
    try:
        ip = ipaddress.ip_address(host.split(":")[0])
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
    except ValueError:
        return False


def is_internal_url(url: str) -> bool:
    if not validate_url(url):
        return True
    return is_internal_hostname(urlparse(url).hostname or "")


class SSRFGuard:
    """URL 安全门：格式 + 内网字面量 + DNS 解析后二次校验。"""

    def __init__(self, config: SecurityConfig | None = None) -> None:
        self.config = config or SecurityConfig()

    async def assert_safe(self, url: str) -> None:
        if not self.config.enable_ssrf_protection:
            return
        if not validate_url(url):
            raise SSRFError(f"invalid url: {url}")
        host = urlparse(url).hostname or ""
        if is_internal_hostname(host):
            raise SSRFError(f"internal address blocked: {host}")
        if self.config.url_whitelist and not any(host == w or host.endswith(f".{w}") for w in self.config.url_whitelist):
            raise SSRFError(f"url not in whitelist: {host}")
        # DNS 二次校验：解析出的 IP 必须是公网
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise SSRFError(f"dns resolution failed: {host}") from exc
        for info in infos[:8]:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private or addr.is_loopback or addr.is_link_local:
                    raise SSRFError(f"internal ip after dns: {ip}")
            except ValueError:
                continue
