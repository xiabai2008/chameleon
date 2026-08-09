# Chameleon 🦎

A production-grade web scraping tool for AI agents, built for the real world: anti-bot detection, dynamic rendering, and fault tolerance. Ships with **MCP Server + REST API + CLI** agent-friendly interfaces. Core philosophy: **layered evasion, adaptive degradation, agent-friendly output**.

## Highlights

- **6-level anti-bot escalation chain**: bare request → UA/header faking → proxy rotation → TLS fingerprint impersonation → headless browser → behavioral simulation/captcha, fully observable at every step
- **Three engines**: HTTP (httpx/curl_cffi), Browser (Playwright + stealth + behavior simulation), API reverse-engineering
- **Processing pipeline**: HTML cleaning → Markdown (token-budgeted) → structured extraction (CSS/XPath/LLM/Hybrid/table) → dynamic Pydantic validation
- **Deep crawling**: BFS/DFS/adaptive strategies, per-domain rate limiting, ETag incremental fetching, checkpoint resume, robots.txt compliance
- **Agent-native**: 12 MCP tools with auto-discovery, unified output contract (`status/content/metadata`), SSRF protection + audit logs
- **Extensible**: third-party fallback providers (Firecrawl, Bright Data Web Unlocker) and self-trained captcha recognition (OpenCV template matching)

## Interfaces

| Interface | Description |
|-----------|-------------|
| MCP Server | stdio transport, 12 tools, SSRF guard + output truncation |
| REST API | FastAPI, 1:1 with MCP tools, API-key auth + WebSocket progress |
| CLI | `chameleon scrape/crawl/extract/map/search ...`, semantic exit codes |
| Python SDK | `Chameleon` facade covering scrape/crawl/extract/batch/search |

## Quick Start

```bash
uv sync
uv run chameleon scrape https://example.com -o markdown          # CLI
uv run python -m chameleon.interfaces.mcp_server                 # MCP (stdio)
uv run uvicorn chameleon.interfaces.rest_api:app --port 8000     # REST API
```

### MCP configuration (Claude Code / opencode)

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

## Architecture

```
Agent → MCP/REST/CLI → Chameleon facade
  ├─ SmartRouter (L0-L6 escalation + strategy memory)
  ├─ Pipeline (clean → markdown → extract → validate)
  └─ DeepCrawler + Scheduler (strategy traversal / rate limit / resume)
```

See [docs/architecture.md](docs/architecture.md).

## Scope & Limitations

**Anti-bot evasion is an ongoing arms race.** This tool does not guarantee success against every site:

- Continuously-maintained anti-bot systems (sliding captchas, device fingerprinting, risk scoring) may defeat any level of automation
- The built-in escalation chain is transparent and observable — results include the engine and escalation level used, so agents can judge trustworthiness
- Residential proxies and captcha-solving services are third-party paid dependencies; budget accordingly
- Use this tool only where you are authorized: respect `robots.txt`, site ToS, local laws (GDPR / PIPL), and rate limits. Misuse can cause harm and is solely the user's responsibility

## Tests

```bash
uv run pytest          # 229 tests (incl. real Playwright rendering, anti-bot simulator)
uv run ruff check src tests
uv run mypy src
```

## Docs

- [docs/开发方案.md](docs/开发方案.md) — design, architecture, interface spec, competitor comparison (Chinese)
- [docs/完整开发路线图.md](docs/完整开发路线图.md) — full P0-P8 roadmap with acceptance criteria (Chinese)
- [docs/architecture.md](docs/architecture.md) / [docs/mcp_tools.md](docs/mcp_tools.md) / [docs/api_reference.md](docs/api_reference.md)

## License

[MIT](LICENSE)
