# Contributing to Chameleon

Thanks for your interest in improving Chameleon! This guide covers the workflow.

## Development Setup

```bash
git clone https://github.com/xiabai2008/chameleon.git
cd chameleon
uv sync
uv run playwright install chromium   # browser engine tests
```

## Quality Gates

Every PR must pass:

```bash
uv run ruff check src tests          # lint
uv run mypy src                      # strict type check
uv run pytest -q -m "not browser"    # fast tests (CI)
uv run pytest                        # full suite incl. browser (local)
```

## Architecture Overview

| Module | Responsibility |
|--------|----------------|
| `core/` | Router (L0-L6 escalation), config, models, exceptions |
| `engines/` | HTTP / TLS / Browser / API engines (uniform `fetch` protocol) |
| `anti_detection/` | Identity, proxy pool, stealth, behavior, captcha, strategy memory |
| `pipeline/` | Cleaner, converter, extractors (CSS/XPath/LLM/Hybrid/Table), validator |
| `crawler/` | URL discovery/filter, robots, rate limiter, deep crawler, scheduler |
| `interfaces/` | SDK facade, MCP server, REST API, CLI, providers, security |

**Key principle**: interfaces are thin shells over the `Chameleon` facade — never duplicate logic across MCP/REST/CLI.

## Testing Conventions

- The **anti-bot simulator sites** in `tests/fixtures/` are core test assets — extend them when adding anti-detection features
- Integration tests use the local test server fixtures (`test_server`, `anti_bot_server`, `cli_server`)
- Keep tests deterministic: no real external network in unit tests (use `respx` for HTTP mocks)
- Browser tests are marked `@pytest.mark.browser`

## Pull Request Process

1. Fork, branch from `main` (`feat/xxx` or `fix/xxx`)
2. Add tests for new behavior (this project is strict about this)
3. Update relevant docs (`docs/`, README) if behavior changes
4. Ensure all quality gates pass
5. Open a PR with a clear description of the problem and approach

## Adding a New Anti-Detection Countermeasure

1. Implement in the appropriate `anti_detection/` module
2. Wire it into the escalation chain in `core/router.py` (new level or engine option)
3. Extend the anti-bot simulator fixture to trigger it
4. Add tests asserting the escalation path
5. Document the new level/option in `docs/architecture.md`

## Ethics

Chameleon is a dual-use tool. Contributions that improve legitimate crawling (rendering, extraction, reliability) are welcome. Do not submit features whose primary purpose is abusive access, credential stuffing, or privacy violation. See the README "Scope & Ethics" section.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
