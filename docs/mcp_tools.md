# MCP 工具参考

MCP Server 通过 stdio 运行：

```json
{
  "mcpServers": {
    "chameleon": {
      "command": "uv",
      "args": ["run", "python", "-m", "chameleon.interfaces.mcp_server"]
    }
  }
}
```

## 工具清单

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `scrape_url` | 采集单页转 Markdown/JSON | url, mode(auto/static/dynamic), output_format, schema, extract_prompt, wait_for, proxy_region |
| `crawl_site` | 整站深度爬取（异步） | url, max_pages, max_depth, strategy(bfs/dfs/adaptive) |
| `map_site` | 发现站点 URL | url, sitemap_only |
| `extract_data` | Schema 结构化提取 | url, schema(JSON Schema), strategy(css/xpath/llm/auto) |
| `search_web` | 必应搜索返回结果 | query, max_results, language |
| `batch_scrape` | 批量采集 | urls, output_format, concurrency |
| `get_screenshot` | 网页截图 base64 | url, full_page |
| `diagnose_site` | 反爬画像诊断 | url |
| `check_proxy` | 代理检测 | proxy_url |
| `get_job_status` | 任务状态查询 | job_id |
| `get_robots_txt` | robots.txt 内容 | url |
| `get_network_log` | 网络请求日志（API 发现） | url, filter_type(xhr/fetch/all) |

## 输出契约

所有工具返回 `{status, data/result, error, suggested_action}` 结构：
- `status`: success | error | captcha_required | rate_limited
- `suggested_action`: 失败时给 Agent 的下一步建议
- 超长 Markdown 自动截断（12k 字符）并标记 `truncated: true`
