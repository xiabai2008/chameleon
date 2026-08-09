# Chameleon 架构文档

## 分层架构

```
Agent / 用户
  │  MCP (stdio/HTTP) │ REST API │ CLI │ Python SDK
  ▼
Chameleon 服务门面（interfaces/sdk.py）
  │
  ├─ SmartRouter（升级链 L0-L6）
  │    ├─ L0-L1: HttpEngine (httpx, UA/Header 伪装)
  │    ├─ L2:    + ProxyManager（加权代理池）
  │    ├─ L3:    TlsHttpEngine (curl_cffi JA3/JA4 指纹)
  │    ├─ L4-L5: BrowserEngine (Playwright + stealth + 行为模拟)
  │    └─ L6:    CaptchaRouter（ddddocr/第三方）
  │
  ├─ Pipeline（清洗 → Markdown → Fit 裁剪 → 提取 → 校验）
  │    ├─ Cleaner (readability)
  │    ├─ Converter (markdownify) + FitMarkdown（token 预算）
  │    ├─ Css/XPath/LLM/Hybrid 提取器
  │    └─ ExtractionValidator（动态 Pydantic 模型）
  │
  └─ DeepCrawler + Scheduler（BFS/DFS/Adaptive、限速、断点、robots）
```

## 核心设计决策（ADR 摘要）

| 决策 | 选择 | 原因 |
|------|------|------|
| 反检测注入 | 自研 CDP init script | playwright-stealth 停滞 |
| 任务队列 | asyncio + JobStore（内存/Redis） | 排除 Celery 线程模型冲突 |
| LLM 集成 | OpenAI 兼容 httpx 直连 | 避免 litellm 重依赖，BYO-LLM |
| 提取校验 | JSON Schema → 动态 Pydantic | TypeAdapter 不支持标准 JSON Schema |

## 数据流

```
HTTP 响应 → decode_html → ContentValidator（状态码/长度/反爬词/JS 壳）
  → SmartRouter 升级链 → FetchResult
  → Pipeline.process → ScrapeResult（方案 6.4 统一结构）
```

## 可观测性

- structlog 结构化日志（request_id 贯穿）
- Prometheus 指标：请求计数/耗时/升级层级/代理健康/缓存命中
- metadata 记录 engine/retries/escalation_level，供 Agent 判断可信度
