"""数据模型（Pydantic v2）：与方案 6.4 统一输出结构严格对齐。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from chameleon.core.exceptions import ScrapeStatus


class EngineType(StrEnum):
    HTTP = "http"
    HTTP_STEALTH = "http_stealth"
    BROWSER = "browser"
    API = "api"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScrapeMetadata(BaseModel):
    """采集过程信息，帮助 Agent 判断结果可信度。"""

    model_config = ConfigDict(extra="allow")

    url: str
    final_url: str | None = None
    status_code: int | None = None
    response_time_ms: int = 0
    content_length: int = 0
    language: str | None = None
    engine: EngineType = EngineType.HTTP
    escalation_level: int = 0
    proxy_used: str | None = None
    retries: int = 0
    stealth_level: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FetchResult(BaseModel):
    """引擎层原始输出（HTTP/Browser 统一接口）。"""

    model_config = ConfigDict(extra="allow")

    url: str
    final_url: str | None = None
    status_code: int | None = None
    content: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    engine: EngineType = EngineType.HTTP
    proxy_used: str | None = None
    response_time_ms: int = 0
    escalation_level: int = 0
    retries: int = 0
    error: str | None = None


class FetchRequest(BaseModel):
    """引擎层统一请求参数。"""

    model_config = ConfigDict(extra="allow")

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float | None = None
    wait_for: str | None = None
    js_render: bool = False
    proxy: str | None = None
    cookies: list[dict[str, str]] = Field(default_factory=list)
    max_output_tokens: int = 0


class ContentOutput(BaseModel):
    """三种粒度的内容输出。"""

    model_config = ConfigDict(extra="allow")

    markdown: str | None = None
    html: str | None = None
    raw_html: str | None = None


class ScrapeResult(BaseModel):
    """统一输出结构（方案 6.4）。"""

    model_config = ConfigDict(extra="allow")

    status: ScrapeStatus = ScrapeStatus.SUCCESS
    url: str
    title: str | None = None
    content: ContentOutput | None = None
    extracted: dict[str, Any] | None = None
    metadata: ScrapeMetadata
    links: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    error: str | None = None
    suggested_action: str | None = None


class CrawlJob(BaseModel):
    """深度爬取任务状态。"""

    model_config = ConfigDict(extra="allow")

    job_id: str
    url: str
    status: JobStatus = JobStatus.QUEUED
    strategy: str = "adaptive"
    max_pages: int = 50
    pages_crawled: int = 0
    pages_failed: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    results: list[str] = Field(default_factory=list)
    error: str | None = None


class ExtractionSchema(BaseModel):
    """结构化提取 Schema（JSON Schema 子集 + 提取配置）。"""

    model_config = ConfigDict(extra="allow")

    base_schema: dict[str, Any] = Field(default_factory=dict)
    strategy: str = "auto"
    name: str | None = None


class ProxyInfo(BaseModel):
    """代理信息与健康状态。"""

    model_config = ConfigDict(extra="allow")

    proxy: str
    region: str | None = None
    score: int = 50
    alive: bool = True
    last_checked: datetime | None = None
    response_time_ms: int | None = None


class ScrapeRequest(BaseModel):
    """REST API / SDK 统一请求模型。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    url: HttpUrl
    mode: str = "auto"
    output_format: str = "markdown"
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")
    extract_prompt: str | None = None
    wait_for: str | None = None
    proxy_region: str | None = None
    stealth_level: str = "medium"
    timeout: float | None = None
    retry: int = 3
    max_output_tokens: int = 8000
