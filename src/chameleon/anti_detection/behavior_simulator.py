"""行为模拟：请求间隔正态分布、人类滚动、鼠标轨迹（方案 5.2 BehaviorSimulator）。"""

from __future__ import annotations

import asyncio
import random

from chameleon.core.config import BehaviorConfig

DEFAULT_INTERVAL_MEAN = 5.0
DEFAULT_INTERVAL_SIGMA = 1.5


class BehaviorSimulator:
    """模拟人类行为特征：请求间隔、滚动节奏、鼠标轨迹。"""

    def __init__(self, config: BehaviorConfig | None = None) -> None:
        cfg = config or BehaviorConfig()
        self.min_interval = cfg.min_interval
        self.max_interval = cfg.max_interval
        self.scroll_steps = cfg.scroll_steps
        self.scroll_delay = cfg.scroll_delay

    def next_interval(self) -> float:
        """下一次请求间隔（秒）：正态分布截断到 [min, max]。"""
        mean = (self.min_interval + self.max_interval) / 2
        sigma = (self.max_interval - self.min_interval) / 6
        value = random.gauss(mean, sigma)
        return max(self.min_interval, min(self.max_interval, round(value, 2)))

    async def human_scroll(self, page: object, *, steps: int | None = None, delay: float | None = None) -> None:
        """增量滚动模拟：每步随机步长 + 随机暂停，模拟阅读节奏。"""
        from playwright.async_api import Page

        p: Page = page  # type: ignore[assignment]
        steps = steps or self.scroll_steps
        delay = delay or self.scroll_delay
        for _ in range(steps):
            step = random.randint(300, 700)
            await p.evaluate(f"window.scrollBy(0, {step})")
            await asyncio.sleep(delay * random.uniform(0.6, 1.4))
            visible = await p.evaluate("window.scrollY + window.innerHeight >= document.body.scrollHeight")
            if visible:
                break

    @staticmethod
    async def human_mouse_trail(page: object) -> None:
        """鼠标轨迹：折线移动 + 随机停留。"""
        from playwright.async_api import Page

        p: Page = page  # type: ignore[assignment]
        x, y = random.randint(300, 600), random.randint(200, 500)
        await p.mouse.move(x, y)
        for _ in range(random.randint(3, 6)):
            x += random.randint(-120, 120)
            y += random.randint(-80, 80)
            await p.mouse.move(x, y, steps=random.randint(5, 12))
            await asyncio.sleep(random.uniform(0.05, 0.25))
