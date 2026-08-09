"""引擎基类：所有引擎（HTTP/Browser/API）实现同一 fetch 协议。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from chameleon.core.models import EngineType, FetchRequest, FetchResult


class BaseEngine(ABC):
    """采集引擎抽象基类。

    职责：根据请求参数执行一次网络采集，返回统一的 FetchResult。
    不负责策略决策（由 Router 负责）与内容校验（由 ContentValidator 负责）。
    """

    name: EngineType = EngineType.HTTP

    @abstractmethod
    async def fetch(self, request: FetchRequest) -> FetchResult:
        """执行一次采集。异常约定：

        - RetryableError: 网络抖动/5xx，可重试
        - BlockedError: 被反爬拦截（403/429）
        - NotReachableError: 目标不可达（DNS/连接失败/超时）
        """

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
