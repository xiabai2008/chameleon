"""身份伪装：UA 池与完整请求头生成（方案 5.2 IdentityFaker）。"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from urllib.parse import urlparse

# 真实浏览器 UA 池（Chrome/Edge/Firefox/Safari × Win/Mac/Linux）
UA_POOL: tuple[str, ...] = (
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome / Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.86",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.56",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.2792.79",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Firefox / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    # Chrome Mobile / Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
)

_CHROME_SEC_FETCH = {
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
_FIREFOX_SEC_FETCH = {
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
}
_SAFARI_SEC_FETCH = {
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
}


def _sec_fetch_for(ua: str) -> dict[str, str]:
    if "Firefox" in ua:
        return _FIREFOX_SEC_FETCH
    if "Safari" in ua and "Chrome" not in ua:
        return _SAFARI_SEC_FETCH
    return _CHROME_SEC_FETCH


class IdentityFaker:
    """生成随机的浏览器身份：UA + 完整请求头。"""

    def __init__(self, ua_pool: tuple[str, ...] | None = None, ua_file: str | None = None) -> None:
        self._ua_pool = list(ua_pool if ua_pool is not None else UA_POOL)
        if ua_file and Path(ua_file).is_file():
            extra = json.loads(Path(ua_file).read_text(encoding="utf-8"))
            if isinstance(extra, list):
                self._ua_pool.extend(str(u) for u in extra)

    def random_ua(self) -> str:
        return secrets.choice(self._ua_pool)

    def pick_ua(self, seed: str = "") -> str:
        """基于 seed 稳定选择 UA（同域名可保持身份一致）。"""
        if not seed:
            return self.random_ua()
        return self._ua_pool[sum(ord(c) for c in seed) % len(self._ua_pool)]

    def generate_headers(self, url: str = "", *, ua: str | None = None, region: str | None = None) -> dict[str, str]:
        """生成完整浏览器请求头，含 Referer、Sec-Fetch-*、语言偏好。"""
        user_agent = ua or self.random_ua()
        headers: dict[str, str] = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8" if not region else f"{region},zh-CN;q=0.9,zh;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Upgrade-Insecure-Requests": "1",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
        }
        headers.update(_sec_fetch_for(user_agent))
        # 统一为 HTTP 标准标题格式（Sec-Fetch-Dest 等）
        headers = {("-".join(p.capitalize() for p in k.split("-"))): v for k, v in headers.items()}
        if url:
            host = urlparse(url).netloc
            if host:
                headers["Referer"] = f"https://{host}/"
                headers["Host"] = host
        if "Firefox" not in user_agent:
            headers["sec-ch-ua-full-version-list"] = (
                '"Chromium";v="131.0.6778.86", "Not_A Brand";v="24.0.0.0", "Google Chrome";v="131.0.6778.86"'
            )
        return headers

    def generate_headers_many(self, url: str = "", count: int = 5) -> list[dict[str, str]]:
        """生成 count 组互不相同的请求头（测试用）。"""
        seen: set[str] = set()
        result: list[dict[str, str]] = []
        for _ in range(count * 3):
            headers = self.generate_headers(url)
            if headers["User-Agent"] in seen:
                continue
            seen.add(headers["User-Agent"])
            result.append(headers)
            if len(result) >= count:
                break
        return result
