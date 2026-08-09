# ADR-0001: 技术栈与关键依赖选型

状态：已接受（2026-08）
关联：《开发方案》第三节

## 背景

需要确定整个项目的基础技术栈。核心约束：asyncio 原生、Agent 接口优先、中文站点优化。

## 决策

| 领域 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 生态最成熟，方案既定 |
| HTTP | httpx (async) | HTTP/2、async 原生 |
| TLS 伪装 | curl_cffi（P4 引入） | impersonate 浏览器指纹 |
| 浏览器 | Playwright | 跨浏览器、CDP 能力强 |
| 反检测注入 | 自研 CDP init script（兜底），playwright-stealth 仅作对照 | stealth 库 2023 年后停滞，长期维护风险高 |
| 配置 | pydantic-settings + YAML | env 覆盖链清晰 |
| 日志 | structlog | 结构化 + request_id 贯穿 |
| 任务队列 | arq 或 Redis + asyncio（P5 再定，倾向 arq） | 排除 Celery：与 asyncio 线程模型冲突 |
| 提取 | selectolax + lxml + LLM(Hybrid) | 快 + 容错 + 语义 |

## 后果

- 全链路 asyncio，避免线程池回退
- 反检测脚本自维护，更新成本可控但需持续维护
