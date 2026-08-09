"""结构化日志：request_id 贯穿一次采集生命周期。"""

from __future__ import annotations

import contextvars
import logging
import sys

import structlog

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("chameleon_request_id", default=None)


def configure_logging(*, level: str = "INFO", json_output: bool = False) -> None:
    """全局配置 structlog。json_output=True 时输出 JSON（生产），否则彩色控制台。"""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer(ensure_ascii=False))
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(int(getattr(logging, level.upper(), 20))),
        cache_logger_on_first_use=True,
    )


def bind_request_id(request_id: str | None) -> None:
    """为当前上下文绑定 request_id。"""
    if request_id:
        structlog.contextvars.bind_contextvars(request_id=request_id)
        _request_id.set(request_id)


def get_request_id() -> str | None:
    return _request_id.get()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name or "chameleon")
    return logger
