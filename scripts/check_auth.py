"""认证验证：无 key 应 401，带 key 应 200。用法: python check_auth.py <key>"""
import sys

import httpx

BASE = "http://127.0.0.1:8010"
key = sys.argv[1] if len(sys.argv) > 1 else ""

r1 = httpx.post(f"{BASE}/api/v1/scrape", json={"url": "https://example.com"}, timeout=30)
print(f"no-key:   {r1.status_code}  (期望 401)")

r2 = httpx.post(
    f"{BASE}/api/v1/scrape",
    json={"url": "https://example.com"},
    headers={"X-API-Key": key},
    timeout=60,
)
print(f"with-key: {r2.status_code}  (期望 200)")
if r2.status_code == 200:
    d = r2.json()
    print(f"  status={d['status']} engine={d['metadata']['engine']} level={d['metadata']['escalation_level']}")

r3 = httpx.get(f"{BASE}/health", timeout=10)
print(f"health:   {r3.status_code}  (开放端点)")
