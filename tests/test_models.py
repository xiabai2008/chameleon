"""数据模型测试：统一输出结构必须与方案 6.4 对齐。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from chameleon.core.exceptions import CaptchaRequiredError, ScrapeStatus
from chameleon.core.models import (
    ContentOutput,
    EngineType,
    FetchResult,
    ScrapeMetadata,
    ScrapeResult,
)


def test_scrape_result_complete_structure() -> None:
    result = ScrapeResult(
        status=ScrapeStatus.SUCCESS,
        url="https://example.com",
        title="Example",
        content=ContentOutput(markdown="# Example"),
        extracted={"price": 100},
        metadata=ScrapeMetadata(url="https://example.com", engine=EngineType.HTTP, retries=1),
        links=["https://example.com/a"],
        images=["https://example.com/i.png"],
    )
    data = result.model_dump()
    assert data["status"] == "success"
    assert data["content"]["markdown"] == "# Example"
    assert data["metadata"]["engine"] == "http"
    assert data["links"] == ["https://example.com/a"]
    assert isinstance(data["metadata"]["timestamp"], datetime)


def test_fetch_result_defaults() -> None:
    fr = FetchResult(url="https://example.com")
    assert fr.status_code is None
    assert fr.content == ""
    assert fr.engine == EngineType.HTTP
    assert fr.response_time_ms == 0


def test_error_status_mapping() -> None:
    err = CaptchaRequiredError("captcha")
    assert err.status == ScrapeStatus.CAPTCHA_REQUIRED
    assert err.suggested_action == "solve_captcha_or_retry_later"


def test_invalid_url_rejected() -> None:
    from chameleon.core.models import ScrapeRequest

    with pytest.raises(ValidationError):
        ScrapeRequest(url="not-a-url")  # type: ignore[arg-type]
