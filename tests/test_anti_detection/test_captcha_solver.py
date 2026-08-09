"""captcha_solver 补强测试（覆盖率 69% → 90%+）。"""

from __future__ import annotations

import pytest

from chameleon.anti_detection.captcha_solver import (
    CaptchaDetector,
    CaptchaRouter,
    DdddocrSolver,
    ThirdPartySolver,
)
from chameleon.core.config import CaptchaConfig
from chameleon.core.exceptions import CaptchaRequiredError

DATA_URI = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


# ---------- CaptchaDetector ----------


def test_detect_all_types() -> None:
    d = CaptchaDetector()
    assert d.detect("<html>请输入验证码</html>") == "text"
    assert d.detect("<html>请输入验证码 4 位数字</html>") == "text"
    assert d.detect("<html>滑块拖动至最右完成验证</html>") == "slider"
    assert d.detect('<img src="/captcha.php?id=1">') == "image"
    assert d.detect('<img src="data:image/png;base64,AAAA">') == "image"
    assert d.detect('<div class="g-recaptcha"></div>') == "recaptcha"
    assert d.detect('<script src="hcaptcha.js"></script>') == "recaptcha"
    assert d.detect("<html>正常内容页面</html>") is None
    assert d.detect("") is None


def test_detect_image_path_variants() -> None:
    d = CaptchaDetector()
    assert d.detect('<img src="/captcha">') == "image"
    assert d.detect('<img src="/verify-code.jpg">') == "image"


def test_extract_image() -> None:
    d = CaptchaDetector()
    assert d.extract_image(f'<img src="{DATA_URI}">') == DATA_URI
    assert d.extract_image('<img src="/captcha.png">') == "/captcha.png"
    assert d.extract_image("<html>无验证码图片</html>") is None


# ---------- DdddocrSolver ----------


class _FakeOcr:
    def classification(self, image: bytes) -> str:
        return "abcd"


def test_ddddocr_solver_with_fake_ocr(monkeypatch: pytest.MonkeyPatch) -> None:

    solver = DdddocrSolver()
    monkeypatch.setattr(solver, "_ensure", lambda: _FakeOcr())
    assert solver.solve_bytes(b"fake-image-bytes") == "abcd"
    assert solver.solve_data_uri(DATA_URI) == "abcd"


def test_ddddocr_solve_data_uri_invalid() -> None:
    solver = DdddocrSolver()
    assert solver.solve_data_uri("http://not-a-data-uri") == ""


def test_ddddocr_ensure_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from types import SimpleNamespace

    calls: list[str] = []

    class _FakeOcr:
        def __init__(self, show_ad: bool) -> None:
            calls.append("init")

        def classification(self, image: bytes) -> str:
            return "x"

    monkeypatch.setitem(sys.modules, "ddddocr", SimpleNamespace(DdddOcr=_FakeOcr))
    solver = DdddocrSolver()
    solver._ensure()
    solver._ensure()
    assert len(calls) == 1  # 缓存


# ---------- ThirdPartySolver ----------


@pytest.mark.asyncio
async def test_third_party_no_key_returns_empty() -> None:
    solver = ThirdPartySolver(CaptchaConfig(provider="capsolver", api_key=""))
    assert await solver.solve("image", "data") == ""


@pytest.mark.asyncio
async def test_third_party_with_key_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """有 key 但未实现协议 → 空串（走人工路径），记录日志。"""
    import chameleon.anti_detection.captcha_solver as mod

    log_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(mod.log, "info", lambda msg, **kw: log_calls.append((msg, kw.get("provider", ""))))
    solver = ThirdPartySolver(CaptchaConfig(provider="capsolver", api_key="sk-test"))
    assert await solver.solve("recaptcha") == ""
    assert log_calls and log_calls[0][0] == "third_party_captcha_requested"


# ---------- CaptchaRouter ----------


@pytest.mark.asyncio
async def test_router_no_captcha() -> None:
    router = CaptchaRouter()
    solved, ctype, text = await router.solve("<html>正常页面</html>")
    assert (solved, ctype, text) == (True, "none", None)


@pytest.mark.asyncio
async def test_router_image_captcha_solved_by_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    router = CaptchaRouter()
    monkeypatch.setattr(router.local_solver, "solve_data_uri", lambda uri: "1234")
    html = f'<img src="{DATA_URI}"><p>请输入验证码</p>'
    solved, ctype, text = await router.solve(html)
    assert (solved, ctype, text) == (True, "image", "1234")


@pytest.mark.asyncio
async def test_router_image_ocr_failure_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """OCR 抛异常 → 日志 + 走第三方（无 key）→ 未解决。"""
    import chameleon.anti_detection.captcha_solver as mod

    router = CaptchaRouter()
    warnings: list[str] = []
    monkeypatch.setattr(mod.log, "warning", lambda msg, **kw: warnings.append(msg))

    def boom(_uri: str) -> str:
        raise RuntimeError("ocr crash")

    monkeypatch.setattr(router.local_solver, "solve_data_uri", boom)
    html = f'<img src="{DATA_URI}">'
    solved, ctype, text = await router.solve(html)
    assert solved is False
    assert ctype == "image"
    assert warnings == ["ddddocr_failed"]


@pytest.mark.asyncio
async def test_router_image_third_party_solves(monkeypatch: pytest.MonkeyPatch) -> None:
    router = CaptchaRouter()
    monkeypatch.setattr(router.local_solver, "solve_data_uri", lambda uri: "")

    async def fake_third(_t: str, _img: str | None = None) -> str:
        return "9999"

    monkeypatch.setattr(router.third_party, "solve", fake_third)
    html = f'<img src="{DATA_URI}">'
    solved, ctype, text = await router.solve(html)
    assert (solved, ctype, text) == (True, "image", "9999")


@pytest.mark.asyncio
async def test_router_slider_unsolved(monkeypatch: pytest.MonkeyPatch) -> None:
    router = CaptchaRouter()

    async def fake_third(_t: str, _img: str | None = None) -> str:
        return ""

    monkeypatch.setattr(router.third_party, "solve", fake_third)
    solved, ctype, _ = await router.solve("<html>滑块拖动验证</html>")
    assert (solved, ctype) == (False, "slider")


@pytest.mark.asyncio
async def test_router_slider_third_party_solves(monkeypatch: pytest.MonkeyPatch) -> None:
    router = CaptchaRouter()

    async def fake_third(_t: str, _img: str | None = None) -> str:
        return "token-abc"

    monkeypatch.setattr(router.third_party, "solve", fake_third)
    solved, ctype, text = await router.solve("<html>滑块拖动验证</html>")
    assert (solved, ctype, text) == (True, "slider", "token-abc")


def test_router_require_solve_raises() -> None:
    router = CaptchaRouter()
    with pytest.raises(CaptchaRequiredError) as excinfo:
        router.require_solve("<html>请输入验证码</html>")
    assert "text" in str(excinfo.value)
    router.require_solve("<html>正常</html>")  # 不抛


def test_router_detect_delegates() -> None:
    router = CaptchaRouter(detector=CaptchaDetector())
    assert router.detect("<html>captcha</html>") == "text"


# ---------- 可选依赖缺失兜底 ----------


def test_ddddocr_import_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """ddddocr 未安装时 _ensure 抛 ImportError（调用方有 try/except 兜底）。"""
    import sys

    monkeypatch.setitem(sys.modules, "ddddocr", None)
    solver = DdddocrSolver()
    solver._ocr = None  # type: ignore[assignment]
    with pytest.raises(ImportError):
        solver._ensure()
