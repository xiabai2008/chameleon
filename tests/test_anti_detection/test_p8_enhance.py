"""P8 增强测试：第三方 Provider + 验证码模板训练。"""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from chameleon.interfaces.providers.base import ProviderError, provider_result
from chameleon.interfaces.providers.brightdata import BrightDataProvider
from chameleon.interfaces.providers.firecrawl import FirecrawlProvider

# ---------- provider_result ----------


def test_provider_result_wraps_markdown() -> None:
    result = provider_result("http://x", "# Title", "provider:test")
    assert result.status.value == "success"
    assert result.content is not None and result.content.markdown == "# Title"
    assert result.metadata.engine == "provider:test"
    assert result.metadata.content_length == len("# Title")


# ---------- FirecrawlProvider ----------


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_scrape_success() -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(
        return_value=Response(200, json={"success": True, "data": {"markdown": "# Hello Firecrawl"}})
    )
    provider = FirecrawlProvider("sk-test")
    result = await provider.scrape("https://example.com")
    assert result is not None
    assert result.content.markdown == "# Hello Firecrawl"
    assert result.metadata.engine == "provider:firecrawl"
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_scrape_not_success() -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(
        return_value=Response(200, json={"success": False, "data": {}})
    )
    provider = FirecrawlProvider("sk-test")
    assert await provider.scrape("https://example.com") is None
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_scrape_empty_content() -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(
        return_value=Response(200, json={"success": True, "data": {"markdown": ""}})
    )
    provider = FirecrawlProvider("sk-test")
    assert await provider.scrape("https://example.com") is None
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_unauthorized() -> None:
    respx.post("https://api.firecrawl.dev/v1/scrape").mock(return_value=Response(401, json={}))
    provider = FirecrawlProvider("bad-key")
    with pytest.raises(ProviderError):
        await provider.scrape("https://example.com")
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    provider = FirecrawlProvider("sk-test")

    async def boom(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(provider._client, "post", boom)  # noqa: SLF001
    with pytest.raises(ProviderError):
        await provider.scrape("https://example.com")
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_search_success() -> None:
    respx.post("https://api.firecrawl.dev/v1/search").mock(
        return_value=Response(
            200,
            json={"success": True, "data": [{"title": "T", "url": "http://x", "description": "d"}]},
        )
    )
    provider = FirecrawlProvider("sk-test")
    results = await provider.search("python")
    assert results == [{"title": "T", "url": "http://x", "snippet": "d"}]
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_firecrawl_crawl_polls_job() -> None:
    respx.post("https://api.firecrawl.dev/v1/crawl").mock(
        return_value=Response(201, json={"success": True, "data": {"id": "job-1"}})
    )
    respx.get("https://api.firecrawl.dev/v1/crawl/job-1").mock(
        return_value=Response(
            200,
            json={"success": True, "data": {"status": "completed", "pages": [{"url": "http://x/1", "markdown": "# p1"}]}},
        )
    )
    provider = FirecrawlProvider("sk-test")
    pages = await provider.crawl("https://example.com")
    assert pages is not None and len(pages) == 1
    assert pages[0].content.markdown == "# p1"
    await provider.close()


# ---------- BrightDataProvider ----------


def test_brightdata_proxy_url_format() -> None:
    provider = BrightDataProvider("cust1", zone="web_unlocker", password="pass123")
    assert provider.proxy_url() == "http://brd-customer-cust1-zone-web_unlocker:pass123@brd.superproxy.io:33335"


@respx.mock
@pytest.mark.asyncio
async def test_brightdata_scrape_success() -> None:
    respx.get("https://example.com").mock(return_value=Response(200, text="<h1>Unlocked</h1><p>content</p>"))
    provider = BrightDataProvider("cust1", password="pass")
    result = await provider.scrape("https://example.com")
    assert result is not None
    assert "Unlocked" in (result.content.markdown or "")
    assert result.metadata.engine == "provider:brightdata"
    await provider.close()


@respx.mock
@pytest.mark.asyncio
async def test_brightdata_scrape_blocked() -> None:
    respx.get("https://example.com").mock(return_value=Response(403, text="denied"))
    provider = BrightDataProvider("cust1", password="pass")
    assert await provider.scrape("https://example.com") is None
    await provider.close()


# ---------- 验证码模板训练闭环 ----------


@pytest.fixture(scope="module")
def trained_model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from tests.fixtures import captcha_gen

    from chameleon.anti_detection.captcha_trainer import TemplateTrainer

    sample_dir = tmp_path_factory.mktemp("captcha_samples")
    captcha_gen.generate_labeled_dataset(n_per_char=30, out_dir=sample_dir)
    model_path = tmp_path_factory.mktemp("models") / "captcha.npz"
    TemplateTrainer(sample_dir).train(model_path)
    return model_path


def test_trainer_rejects_missing_dir(tmp_path: Path) -> None:
    from chameleon.anti_detection.captcha_trainer import TemplateTrainer

    with pytest.raises(FileNotFoundError):
        TemplateTrainer(tmp_path / "nope").train(tmp_path / "out.npz")


def test_trainer_rejects_no_samples(tmp_path: Path) -> None:
    from chameleon.anti_detection.captcha_trainer import TemplateTrainer

    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError):
        TemplateTrainer(tmp_path).train(tmp_path / "out.npz")


def test_recognizer_accuracy_on_unseen_samples(trained_model: Path) -> None:
    from tests.fixtures import captcha_gen

    from chameleon.anti_detection.captcha_trainer import TemplateRecognizer

    recognizer = TemplateRecognizer(trained_model)
    samples = captcha_gen.generate_test_samples(n=20, text_len=4, seed=7)
    accuracy = recognizer.recognize_accuracy(samples)
    assert accuracy >= 0.8, f"accuracy too low: {accuracy:.0%}"


def test_recognizer_invalid_image(trained_model: Path) -> None:
    from chameleon.anti_detection.captcha_trainer import TemplateRecognizer

    recognizer = TemplateRecognizer(trained_model)
    with pytest.raises(ValueError):
        recognizer.recognize(b"not an image")


def test_captcha_text_validation() -> None:
    from chameleon.anti_detection.captcha_trainer import is_valid_captcha_text

    assert is_valid_captcha_text("aB34")
    assert not is_valid_captcha_text("")
    assert not is_valid_captcha_text("ab")
    assert not is_valid_captcha_text("abcd ef")
    assert not is_valid_captcha_text("abcd!")
    assert not is_valid_captcha_text("a" * 9)


# ---------- SDK provider 兜底集成 ----------


@pytest.mark.asyncio
async def test_sdk_provider_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from chameleon.core.config import ProviderConfig, Settings
    from chameleon.interfaces.sdk import Chameleon

    settings = Settings()
    settings.provider = ProviderConfig(enabled=True, type="firecrawl", api_key="sk-test")
    service = Chameleon(settings)

    captured: list[str] = []

    class _FakeProvider:
        name = "provider:fake"

        async def scrape(self, url: str, *, output_format: str) -> object:
            captured.append(url)
            return provider_result(url, "# 兜底成功", self.name)

    service.provider = _FakeProvider()  # type: ignore[assignment]

    # 引擎失败（127.0.0.1:1 不可达）→ 兜底
    result = await service.scrape("http://127.0.0.1:1/nope")
    assert result.status.value == "success"
    assert result.metadata.engine == "provider:fake"
    assert captured == ["http://127.0.0.1:1/nope"]
    await service.close()


@pytest.mark.asyncio
async def test_sdk_provider_fallback_disabled() -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    assert service.provider is None  # 默认关闭
    result = await service.scrape("http://127.0.0.1:1/nope")
    assert result.status.value == "error"  # 无兜底，走错误路径
    await service.close()


@pytest.mark.asyncio
async def test_sdk_brightdata_provider_build() -> None:
    from chameleon.core.config import ProviderConfig, Settings
    from chameleon.interfaces.sdk import Chameleon

    settings = Settings()
    settings.provider = ProviderConfig(
        enabled=True, type="brightdata", customer="cust1", zone_password="pw"
    )
    service = Chameleon(settings)
    assert service.provider is not None
    assert service.provider.name == "provider:brightdata"
    assert "brd-customer-cust1" in service.provider.proxy_url()  # type: ignore[attr-defined]
    await service.close()
