"""robots.txt 解析与遵守（方案 5.4，合规红线）。"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


class RobotsTxt:
    """缓存式 robots.txt 解析器。

    - fetch: 拉取并缓存（带 TTL）
    - is_allowed: 判断 URL 是否允许采集（默认 UA: ChameleonBot）
    """

    UA = "ChameleonBot/0.1"

    def __init__(self, client: httpx.AsyncClient | None = None, ttl: int = 3600) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        self._ttl = ttl
        self._cache: dict[str, tuple[float, RobotFileParser]] = {}

    @staticmethod
    def _origin(url: str) -> str:
        """scheme://host:port（保留端口）。"""
        parsed = urlparse(url)
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}"

    async def _ensure(self, base_url: str) -> RobotFileParser:
        now = time.time()
        cached = self._cache.get(base_url)
        if cached and now - cached[0] < self._ttl:
            return cached[1]
        parser = RobotFileParser()
        robots_url = f"{base_url}/robots.txt"
        try:
            resp = await self._client.get(robots_url)
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
        except Exception:
            parser = RobotFileParser()  # 失败视为放行
        self._cache[base_url] = (now, parser)
        return parser

    async def is_allowed(self, url: str, user_agent: str | None = None) -> bool:
        try:
            parser = await self._ensure(self._origin(url))
            return parser.can_fetch(user_agent or self.UA, url)
        except Exception:
            return True

    async def close(self) -> None:
        await self._client.aclose()
