# Chameleon 🦎

面向真实世界反爬、动态渲染、异常容错的 AI Agent 爬虫工具。提供 **MCP Server + REST API + CLI** 三套 Agent 友好接口，核心理念：**分层对抗、自适应降级、Agent 友好输出**。

## 核心能力

- **6 级反爬自动升级**：裸请求 → UA/Header 伪装 → 代理轮换 → TLS 指纹模拟 → 浏览器渲染 → 行为模拟/验证码，逐级升级，全程可观测
- **三引擎架构**：HTTP 引擎（httpx/curl_cffi）、浏览器引擎（Playwright + stealth + 行为模拟）、API 逆向引擎
- **处理管线**：HTML 清洗 → Markdown 转换（token 预算裁剪）→ 结构化提取（CSS/XPath/LLM/Hybrid/表格）→ 动态 Pydantic 校验
- **深度爬取**：BFS/DFS/Adaptive 策略、每域名限速、ETag 增量采集、断点续爬、robots.txt 合规
- **Agent 原生**：MCP 12 工具自动发现、统一结构化输出（status/content/metadata）、SSRF 防护 + 审计日志

## 接口形态

| 形态 | 说明 |
|------|------|
| MCP Server | stdio 传输，12 个工具，SSRF 防护 + 输出截断 |
| REST API | FastAPI，与 MCP 工具一一对应，API Key 认证 + WebSocket 进度 |
| CLI | `chameleon scrape/crawl/extract/map/search ...`，退出码语义化 |
| Python SDK | `Chameleon` 服务门面，scrape/crawl/extract/batch/search 全覆盖 |

## 快速开始

```bash
uv sync
uv run chameleon scrape https://example.com -o markdown          # CLI
uv run python -m chameleon.interfaces.mcp_server                 # MCP (stdio)
uv run uvicorn chameleon.interfaces.rest_api:app --port 8000     # REST API
```

### MCP 配置（Claude Code / opencode）

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

Agent 自动发现工具后可直接说："抓取 https://example.com/products 的所有产品名称和价格，输出 JSON"。

## 架构一览

```
Agent → MCP/REST/CLI → Chameleon 门面
  ├─ SmartRouter（L0-L6 升级链 + 策略记忆）
  ├─ Pipeline（清洗 → Markdown → 提取 → 校验）
  └─ DeepCrawler + Scheduler（策略遍历/限速/断点）
```

详见 [docs/architecture.md](docs/architecture.md)。

## 测试

```bash
uv run pytest          # 229 个测试（含 Playwright 真实渲染、反爬模拟站对抗）
uv run ruff check src tests
uv run mypy src
```

## 边界与声明

**反爬对抗是持续的军备竞赛**，本工具不保证对任何站点必然成功：

- 持续演进的验证码（滑块/设备指纹/风控评分）可能击败任何自动化手段
- 内置升级链全程透明可观测——结果中记录实际使用的引擎与升级层级，Agent 可据此判断可信度
- 住宅代理与打码服务为第三方付费依赖，请按预算使用
- 仅在获得授权的范围内使用：遵守 robots.txt、站点服务条款、当地法律（GDPR/个保法）与限速要求。滥用造成的后果由使用者自行承担

## 文档

- [开发方案](docs/开发方案.md) — 项目定位、架构、接口设计、竞品对比
- [完整开发路线图](docs/完整开发路线图.md) — P0-P8 全部任务分解与验收标准
- [架构文档](docs/architecture.md) / [MCP 工具](docs/mcp_tools.md) / [REST API](docs/api_reference.md)
- English: [README.en.md](README.en.md)

## 开源

[MIT](LICENSE)
