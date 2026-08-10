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

## CSS 提取器 Schema DSL

Chameleon 使用 Crawl4AI 兼容的 `JsonCssExtractionStrategy` 格式。
`extract_data` 和 `scrape_url`（带 `schema` 参数）都支持在 JSON Schema 中
嵌入 `"css"` / `"xpath"` 指令来定位 DOM 节点。

> ⚠️ 纯 JSON Schema（只有 `"type": "string"` 等类型声明）**不会自动提取**。
> 每个字段必须包含 `"css"` 或 `"xpath"` 指令。

### 基础字段提取

`"css"` 指定 CSS 选择器，`"attr"` 指定要取的属性（默认取 inner text）。

```json
{
  "type": "object",
  "properties": {
    "page_title": {"type": "string", "css": "h1"},
    "first_link": {"type": "string", "css": "a", "attr": "href"},
    "meta_desc": {"type": "string", "css": "meta[name=description]", "attr": "content"}
  }
}
```

输出：
```json
{"page_title": "Example Domain", "first_link": "https://iana.org/domains/example", "meta_desc": "..."}
```

### 嵌套对象

在 `properties` 中继续声明子字段，选择器相对于父节点执行。

```json
{
  "type": "object",
  "properties": {
    "author": {
      "type": "object",
      "css": ".author-box",
      "properties": {
        "name": {"type": "string", "css": ".name"},
        "bio": {"type": "string", "css": ".bio"}
      }
    }
  }
}
```

### 数组提取

用 `"type": "array"` + `"items"` 提取列表。`"css"` 定位容器，
`"items"` 中再声明每个元素的 `"css"` 选择器和 `"properties"`。

```json
{
  "type": "object",
  "properties": {
    "products": {
      "type": "array",
      "css": "ol.row",
      "items": {
        "type": "object",
        "css": "article.product_pod",
        "properties": {
          "title": {"type": "string", "css": "h3 a", "attr": "title"},
          "price": {"type": "string", "css": "p.price_color"},
          "rating": {"type": "string", "css": "p.star-rating", "attr": "class"}
        }
      }
    }
  }
}
```

输出（books.toscrape.com 实测）：
```json
{"products": [
  {"title": "A Light in the Attic", "price": "£51.77", "rating": "star-rating Three"},
  {"title": "Tipping the Velvet", "price": "£53.74", "rating": "star-rating One"},
  ...
]}
```

### Agent 调用示例

Agent 通过 MCP 调用时可以直接传入 schema 对象（无需文件）：

```python
# scrape_url 带结构化提取
result = await session.call_tool("scrape_url", {
    "url": "https://books.toscrape.com",
    "output_format": "json",
    "schema": {
        "type": "object",
        "properties": {
            "first_book": {"type": "string", "css": "article.product_pod h3 a", "attr": "title"}
        }
    }
})

# extract_data 专用结构化提取
result = await session.call_tool("extract_data", {
    "url": "https://news.ycombinator.com",
    "schema": {
        "type": "object",
        "properties": {
            "top_stories": {
                "type": "array",
                "css": "tr.athing",
                "items": {
                    "type": "object",
                    "css": "tr.athing",
                    "properties": {
                        "title": {"type": "string", "css": ".titleline a"},
                        "url": {"type": "string", "css": ".titleline a", "attr": "href"}
                    }
                }
            }
        }
    },
    "strategy": "css"
})
```
