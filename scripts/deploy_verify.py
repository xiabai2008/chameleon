"""部署验证：服务器本机验证 REST API + 真实站点爬取。"""

import asyncio
import json

import httpx

BASE = "http://127.0.0.1:8010"


async def check(name: str, coro) -> None:
    try:
        result = await coro
        print(f"[PASS] {name}: {result}")
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")


async def main() -> None:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{BASE}/health")
        await check("health", _done(f"status={r.status_code} {r.json()}"))

        r = await client.post(f"{BASE}/api/v1/scrape", json={"url": "https://www.python.org"})
        d = r.json()
        await check(
            "scrape python.org",
            _done(
                f"status={d['status']} engine={d['metadata']['engine']} "
                f"level={d['metadata']['escalation_level']} len={d['metadata']['content_length']}"
            ),
        )

        r = await client.post(f"{BASE}/api/v1/scrape", json={"url": "https://example.com"})
        d = r.json()
        await check(
            "scrape example.com (升级链)",
            _done(
                f"status={d['status']} engine={d['metadata']['engine']} "
                f"level={d['metadata']['escalation_level']} len={d['metadata']['content_length']}"
            ),
        )

        r = await client.post(f"{BASE}/api/v1/extract", json={
            "url": "https://httpbin.org/html",
            "schema": {"type": "object", "properties": {"h1": {"type": "string", "css": "h1"}}},
        })
        d = r.json()
        await check("extract httpbin h1", _done(f"extracted={d.get('extracted')} err={d.get('error')}"))

        r = await client.post(f"{BASE}/api/v1/map", json={"url": "https://www.python.org"})
        d = r.json()
        await check("map python.org", _done(f"links={len(d.get('links', []))}"))


async def _done(text: str) -> str:
    return text


if __name__ == "__main__":
    asyncio.run(main())
