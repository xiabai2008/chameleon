"""高级反爬（P4）测试：TLS 引擎、升级链、行为模拟、验证码、Shadow DOM、无限滚动。"""

from __future__ import annotations

import pytest

from chameleon.anti_detection.behavior_simulator import BehaviorSimulator
from chameleon.anti_detection.captcha_solver import CaptchaDetector, CaptchaRouter
from chameleon.core.config import BehaviorConfig
from chameleon.core.exceptions import CaptchaRequiredError
from chameleon.core.models import EngineType, FetchRequest, FetchResult
from chameleon.core.router import SmartRouter
from chameleon.engines.base import BaseEngine
from chameleon.engines.tls_engine import TlsHttpEngine

# ---------- CaptchaDetector ----------


def test_captcha_detector_types() -> None:
    detector = CaptchaDetector()
    assert detector.detect("<html>请输入验证码</html>") is not None
    assert detector.detect("<html>滑块拖动验证</html>") == "slider"
    assert detector.detect('<img src="/captcha.jpg">') == "image"
    assert detector.detect('<script src="recaptcha.js">') == "recaptcha"
    assert detector.detect("<html>正常内容</html>") is None


def test_captcha_router_detects_captcha_page() -> None:
    from tests.fixtures.site import CAPTCHA_PAGE

    router = CaptchaRouter()
    captcha_type = router.detect(CAPTCHA_PAGE)
    assert captcha_type is not None
    with pytest.raises(CaptchaRequiredError):
        router.require_solve(CAPTCHA_PAGE)


# ---------- BehaviorSimulator ----------


def test_behavior_interval_within_bounds() -> None:
    sim = BehaviorSimulator(BehaviorConfig(min_interval=2.0, max_interval=10.0))
    intervals = [sim.next_interval() for _ in range(200)]
    assert all(2.0 <= i <= 10.0 for i in intervals)
    assert len(set(intervals)) > 5  # 有变化


@pytest.mark.asyncio
async def test_behavior_scroll_mock() -> None:
    sim = BehaviorSimulator()

    class FakePage:
        def __init__(self) -> None:
            self.scroll_y = 0

        class Mouse:
            async def move(self, x: int, y: int, steps: int = 1) -> None:
                pass

        mouse = Mouse()

        async def evaluate(self, expr: str) -> int | bool:
            if "scrollBy" in expr:
                self.scroll_y += 400
                return True
            if "scrollY" in expr:
                return self.scroll_y + 900 >= 3000
            return 0

    await sim.human_scroll(FakePage(), steps=3, delay=0.01)
    await sim.human_mouse_trail(FakePage())


# ---------- TLS 引擎 ----------


@pytest.mark.asyncio
async def test_tls_engine_fetch(test_server: str) -> None:
    engine = TlsHttpEngine()
    result = await engine.fetch(FetchRequest(url=f"{test_server}/static"))
    assert result.status_code == 200
    assert "静态页面标题" in result.content
    assert result.engine == EngineType.HTTP_STEALTH
    await engine.close()


# ---------- 升级链 ----------


class _FakeEngine(BaseEngine):
    """按 URL 返回预设结果的假引擎。"""

    name = EngineType.HTTP

    def __init__(self, name: EngineType, sequence: list[FetchResult]) -> None:
        self.name = name
        self.sequence = sequence
        self.calls: list[FetchRequest] = []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        self.calls.append(request)
        return self.sequence.pop(0)

    async def close(self) -> None:
        pass


def _make_result(engine: EngineType, content: str, status: int = 200) -> FetchResult:
    return FetchResult(url="http://x", status_code=status, content=content, engine=engine)


class SequenceEngine(BaseEngine):
    """按顺序返回预设结果/抛异常，记录调用次数。"""

    name = EngineType.HTTP

    def __init__(self, *results: FetchResult | Exception) -> None:
        self.results = list(results)
        self.calls = 0

    async def fetch(self, request: FetchRequest) -> FetchResult:
        item = self.results.pop(0)
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_escalation_chain_l0_l1() -> None:
    """L0 失败（403）→ L1 成功。"""
    from chameleon.core.exceptions import BlockedError

    engine = SequenceEngine(
        BlockedError("blocked", status_code=403),
        _make_result(EngineType.HTTP, "x" * 600 + "有效内容" * 20),
    )
    router = SmartRouter(http_engine=engine)  # type: ignore[arg-type]
    result = await router.fetch(FetchRequest(url="http://x"))
    assert result.escalation_level == 1
    assert engine.calls == 2


@pytest.mark.asyncio
async def test_escalation_chain_full_failure_reports_blocked() -> None:
    """全部失败且最后一步 403 → BlockedError。"""
    from chameleon.core.exceptions import BlockedError

    engine = SequenceEngine(*[BlockedError("blocked", status_code=403)] * 6)
    router = SmartRouter(http_engine=engine)  # type: ignore[arg-type]
    with pytest.raises(BlockedError) as excinfo:
        await router.fetch(FetchRequest(url="http://x"))
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_captcha_page_raises_captcha_required() -> None:
    """内容触发验证码 → CaptchaRequiredError。"""
    from tests.fixtures.site import CAPTCHA_PAGE

    class FakeCaptchaEngine(BaseEngine):
        name = EngineType.HTTP

        async def fetch(self, request: FetchRequest) -> FetchResult:
            return _make_result(EngineType.HTTP, CAPTCHA_PAGE)

        async def close(self) -> None:
            pass

    from chameleon.anti_detection.captcha_solver import CaptchaRouter

    router = SmartRouter(
        http_engine=FakeCaptchaEngine(),  # type: ignore[arg-type]
        captcha_router=CaptchaRouter(),
    )
    with pytest.raises(CaptchaRequiredError):
        await router.fetch(FetchRequest(url="http://x/captcha"))


# ---------- 浏览器增强 ----------


@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_shadow_dom_extraction(test_server: str) -> None:
    from chameleon.engines.browser_engine import BrowserEngine

    browser = BrowserEngine(pool_size=1, headless=True, extract_shadow=True)
    result = await browser.fetch(FetchRequest(url=f"{test_server}/shadow"))
    assert "Shadow 内部标题" in result.content
    await browser.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_infinite_scroll(test_server: str) -> None:
    from chameleon.engines.browser_engine import BrowserEngine

    browser = BrowserEngine(pool_size=1, headless=True, infinite_scroll=True)
    result = await browser.fetch(FetchRequest(url=f"{test_server}/infinite"))
    assert "滚动加载项" in result.content
    assert result.content.count("滚动加载项") >= 10  # 初始 5 项 + 滚动追加
    await browser.close()


@pytest.mark.browser
@pytest.mark.asyncio
async def test_browser_websocket_frame_interception(test_server: str) -> None:
    """WebSocket 帧拦截：收集页面 WS 收到的推送消息。"""
    from chameleon.engines.browser_engine import BrowserEngine

    browser = BrowserEngine(pool_size=1, headless=True)
    frames = await browser.collect_websocket_frames(f"{test_server}/ws-page", timeout_ms=3000)
    received = [f["data"] for f in frames if f["type"] == "received"]
    assert any("tick-" in d for d in received), f"frames={frames}"
    await browser.close()
