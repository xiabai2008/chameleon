"""野外验证：对真实站点跑通过率（需网络）。"""

from __future__ import annotations

import asyncio
import sys

SITES = [
    "https://example.com",
    "https://www.python.org",
    "https://httpbin.org/html",
    "https://httpbin.org/robots.txt",
]


async def main() -> None:
    from chameleon.interfaces.sdk import Chameleon

    service = Chameleon()
    passed = 0
    for url in SITES:
        try:
            result = await service.scrape(url, timeout_seconds=20)
            ok = result.status.value == "success" and result.content is not None and bool(result.content.markdown)
            print(f"[{'PASS' if ok else 'FAIL'}] {url}  engine={result.metadata.engine.value} "
                  f"level={result.metadata.escalation_level} len={result.metadata.content_length} "
                  f"status={result.metadata.status_code} {result.error or ''}")
            if ok:
                passed += 1
        except Exception as exc:
            print(f"[ERROR] {url}  {type(exc).__name__}: {exc}")
    print(f"\n通过率: {passed}/{len(SITES)}")
    await service.close()
    sys.exit(0 if passed == len(SITES) else 1)


if __name__ == "__main__":
    asyncio.run(main())
