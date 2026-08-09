# REST API 参考

基础地址：`http://localhost:8000`。认证：`X-API-Key` 头（未配置 `CHAMELEON_SECURITY__API_KEY` 时开放）。

## 端点

### POST /api/v1/scrape
单页采集（同步）。

```json
{
  "url": "https://example.com/product/1",
  "mode": "auto",
  "output_format": "markdown",
  "schema": null,
  "extract_prompt": null,
  "wait_for": null,
  "proxy_region": null,
  "timeout": 30,
  "retry": 3,
  "max_output_tokens": 8000
}
```

响应：方案 6.4 统一 ScrapeResult 结构（status/content/metadata/links/images）。

### POST /api/v1/crawl
整站爬取（异步）→ `{"job_id": "...", "status": "queued"}`。

### POST /api/v1/map
URL 发现 → `{"url", "links", "sitemap"}`。

### POST /api/v1/extract
Schema 提取 → `{"status", "extracted", "error"}`。

### POST /api/v1/search
搜索 → `{"query", "results": [{title, url, snippet}]}`。

### POST /api/v1/batch
批量采集 → `{"count", "results"}`。

### POST /api/v1/screenshot
截图 → `{"url", "screenshot_base64"}`。

### GET /api/v1/jobs/{job_id}
任务状态 → CrawlJob。

### DELETE /api/v1/jobs/{job_id}
取消任务。

### WS /api/v1/jobs/{job_id}/ws
实时进度推送：`{"job_id", "status", "pages"}`。

### GET /health
健康检查。

## 错误码

| 状态码 | 含义 |
|--------|------|
| 400 | 参数错误 |
| 401 | API Key 无效 |
| 429 | 速率限制 |
| 500 | 服务端错误 |

OpenAPI 文档：`http://localhost:8000/docs`。
