"""API 逆向引擎：直接调用站点内部 JSON API（方案 P8-1）。"""

from __future__ import annotations

import json
from typing import Any

from chameleon.core.exceptions import (
    RetryableError,
)
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.engines.base import BaseEngine


class ApiEngine(BaseEngine):
    """内部 API 直调：复用 HttpEngine 的连接池与代理，校验 JSON 响应。"""

    name = EngineType.API

    def __init__(self, http_engine: BaseEngine) -> None:
        self._http = http_engine

    async def fetch(self, request: FetchRequest) -> FetchResult:
        json_request = request.model_copy(update={
            "headers": {**request.headers, "Accept": "application/json, text/plain, */*"},
        })
        result = await self._http.fetch(json_request)
        # JSON 校验：非 JSON 视为无效内容
        try:
            json.loads(result.content)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RetryableError(f"api response is not json for {request.url}") from exc
        return result

    async def call_json(
        self,
        url: str,
        *,
        method: str = "GET",
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
    ) -> dict[str, Any]:
        """便捷方法：直接返回解析后的 JSON dict。"""
        request = FetchRequest(
            url=url,
            headers=headers or {},
            proxy=proxy,
        )
        result = await self.fetch(request)
        data: dict[str, Any] = json.loads(result.content)
        return data

    async def close(self) -> None:
        pass


class ApiDiscovery:
    """从网络日志中提取候选 API 端点。"""

    @staticmethod
    def filter_api_entries(entries: list[dict[str, Any]], base_domain: str) -> list[dict[str, Any]]:
        """筛选 XHR/fetch 中的 JSON 类请求（非静态资源）。"""
        skip_exts = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".woff2", ".ttf", ".ico")
        candidates: list[dict[str, Any]] = []
        for entry in entries:
            url = entry.get("url", "")
            if any(url.lower().endswith(ext) for ext in skip_exts):
                continue
            if base_domain and base_domain not in url:
                continue
            candidates.append(entry)
        return candidates
