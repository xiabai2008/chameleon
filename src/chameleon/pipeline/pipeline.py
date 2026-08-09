"""处理管线门面：FetchResult → ScrapeResult（方案 5.3 完整流水线）。"""

from __future__ import annotations

from typing import Any

from chameleon.anti_detection.honeypot_filter import HoneypotFilter
from chameleon.core.exceptions import ScrapeStatus
from chameleon.core.models import (
    ContentOutput,
    FetchResult,
    ScrapeMetadata,
    ScrapeResult,
)
from chameleon.pipeline.cleaner import Cleaner
from chameleon.pipeline.converter import Converter, FitMarkdown
from chameleon.pipeline.extractors.base import BaseExtractor
from chameleon.pipeline.extractors.css_extractor import CssExtractor
from chameleon.pipeline.extractors.hybrid_extractor import HybridExtractor
from chameleon.pipeline.extractors.llm_extractor import LLMExtractor
from chameleon.pipeline.validator import ExtractionValidator
from chameleon.utils.url_utils import resolve_url


class Pipeline:
    """处理管线：清洗 → Markdown → 裁剪 → 提取 → 校验 → 统一输出。"""

    def __init__(
        self,
        *,
        cleaner: Cleaner | None = None,
        converter: Converter | None = None,
        fitter: FitMarkdown | None = None,
        validator: ExtractionValidator | None = None,
        honeypot: HoneypotFilter | None = None,
        extractors: dict[str, BaseExtractor] | None = None,
        llm: LLMExtractor | None = None,
        default_max_tokens: int = 8000,
    ) -> None:
        self.cleaner = cleaner or Cleaner()
        self.converter = converter or Converter()
        self.fitter = fitter or FitMarkdown(default_max_tokens=default_max_tokens)
        self.validator = validator or ExtractionValidator()
        self.honeypot = honeypot or HoneypotFilter()
        self.extractors = extractors or {
            "css": CssExtractor(),
            "xpath": CssExtractor(),  # xpath 在 strategy=xpath 时切换
        }
        self.llm = llm
        self.default_max_tokens = default_max_tokens

    def _get_extractor(self, strategy: str) -> BaseExtractor:
        if strategy == "xpath":
            from chameleon.pipeline.extractors.css_extractor import XPathExtractor

            return XPathExtractor()
        if strategy == "llm":
            if self.llm is None:
                raise RuntimeError("llm 提取需要配置 LLMExtractor")
            return self.llm
        if strategy == "hybrid":
            if self.llm is None:
                return self.extractors["css"]
            return HybridExtractor(self.llm)
        return self.extractors["css"]

    async def process(
        self,
        result: FetchResult,
        *,
        output_format: str = "markdown",
        schema: dict[str, Any] | None = None,
        extract_prompt: str | None = None,
        strategy: str = "auto",
        max_output_tokens: int | None = None,
    ) -> ScrapeResult:
        """FetchResult → 完整 ScrapeResult（方案 6.4 结构）。"""
        html = result.content or ""
        title, main_html = self.cleaner.clean(html)
        base_url = result.final_url or result.url

        markdown: str | None = None
        if output_format in ("markdown", "json"):
            markdown = self.converter.to_markdown(main_html, base_url)
            markdown = self.fitter.fit(markdown, max_tokens=max_output_tokens or self.default_max_tokens)

        extracted: dict[str, Any] | None = None
        validation_issues: list[str] = []
        if schema:
            selected = "llm" if extract_prompt else strategy
            if selected == "auto":
                selected = "hybrid" if self.llm is not None else "css"
            try:
                extractor = self._get_extractor(selected)
                extracted = await extractor.extract(html, schema, base_url)
            except Exception as exc:
                extracted = None
                validation_issues.append(f"extract_error:{exc}")
            if extracted is not None:
                ok, issues = self.validator.validate(extracted, schema)
                validation_issues.extend(issues)

        links = self.honeypot.filter_links(html, base_url)
        images = self._extract_images(html, base_url)

        return ScrapeResult(
            status=ScrapeStatus.SUCCESS,
            url=result.url,
            title=title,
            content=ContentOutput(
                markdown=markdown,
                html=main_html if output_format == "html" else None,
                raw_html=html,
            ),
            extracted=extracted,
            metadata=ScrapeMetadata(
                url=result.url,
                final_url=result.final_url,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                content_length=len(html),
                engine=result.engine,
                escalation_level=result.escalation_level,
                proxy_used=result.proxy_used,
                retries=result.retries,
            ),
            links=links,
            images=images,
            error="; ".join(validation_issues) if validation_issues else None,
            suggested_action="adjust_schema" if any(v.startswith("missing_required") for v in validation_issues) else None,
        )

    def _extract_images(self, html: str, base_url: str) -> list[str]:
        from selectolax.parser import HTMLParser

        images: list[str] = []
        try:
            tree = HTMLParser(html)
            for img in tree.css("img[src]"):
                src = img.attributes.get("src") or ""
                resolved = resolve_url(base_url, src)
                if resolved:
                    images.append(resolved)
        except Exception:
            pass
        return images
