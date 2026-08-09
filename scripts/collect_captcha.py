"""验证码样本收集器：从目标站点批量抓取验证码图片到 sample_dir（P8-8）。

用法: uv run python scripts/collect_captcha.py <页面URL> <图片选择器> <输出目录> [数量]
示例: uv run python scripts/collect_captcha.py https://example.com/login "img.captcha" data/captcha_samples 100

抓取后需人工按字符归档为 sample_dir/{char}/xxx.png 再训练。
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from chameleon.anti_detection.captcha_solver import CaptchaDetector
from chameleon.interfaces.sdk import Chameleon


async def collect(url: str, selector: str, out_dir: str, limit: int = 100) -> int:
    from selectolax.parser import HTMLParser

    service = Chameleon()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = 0
    for i in range(limit):
        try:
            result = await service.scrape(url, mode="dynamic", timeout_seconds=40)
        except Exception as exc:
            print(f"[skip] fetch failed: {exc}")
            continue
        html = (result.content.raw_html if result.content else "") or ""
        tree = HTMLParser(html)
        srcs: list[str] = []
        if selector:
            for node in tree.css(selector):
                src = node.attributes.get("src")
                if src:
                    srcs.append(src)
        else:
            img = CaptchaDetector.extract_image(html)
            if img:
                srcs.append(img)
        if not srcs:
            print(f"[skip] no captcha image on page {i + 1}")
            continue
        import base64
        import urllib.parse

        for j, src in enumerate(srcs[:3]):
            try:
                if src.startswith("data:"):
                    raw = base64.b64decode(src.split(",", 1)[1])
                else:
                    raw = await _download(service, urllib.parse.urljoin(url, src))
                (out / f"captcha_{i}_{j}.png").write_bytes(raw)
                saved += 1
            except Exception as exc:
                print(f"[skip] download failed {src}: {exc}")
    await service.close()
    return saved


async def _download(service: Chameleon, src: str) -> bytes:
    from chameleon.core.models import FetchRequest
    from chameleon.utils.encoding import decode_html

    raw = await service.router.fetch(
        FetchRequest(url=src, headers=service.identity.generate_headers(src)),
        mode="static",
    )
    if raw.status_code != 200:
        raise RuntimeError(f"status {raw.status_code}")
    content = decode_html(raw.content)
    match = re.search(r"base64,([A-Za-z0-9+/=]+)", content)
    if match:
        import base64

        return base64.b64decode(match.group(1))
    raise RuntimeError("not an image response")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    url, selector, out = sys.argv[1], sys.argv[2], sys.argv[3]
    limit = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    saved = asyncio.run(collect(url, selector, out, limit))
    print(f"saved {saved} captcha images to {out}")
