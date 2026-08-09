"""Hybrid 提取：LLM 生成 CSS Schema → 批量 CSS 执行（方案 16.1.4 Hybrid 模式）。

降低 token 成本：先用 LLM 分析 1-2 个样本生成带 css 指令的 Schema，
后续同构页面全部走 CssExtractor（零 LLM 成本），质量漂移时重新生成。
"""

from __future__ import annotations

import json
from typing import Any

from chameleon.pipeline.extractors.base import BaseExtractor
from chameleon.pipeline.extractors.css_extractor import CssExtractor
from chameleon.pipeline.extractors.llm_extractor import LLMExtractor, parse_json_response

_SCHEMA_GEN_PROMPT = """你是 CSS 选择器专家。给定页面 HTML 与目标 JSON Schema，
为 schema 中每个字段设计稳定可靠的 CSS 选择器，输出带 "css" 指令的完整 JSON Schema。

规则：
1. 字段选择器要能在同类型页面上通用（用类名/语义标签，避免唯一样本特征）
2. 列表用 "items" + "css" 容器 + 子项 "css"
3. 需要属性值时用 "attr": "href"/"src"
4. 只输出 JSON

目标 Schema：{schema}

页面 HTML（截断）：{html}
"""


_SCHEMA_GEN_SYSTEM = "你是 CSS 选择器专家。"


class HybridExtractor(BaseExtractor):
    """先 LLM 生成 css schema，再纯 CSS 提取；字段缺失则回退 LLM。"""

    name = "hybrid"

    def __init__(self, llm: LLMExtractor, css: CssExtractor | None = None, sample_size: int = 20000) -> None:
        self.llm = llm
        self.css = css or CssExtractor()
        self.sample_size = sample_size
        self._css_schema_cache: dict[str, dict[str, Any]] = {}

    async def generate_css_schema(self, html: str, schema: dict[str, Any]) -> dict[str, Any]:
        """LLM 分析样本生成带 css 指令的 Schema。"""
        if self.llm.client is None:
            raise RuntimeError("HybridExtractor 需要 LLM client 生成 Schema")
        sample = html[: self.sample_size]
        raw = await self.llm.client.chat(
            _SCHEMA_GEN_SYSTEM,
            _SCHEMA_GEN_PROMPT.format(schema=json.dumps(schema, ensure_ascii=False), html=sample),
        )
        result = parse_json_response(raw)
        if not isinstance(result, dict):
            raise ValueError("LLM 生成的 Schema 非法")
        self._css_schema_cache[json.dumps(schema, sort_keys=True)] = result
        return result

    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        cache_key = json.dumps(schema, sort_keys=True)
        css_schema = self._css_schema_cache.get(cache_key)
        if css_schema is None:
            if self.llm.client is not None:
                css_schema = await self.generate_css_schema(html, schema)
            else:
                css_schema = schema

        data = await self.css.extract(html, css_schema, base_url)
        # 字段缺失检测：required 字段缺失时回退 LLM 兜底提取
        required = schema.get("required", [])
        missing = [f for f in required if not data.get(f)]
        if missing:
            return await self.llm.extract(html, schema, base_url)
        return data
