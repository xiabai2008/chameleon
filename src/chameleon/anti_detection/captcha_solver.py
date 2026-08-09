"""验证码处理：类型检测 → ddddocr 简单验证码 → 第三方 API → 上报（方案 5.2 CaptchaRouter）。"""

from __future__ import annotations

import base64
import re
from typing import Any

from chameleon.core.config import CaptchaConfig
from chameleon.core.exceptions import CaptchaRequiredError
from chameleon.infra.logging import get_logger

log = get_logger("captcha")

CAPTCHA_KEYWORDS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "请输入验证码",
    "验证码",
    "人机验证",
    "滑块验证",
    "滑动验证",
    "安全验证",
    "图形验证",
    "verify you are human",
)
_IMAGE_RE = re.compile(r'<img[^>]+src="([^"]*(?:data:image|/captcha|/verify)[^"]*)"', re.IGNORECASE)
_SLIDER_RE = re.compile(r"滑块|滑动验证|slider|drag", re.IGNORECASE)
_RECAPTCHA_RE = re.compile(r"recaptcha|hcaptcha", re.IGNORECASE)


class CaptchaDetector:
    """检测页面是否触发验证码及类型。"""

    @staticmethod
    def detect(html: str) -> str | None:
        """返回验证码类型：image | slider | recaptcha | text，未触发返回 None。"""
        lowered = html[:30000].lower()
        if _RECAPTCHA_RE.search(lowered):
            return "recaptcha"
        if _SLIDER_RE.search(lowered) and ("验证" in html or "verify" in lowered):
            return "slider"
        if _IMAGE_RE.search(html):
            return "image"
        if "请输入验证码" in html or "请输入验证码" in lowered:
            return "text"
        for keyword in CAPTCHA_KEYWORDS:
            if keyword in lowered:
                return "text"
        return None

    @staticmethod
    def extract_image(html: str) -> str | None:
        """提取验证码图片 URL（data URI 或路径）。"""
        match = _IMAGE_RE.search(html)
        return match.group(1) if match else None


class DdddocrSolver:
    """本地 OCR：简单数字/字母验证码。"""

    def __init__(self) -> None:
        self._ocr: Any | None = None

    def _ensure(self) -> Any:
        if self._ocr is None:
            import ddddocr  # type: ignore[import-untyped]

            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    def solve_bytes(self, image_bytes: bytes) -> str:
        return str(self._ensure().classification(image_bytes))

    def solve_data_uri(self, data_uri: str) -> str:
        if data_uri.startswith("data:"):
            _, encoded = data_uri.split(",", 1)
            return self.solve_bytes(base64.b64decode(encoded))
        return ""


class ThirdPartySolver:
    """第三方打码服务（CapSolver/2Captcha 风格，预留接口）。"""

    def __init__(self, config: CaptchaConfig) -> None:
        self.provider = config.provider
        self.api_key = config.api_key

    async def solve(self, detected_type: str, image_data: str | None = None) -> str:
        """按 provider 调用对应 API。未配置返回空串（表示无法自动解决）。"""
        if not self.api_key:
            return ""
        log.info("third_party_captcha_requested", provider=self.provider, captcha_type=detected_type)
        # CapSolver: POST https://api.capsolver.com/createTask (taskType: ImageToTextTask / ReCaptchaV3TaskProxyLess)
        # 2Captcha:  POST https://2captcha.com/in.php
        # 具体协议按 API key 配置实现；未实现前返回空串走人工路径
        return ""


class CaptchaRouter:
    """验证码路由：检测 → 本地 OCR / 第三方 → 失败上报。"""

    def __init__(self, config: CaptchaConfig | None = None, detector: CaptchaDetector | None = None) -> None:
        self.config = config or CaptchaConfig()
        self.detector = detector or CaptchaDetector()
        self.local_solver = DdddocrSolver()
        self.third_party = ThirdPartySolver(self.config)

    def detect(self, html: str) -> str | None:
        return self.detector.detect(html)

    async def solve(self, html: str) -> tuple[bool, str, str | None]:
        """尝试解决页面中的验证码。

        返回 (是否解决, 验证码类型, 识别文本)。未解决时调用方应抛 CaptchaRequiredError。
        """
        captcha_type = self.detect(html)
        if captcha_type is None:
            return True, "none", None
        if captcha_type == "image":
            image = self.detector.extract_image(html)
            if image:
                if image.startswith("data:"):
                    try:
                        text = self.local_solver.solve_data_uri(image)
                        if text:
                            return True, "image", text
                    except Exception as exc:
                        log.warning("ddddocr_failed", error=str(exc))
                text = await self.third_party.solve("image", image)
                if text:
                    return True, "image", text
        else:
            text = await self.third_party.solve(captcha_type)
            if text:
                return True, captcha_type, text
        return False, captcha_type, None

    def require_solve(self, html: str) -> None:
        """检测到验证码且无法自动解决时抛 CaptchaRequiredError。"""
        captcha_type = self.detect(html)
        if captcha_type is not None:
            raise CaptchaRequiredError(f"captcha triggered: {captcha_type}")
