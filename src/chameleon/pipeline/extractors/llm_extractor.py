"""LLM 语义提取：BYO-LLM，OpenAI 兼容接口，可注入自定义 client。"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from chameleon.pipeline.converter import estimate_tokens
from chameleon.pipeline.extractors.base import BaseExtractor

_SYSTEM_PROMPT = """你是网页数据提取引擎。根据用户提供的 JSON Schema 与页面 Markdown 内容，
提取结构化数据。只输出合法 JSON，不要输出任何解释文字。无法提取的字段用 null 填充。"""


class AsyncLLMClient(ABC):
    """LLM 调用抽象：生产用 OpenAI 兼容端点，测试可注入 fake。"""

    @abstractmethod
    async def chat(self, system: str, user: str) -> str:
        """返回模型回复文本。"""


class OpenAIClient(AsyncLLMClient):
    """OpenAI 兼容端点客户端（httpx 直连，无重依赖）。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content: str = data["choices"][0]["message"]["content"]
        return content


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_response(text: str) -> Any:
    """容错解析 LLM 输出（可能包含 ```json 包裹或前后说明）。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = _JSON_RE.search(text)
    if match:
        text = match.group(0)
    return json.loads(text)


class LLMExtractor(BaseExtractor):
    """LLM 语义提取：先裁剪输入到预算，再提示词提取 JSON。

    - max_input_tokens: 送入 LLM 的内容上限（默认 12000）
    - 注入自定义 client 可离线测试
    """

    name = "llm"

    def __init__(self, client: AsyncLLMClient | None = None, max_input_tokens: int = 12000) -> None:
        self.client = client
        self.max_input_tokens = max_input_tokens

    def set_client(self, client: AsyncLLMClient) -> None:
        self.client = client

    def _user_prompt(self, content: str, schema: dict[str, Any], extract_prompt: str | None) -> str:
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        instruction = extract_prompt or "根据 schema 从页面提取数据"
        return (
            f"提取要求：{instruction}\n\n"
            f"JSON Schema：\n{schema_str}\n\n"
            f"页面内容（Markdown）：\n{content}"
        )

    async def extract(self, html: str, schema: dict[str, Any], base_url: str = "") -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("LLMExtractor 未配置 LLM client")
        from chameleon.pipeline.converter import Converter

        md = Converter().to_markdown(html, base_url)
        if estimate_tokens(md) > self.max_input_tokens:
            from chameleon.pipeline.converter import FitMarkdown

            md = FitMarkdown(default_max_tokens=self.max_input_tokens).fit(md)
        raw = await self.client.chat(_SYSTEM_PROMPT, self._user_prompt(md, schema, None))
        result = parse_json_response(raw)
        if not isinstance(result, dict):
            raise ValueError(f"LLM 返回非对象 JSON: {type(result).__name__}")
        return result
