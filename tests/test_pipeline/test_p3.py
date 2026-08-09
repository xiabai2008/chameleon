"""处理管线（P3）测试。"""

from __future__ import annotations

from typing import Any

import pytest

from chameleon.core.models import FetchResult, ScrapeStatus
from chameleon.pipeline.cleaner import Cleaner
from chameleon.pipeline.converter import Converter, FitMarkdown, estimate_tokens
from chameleon.pipeline.deduplicator import Deduplicator
from chameleon.pipeline.extractors.css_extractor import CssExtractor, XPathExtractor
from chameleon.pipeline.extractors.llm_extractor import (
    AsyncLLMClient,
    LLMExtractor,
    parse_json_response,
)
from chameleon.pipeline.pipeline import Pipeline
from chameleon.pipeline.validator import ExtractionValidator

PRODUCT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "css": "h1"},
        "items": {
            "type": "array",
            "css": "ul.products",
            "items": {
                "type": "object",
                "css": "li.product",
                "properties": {
                    "name": {"type": "string", "css": "h2.name"},
                    "price": {"type": "string", "css": "span.price"},
                },
            },
        },
    },
    "required": ["title"],
}


# ---------- Cleaner / Converter ----------


def test_cleaner_removes_noise(test_server: str) -> None:
    html = """
    <html><head><title>测试页</title></head><body>
    <nav><a href="/a">导航</a></nav>
    <div id="content"><p>这是主要内容段落，用于验证清洗是否保留下核心文本内容。</p></div>
    <script>var x = 1;</script>
    <footer>版权信息</footer>
    </body></html>
    """
    cleaner = Cleaner(use_readability=False)
    title, main = cleaner.clean(html)
    assert title == "测试页"
    assert "script" not in main
    assert "nav" not in main
    assert "footer" not in main
    assert "主要内容段落" in main


def test_converter_markdown(test_server: str) -> None:
    converter = Converter()
    md = converter.to_markdown("<h1>标题</h1><p>正文内容 <a href='/x'>链接</a></p>", "https://example.com/page")
    assert md.startswith("# 标题")
    assert "正文内容" in md
    assert "https://example.com/x" in md


def test_fit_markdown_truncates() -> None:
    fitter = FitMarkdown(default_max_tokens=50)
    long_md = "\n".join(f"### 段落{i}\n" + "内容内容内容内容内容内容内容内容内容内容" * 5 for i in range(20))
    fitted = fitter.fit(long_md, max_tokens=50)
    assert estimate_tokens(fitted) <= 50 * 1.2
    assert "截断" in fitted or estimate_tokens(fitted) <= 50


def test_estimate_tokens() -> None:
    assert estimate_tokens("中文内容") == 4
    assert estimate_tokens("hello world") >= 2


# ---------- Extractors ----------


def test_css_extractor_products() -> None:
    import asyncio

    from tests.fixtures.site import PRODUCTS_HTML

    extractor = CssExtractor()
    result = asyncio.run(extractor.extract(PRODUCTS_HTML, PRODUCT_SCHEMA))
    assert result["title"] == "全部产品"
    assert len(result["items"]) == 5
    assert result["items"][0]["name"] == "智能手表 Pro"
    assert result["items"][0]["price"] == "¥1299"


def test_xpath_extractor_products() -> None:
    import asyncio

    from tests.fixtures.site import PRODUCTS_HTML

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "xpath": "//h1"},
            "names": {
                "type": "array",
                "xpath": "//li[contains(@class,'product')]/h2",
                "items": {"type": "string"},
            },
        },
    }
    extractor = XPathExtractor()
    result = asyncio.run(extractor.extract(PRODUCTS_HTML, schema))
    assert result["title"] == "全部产品"
    assert result["names"] == ["智能手表 Pro", "无线耳机 Max", "便携充电宝 20000mAh", "机械键盘 K87", "显示器 27寸 4K"]


class FakeLLMClient(AsyncLLMClient):
    """返回固定 JSON 的假 LLM。"""

    async def chat(self, system: str, user: str) -> str:
        return '{"title": "Fake 标题", "count": 3}'


def test_llm_extractor_with_fake_client() -> None:
    import asyncio

    llm = LLMExtractor(client=FakeLLMClient())
    result = asyncio.run(llm.extract("<h1>hello</h1>", {"type": "object", "properties": {"title": {}}}))
    assert result == {"title": "Fake 标题", "count": 3}


def test_parse_json_response_tolerates_wrappers() -> None:
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_response('前后说明 {"a": 1} 结尾') == {"a": 1}


# ---------- Validator / Deduplicator ----------


def test_validator_required_fields() -> None:
    v = ExtractionValidator()
    ok, issues = v.validate({"title": "x"}, {"type": "object", "required": ["title", "price"]})
    assert not ok
    assert any(i.startswith("missing_required:price") for i in issues)
    ok2, _ = v.validate({"title": "x", "price": 100}, {"type": "object", "required": ["title", "price"]})
    assert ok2


def test_validator_type_check() -> None:
    v = ExtractionValidator()
    ok, issues = v.validate({"count": "not-a-number"}, {"type": "object", "properties": {"count": {"type": "integer"}}})
    assert not ok
    assert any(i.startswith("type_error") for i in issues)


def test_deduplicator() -> None:
    d = Deduplicator()
    text = "这是用于去重测试的一段重复文本内容，包含足够多的字符信息。"
    assert d.add(text) is False
    assert d.add(text) is True
    similar = text + "。加一点尾巴"
    assert d.is_duplicate(similar) is True


# ---------- Pipeline 集成 ----------


@pytest.mark.asyncio
async def test_pipeline_full_output(test_server: str) -> None:
    from chameleon.core.models import FetchRequest
    from chameleon.engines.http_engine import HttpEngine

    engine = HttpEngine()
    raw = await engine.fetch(FetchRequest(url=f"{test_server}/products"))
    await engine.close()

    pipeline = Pipeline()
    result = await pipeline.process(raw, output_format="markdown", schema=PRODUCT_SCHEMA)
    assert result.status == ScrapeStatus.SUCCESS
    assert result.title == "产品列表"
    assert result.content is not None
    assert "智能手表 Pro" in (result.content.markdown or "")
    assert result.extracted is not None
    assert len(result.extracted["items"]) == 5
    assert len(result.links) >= 5
    assert result.metadata.status_code == 200
    assert result.metadata.engine.value == "http"


@pytest.mark.asyncio
async def test_pipeline_links_filtered_honeypot(test_server: str) -> None:
    from chameleon.core.models import FetchRequest
    from chameleon.engines.http_engine import HttpEngine

    engine = HttpEngine()
    raw = await engine.fetch(FetchRequest(url=f"{test_server}/static"))
    await engine.close()
    pipeline = Pipeline()
    result = await pipeline.process(raw)
    assert f"{test_server}/blocked" in result.links
    assert f"{test_server}/static2" in result.links


@pytest.mark.asyncio
async def test_pipeline_error_schema() -> None:
    raw = FetchResult(url="http://x", status_code=200, content="<html><body><h1>a</h1></body></html>")
    pipeline = Pipeline()
    bad_schema: dict[str, Any] = {"type": "object", "required": ["nope"], "properties": {"nope": {"css": ".missing"}}}
    result = await pipeline.process(raw, schema=bad_schema)
    assert result.error is not None
    assert "missing_required" in (result.error or "")
