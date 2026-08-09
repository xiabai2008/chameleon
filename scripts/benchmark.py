"""基准测试：单节点吞吐（P7-8）。"""

from __future__ import annotations

import asyncio
import time
from statistics import mean, median


async def benchmark(url: str, n: int = 20, concurrency: int = 5) -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    # 预热
    await service.scrape(url)
    latencies: list[float] = []
    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()

    async def one() -> None:
        async with semaphore:
            t0 = time.perf_counter()
            result = await service.scrape(url, mode="static")
            latencies.append(time.perf_counter() - t0)
            assert result.status.value == "success", result.error

    await asyncio.gather(*[one() for _ in range(n)])
    total = time.perf_counter() - started
    print(f"URL: {url}")
    print(f"请求数: {n}  并发: {concurrency}")
    print(f"总耗时: {total:.2f}s  吞吐: {n / total:.1f} req/s")
    print(f"延迟: p50={median(latencies) * 1000:.0f}ms  avg={mean(latencies) * 1000:.0f}ms")
    await service.close()


if __name__ == "__main__":
    import sys

    asyncio.run(benchmark(sys.argv[1] if len(sys.argv) > 1 else "https://example.com"))
