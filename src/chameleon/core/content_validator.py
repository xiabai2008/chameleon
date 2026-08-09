"""内容校验器：HTTP 200 不等于内容有效。"""

from __future__ import annotations

import re

from chameleon.core.models import FetchResult

_JS_MOUNT_POINTS = re.compile(r"<div[^>]+\bid\s*=\s*[\"'](app|root|__nuxt|__next|main)[\"']", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)


def _visible_text_len(html: str) -> int:
    text = _TAG_RE.sub(" ", html)
    return len(re.sub(r"\s+", " ", text).strip())


class ContentValidator:
    """判断 FetchResult 的内容是否真实有效。

    校验维度：
    1. 状态码（403/429 直接无效）
    2. 内容长度下限（< 阈值可能是 JS 渲染空壳）
    3. 反爬关键词（中英文验证码/拦截页面）
    4. JS 渲染壳检测（有效但可见文本极少 + 存在挂载点 → 疑似 SPA 初始壳）
    """

    def __init__(self, min_content_length: int = 500) -> None:
        self.min_content_length = min_content_length
        self.anti_bot_markers: tuple[str, ...] = (
            "captcha",
            "access denied",
            "please verify you are a human",
            "challenge",
            "请输入验证码",
            "验证码",
            "访问被拒绝",
            "请开启javascript",
            "您的请求被拦截",
            "人机验证",
            "滑动验证",
        )

    def is_valid(self, result: FetchResult) -> tuple[bool, str | None]:
        """返回 (是否有效, 失败原因)。失败原因用于日志与策略决策。"""
        if result.error:
            return False, result.error
        if result.status_code in (403, 429):
            return False, f"blocked_status_{result.status_code}"
        if result.status_code is not None and result.status_code >= 400:
            return False, f"http_{result.status_code}"
        if len(result.content) < self.min_content_length:
            return False, "content_too_short"
        lowered = result.content[:20000].lower()
        for marker in self.anti_bot_markers:
            if marker in lowered:
                return False, f"anti_bot_marker:{marker}"
        return True, None

    def is_js_shell(self, result: FetchResult) -> bool:
        """内容有效但疑似 JS 渲染壳（SPA 初始 HTML），应升级浏览器引擎。"""
        if not self.is_valid(result)[0]:
            return False
        return bool(_JS_MOUNT_POINTS.search(result.content)) and _visible_text_len(result.content) < self.min_content_length
