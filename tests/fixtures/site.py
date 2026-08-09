"""本地测试站点：覆盖静态页/SPA/反爬/短内容/重定向场景。"""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

STATIC_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>静态测试页</title></head>
<body>
<h1>静态页面标题</h1>
<p>这是一段用于内容校验的静态页面正文，长度必须超过 500 字符阈值。
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute
irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla
pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia
deserunt mollit anim id est laborum. 中文内容也需要足够长以便通过最小长度校验，
这一段继续补充文字。搜索爬虫、数据采集、信息抽取是常见应用场景。</p>
<a href="/static2">链接一</a>
<a href="/blocked">链接二</a>
</body>
</html>
"""

SPA_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>SPA 测试页</title></head>
<body>
<div id="app"><p>loading...</p></div>
<script>
  window.__SPA_CONTENT__ = [
    "SPA 动态渲染内容第一段，由 JavaScript 注入到页面中。",
    "SPA 动态渲染内容第二段，这段文字在初始 HTML 中并不存在，",
    "必须由浏览器执行脚本后才会出现，用于验证浏览器引擎能力。"
  ];
  setTimeout(function() {
    var app = document.getElementById('app');
    var html = '<h1>SPA 动态标题</h1>';
    html += window.__SPA_CONTENT__.map(function(t) { return '<p>' + t + '</p>'; }).join('');
    html += '<ul><li>产品A 100元</li><li>产品B 200元</li></ul>';
    app.innerHTML = html;
  }, 200);
</script>
</body>
</html>
"""

SHORT_PAGE = "<html><body><p>too short</p></body></html>"

CAPTCHA_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>验证</title></head>
<body><h1>请完成验证</h1><p>请输入验证码以继续访问。</p></body></html>
"""

LONG_PAGE_BODY = "\n".join(f"<p>段落{idx}: 用于测试长页面内容的填充文字，重复扩充长度以便验证清理与转换逻辑。</p>" for idx in range(30))


PRODUCTS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>产品列表</title></head>
<body>
<h1>全部产品</h1>
<ul class="products">
  <li class="product">
    <h2 class="name">智能手表 Pro</h2>
    <span class="price">¥1299</span>
    <a class="buy" href="/product/1">购买</a>
  </li>
  <li class="product">
    <h2 class="name">无线耳机 Max</h2>
    <span class="price">¥899</span>
    <a class="buy" href="/product/2">购买</a>
  </li>
  <li class="product">
    <h2 class="name">便携充电宝 20000mAh</h2>
    <span class="price">¥199</span>
    <a class="buy" href="/product/3">购买</a>
  </li>
  <li class="product">
    <h2 class="name">机械键盘 K87</h2>
    <span class="price">¥459</span>
    <a class="buy" href="/product/4">购买</a>
  </li>
  <li class="product">
    <h2 class="name">显示器 27寸 4K</h2>
    <span class="price">¥2499</span>
    <a class="buy" href="/product/5">购买</a>
  </li>
</ul>
<script>var track = "should be removed";</script>
</body></html>
"""


SHADOW_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Shadow DOM 测试</title></head>
<body>
<h1>Shadow 页面</h1>
<my-widget></my-widget>
<script>
class MyWidget extends HTMLElement {
  connectedCallback() {
    const shadow = this.attachShadow({mode: 'open'});
    shadow.innerHTML = '<h2>Shadow 内部标题</h2><p>Shadow 内部文本内容，普通 DOM 无法直接读取。</p>';
  }
}
customElements.define('my-widget', MyWidget);
</script>
</body></html>
"""

INFINITE_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>无限滚动测试</title>
<style>li { padding: 160px 0; border-bottom: 1px solid #eee; }</style>
</head>
<body>
<h1>无限滚动列表</h1>
<ul id="list"></ul>
<script>
let count = 0;
function addItems(n) {
  const list = document.getElementById('list');
  for (let i = 0; i < n; i++) {
    const li = document.createElement('li');
    li.textContent = '滚动加载项 ' + (++count) + ' - 内容填充保证足够长度以便校验';
    list.appendChild(li);
  }
}
addItems(5);
window.addEventListener('scroll', () => {
  if (window.scrollY + window.innerHeight >= document.body.scrollHeight - 50) {
    addItems(5);
  }
});
</script>
</body></html>
"""

CAPTCHA_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>安全验证</title></head>
<body>
<h1>请完成滑块验证</h1>
<p>拖动滑块完成验证后继续访问。</p>
<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" alt="captcha">
<div class="slider-container"><div class="slider"></div></div>
</body></html>
"""


SITE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>站点页面 {page}</title></head>
<body>
<h1>站点页面 {page}</h1>
<p>这是测试站点第 {page} 页的内容。Lorem ipsum dolor sit amet, consectetur
adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna
aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris
nisi ut aliquip ex ea commodo consequat. 页面正文填充足够长以便通过校验。</p>
<nav class="links">
{links}
</nav>
</body></html>
"""

SITE_PAGES = "abcdefghij"


def _site_links(page: str) -> str:
    idx = SITE_PAGES.index(page)
    prev_page = SITE_PAGES[(idx - 1) % len(SITE_PAGES)]
    next_page = SITE_PAGES[(idx + 1) % len(SITE_PAGES)]
    links = [f'<a href="/site/{p}">页面{p}</a>' for p in (prev_page, next_page)]
    links.append('<a href="https://external.example.com/foreign">外链</a>')
    links.append('<a href="/asset.jpg">图片</a>')
    links.append('<a href="#section">锚点</a>')
    return "\n".join(links)


def create_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(STATIC_PAGE)

    @app.get("/static")
    async def static_page() -> HTMLResponse:
        return HTMLResponse(STATIC_PAGE)

    @app.get("/static2")
    async def static_page2() -> HTMLResponse:
        return HTMLResponse(STATIC_PAGE.replace("静态测试页", "静态测试页二"))

    @app.get("/spa")
    async def spa_page() -> HTMLResponse:
        return HTMLResponse(SPA_PAGE)

    @app.get("/short")
    async def short_page() -> HTMLResponse:
        return HTMLResponse(SHORT_PAGE)

    @app.get("/blocked")
    async def blocked() -> Response:
        return Response(content="<html><body>denied</body></html>", status_code=403)

    @app.get("/rate-limited")
    async def rate_limited() -> Response:
        return Response(content="Too Many Requests", status_code=429)

    @app.get("/captcha")
    async def captcha() -> HTMLResponse:
        return HTMLResponse(CAPTCHA_PAGE)

    @app.get("/redirect")
    async def redirect() -> RedirectResponse:
        return RedirectResponse("/static", status_code=302)

    @app.get("/long")
    async def long_page() -> HTMLResponse:
        return HTMLResponse(f"<html><head><title>长页面</title></head><body>{LONG_PAGE_BODY}</body></html>")

    @app.get("/products")
    async def products() -> HTMLResponse:
        return HTMLResponse(PRODUCTS_HTML)

    @app.get("/shadow")
    async def shadow() -> HTMLResponse:
        return HTMLResponse(SHADOW_PAGE)

    @app.get("/infinite")
    async def infinite() -> HTMLResponse:
        return HTMLResponse(INFINITE_PAGE)

    @app.get("/captcha-page")
    async def captcha_page() -> HTMLResponse:
        return HTMLResponse(CAPTCHA_PAGE)

    @app.get("/site/{page}")
    async def site_page(page: str) -> Response:
        if page not in SITE_PAGES:
            return Response(content="<html><body>404</body></html>", status_code=404)
        return HTMLResponse(SITE_PAGE_TEMPLATE.format(page=page, links=_site_links(page)))

    @app.get("/robots.txt")
    async def robots() -> PlainTextResponse:
        return PlainTextResponse("User-agent: *\nDisallow: /site/e\n")

    @app.get("/gzip")
    async def gzip_page() -> Response:
        import gzip as gzip_mod

        body = STATIC_PAGE.encode("utf-8")
        return Response(content=gzip_mod.compress(body), media_type="text/html", headers={"Content-Encoding": "gzip"})

    @app.get("/gbk")
    async def gbk_page() -> PlainTextResponse:
        html = "<html><head><meta charset='gbk'></head><body>中文编码测试页面内容</body></html>"
        return Response(content=html.encode("gbk"), media_type="text/html; charset=gbk")

    @app.get("/json")
    async def json_api() -> dict:
        return {"name": "test", "items": [{"id": 1}, {"id": 2}]}

    return app
