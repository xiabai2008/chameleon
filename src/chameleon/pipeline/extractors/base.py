"""结构化提取：策略模式基类（Crawl4AI ExtractionStrategy 借鉴）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseExtractor(ABC):
    """提取策略基类：schema 为 JSON Schema 子集，含 css/xpath 提取指令。"""

    name: str = "base"

    @abstractmethod
    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        """从 HTML 按 schema 提取结构化数据。"""


class NoExtractorError(Exception):
    """无法提取任何字段。"""
