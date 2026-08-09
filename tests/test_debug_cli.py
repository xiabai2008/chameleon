"""临时调试（用完删除）。"""
import asyncio
import json
import os
import threading
import time
import urllib.request

import uvicorn
from typer.testing import CliRunner

os.environ["CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION"] = "false"

from chameleon.interfaces.cli import app  # noqa: E402
from tests.fixtures.site import create_test_app  # noqa: E402

config = uvicorn.Config(create_test_app(), host="127.0.0.1", port=8767, log_level="error")
server = uvicorn.Server(config)
t = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
t.start()
for _ in range(100):
    try:
        urllib.request.urlopen("http://127.0.0.1:8767/short", timeout=0.3)
        break
    except Exception:
        time.sleep(0.05)

result = CliRunner().invoke(app, ["scrape", "http://127.0.0.1:8767/static", "--json"])
out = result.output
bad = [(i, hex(ord(ch))) for i, ch in enumerate(out) if ord(ch) < 0x20 and ch not in "\n\t"]
print("CTRL:", bad[:8])
try:
    json.loads(out)
    print("JSON OK")
except Exception as e:
    print("FAIL:", e)
