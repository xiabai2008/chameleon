"""反爬模拟站：验证 UA/Header 检测、代理轮换、蜜罐链接、Cookie 追踪。"""

from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse

PROTECTED_PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>受保护页面</title></head>
<body>
<h1>受保护内容</h1>
<p>只有携带正确请求头与 Cookie 的请求才能看到这段内容。
这里是足够长的正文用于通过内容校验器的最小长度检查，包含多个
完整句子以模拟真实页面的信息密度。Lorem ipsum dolor sit amet,
consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut
labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum
dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non
proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
中文段落继续补充文字以突破长度阈值，确保内容校验器认为页面真实有效。</p>
<a href="/public-visible" style="display:block">可见链接</a>
<a href="/honeypot-1" style="display:none">蜜罐链接1</a>
<a href="/honeypot-2" aria-hidden="true">蜜罐链接2</a>
<a href="/normal-link">正常链接</a>
</body></html>
"""

HONEYPOT_TARGET = "<html><body><h1>这是蜜罐页面</h1></body></html>"


class AntiBotSimulator:
    """记录并判定每次请求的身份质量。"""

    def __init__(self) -> None:
        self.ua_seen: dict[str, int] = defaultdict(int)
        self.header_incomplete: int = 0
        self.requests_without_cookie: int = 0
        self.honeypot_visits: int = 0
        self.blocked_bare: int = 0
        self.cookie_set = False

    def snapshot(self) -> dict[str, int]:
        return {
            "ua_seen": len(self.ua_seen),
            "header_incomplete": self.header_incomplete,
            "requests_without_cookie": self.requests_without_cookie,
            "honeypot_visits": self.honeypot_visits,
            "blocked_bare": self.blocked_bare,
        }


simulator = AntiBotSimulator()


def create_anti_bot_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(request: Request) -> Response:
        ua = request.headers.get("user-agent", "")
        accept_language = request.headers.get("accept-language", "")
        sec_fetch = request.headers.get("sec-fetch-dest", "")
        cookie = request.headers.get("cookie", "")

        if "python-httpx" in ua or ua == "":
            simulator.blocked_bare += 1
            return Response(content="<html><body>403 Forbidden</body></html>", status_code=403)
        if not accept_language or not sec_fetch:
            simulator.header_incomplete += 1
            return Response(content="<html><body>403 Forbidden</body></html>", status_code=403)
        if not cookie and not simulator.cookie_set:
            simulator.requests_without_cookie += 1
            response = Response(content=PROTECTED_PAGE, status_code=200)
            response.set_cookie("chameleon_tracker", "ok", max_age=3600)
            simulator.cookie_set = True
            return response
        return Response(content=PROTECTED_PAGE, status_code=200)

    @app.get("/public-visible")
    async def visible() -> HTMLResponse:
        return HTMLResponse("<html><body><h1>可见页面</h1></body></html>")

    @app.get("/honeypot-1")
    @app.get("/honeypot-2")
    async def honeypot() -> HTMLResponse:
        simulator.honeypot_visits += 1
        return HTMLResponse(HONEYPOT_TARGET)

    @app.get("/normal-link")
    async def normal() -> HTMLResponse:
        return HTMLResponse("<html><body><h1>正常页面</h1></body></html>")

    @app.get("/stats")
    async def stats() -> dict[str, int]:
        return simulator.snapshot()

    @app.get("/echo")
    async def echo(request: Request) -> dict[str, str]:
        return {
            "ua": request.headers.get("user-agent", ""),
            "accept_language": request.headers.get("accept-language", ""),
            "sec_fetch": request.headers.get("sec-fetch-dest", ""),
            "cookie": request.headers.get("cookie", ""),
            "host": request.headers.get("host", ""),
        }

    @app.get("/reset")
    async def reset() -> dict[str, bool]:
        simulator.__init__()
        return {"ok": True}

    return app
