# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

Please **do not** open a public issue for security vulnerabilities.

Report privately via GitHub's [Security Advisories](https://github.com/xiabai2008/chameleon/security/advisories/new) with:

- Affected component and version
- Reproduction steps or proof of concept
- Impact assessment (what an attacker could do)

We aim to acknowledge reports within 72 hours and will coordinate disclosure.

## Security-Relevant Design

Chameleon is a network-facing service. Notable protections already built in:

- **SSRF guard** — blocks requests to private/internal IP ranges (including DNS re-resolution) when the API is exposed (`interfaces/security.py`)
- **API key auth + rate limiting** — for the REST API (`X-API-Key`)
- **No credential storage** — proxy/captcha/provider keys are read from env/config at runtime, never persisted
- **Audit-friendly logging** — structured logs with request IDs

## Hardening Checklist for Deployments

- Always set `CHAMELEON_SECURITY__API_KEY` before exposing the REST API publicly
- Keep `CHAMELEON_SECURITY__ENABLE_SSRF_PROTECTION=true` (default) for shared/multi-tenant deployments
- Run behind a reverse proxy with TLS; consider an IP allowlist for the MCP HTTP transport
- Treat proxy credentials and captcha-provider keys as secrets (env vars / secret manager, not config files in the repo)
