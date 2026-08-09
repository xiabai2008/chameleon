# Chameleon 🦎

面向真实世界反爬、动态渲染、异常容错的 AI Agent 爬虫工具。提供 **MCP Server + REST API + CLI** 三套 Agent 友好接口，核心理念：**分层对抗、自适应降级、Agent 友好输出**。

## 核心能力

- **6 级反爬自动升级**：裸请求 → UA/Header 伪装 → 代理轮换 → TLS 指纹模拟 → 浏览器渲染 → 行为模拟/验证码，逐级升级，全程可观测
- **三引擎架构**：HTTP 引擎（httpx/curl_cffi）、浏览器引擎（Playwright + stealth）、API 逆向引擎
- **处理管线**：HTML 清洗 → Markdown 转换（token 预算裁剪）→ 结构化提取（CSS/XPath/LLM/Hybrid）→ Pydantic 校验
- **深度爬取**：BFS/DFS/Adaptive 策略、每域名限速、断点续爬、robots.txt 合规
- **Agent 原生**：MCP 12 工具自动发现、统一结构化输出（status/content/metadata）、SSRF 防护 + 审计日志

## 接口形态

| 形态 | 说明 |
|------|------|
| MCP Server | stdio / Streamable HTTP 双传输，12 个工具 |
| REST API | FastAPI，与 MCP 工具一一对应，异步任务 + WebSocket 进度 |
| CLI | `chameleon scrape/crawl/extract/map/search ...`，退出码语义化 |
| Python SDK | `ChameleonClient` 同步/异步门面 |

## 快速开始

```bash
uv sync
uv run chameleon scrape https://example.com -o markdown
```

## 文档

- [开发方案](docs/开发方案.md) — 项目定位、架构、接口设计、竞品对比
- [完整开发路线图](docs/完整开发路线图.md) — P0-P8 全部任务分解与验收标准

## 开源

核心引擎 MIT 协议，后续开源。
