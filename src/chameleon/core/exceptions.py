"""异常体系：每个异常携带统一的输出状态，可无缝映射到 ScrapeResult.status。"""

from __future__ import annotations

from enum import StrEnum


class ScrapeStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    CAPTCHA_REQUIRED = "captcha_required"
    RATE_LIMITED = "rate_limited"


class ChameleonError(Exception):
    """所有 Chameleon 异常的基类。

    status: 对应统一输出结构中的 status 字段。
    suggested_action: 给 Agent 的下一步行动建议。
    """

    status: ScrapeStatus = ScrapeStatus.ERROR
    suggested_action: str = "retry"

    def __init__(self, message: str = "", *, status: ScrapeStatus | None = None, suggested_action: str | None = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status
        if suggested_action is not None:
            self.suggested_action = suggested_action


class ConfigError(ChameleonError):
    """配置错误（YAML 缺失/非法、冲突配置）。"""


class RetryableError(ChameleonError):
    """可重试错误（网络抖动、5xx、代理连接失败）。"""

    suggested_action = "retry"


class BlockedError(ChameleonError):
    """被反爬拦截（403/429），换策略/代理重试。"""

    status = ScrapeStatus.RATE_LIMITED
    suggested_action = "switch_proxy_or_escalate"

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        status: ScrapeStatus | None = None,
        suggested_action: str | None = None,
    ) -> None:
        super().__init__(message, status=status, suggested_action=suggested_action)
        self.status_code = status_code


class ContentInvalidError(ChameleonError):
    """HTTP 200 但内容为反爬/空壳/假内容。"""

    status = ScrapeStatus.RATE_LIMITED
    suggested_action = "escalate_strategy"


class CaptchaRequiredError(ChameleonError):
    """触发验证码，需要打码或人工干预。"""

    status = ScrapeStatus.CAPTCHA_REQUIRED
    suggested_action = "solve_captcha_or_retry_later"


class NotReachableError(ChameleonError):
    """目标不可达（DNS 失败、连接拒绝、超时、全部策略耗尽）。"""

    suggested_action = "check_url_or_delay_retry"


class ProxyUnavailableError(ChameleonError):
    """代理池无可用代理。"""

    suggested_action = "add_proxies_or_use_direct"


class ExtractionValidationError(ChameleonError):
    """提取结果未通过 schema 校验。"""

    suggested_action = "adjust_schema_or_retry"
