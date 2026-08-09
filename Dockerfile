# Chameleon — 多阶段构建
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 依赖层（利用缓存）
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# 系统依赖 + Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 && rm -rf /var/lib/apt/lists/*
RUN uv run playwright install chromium --with-deps

# 运行层
FROM base AS runtime
ENV PYTHONPATH=/app/src CHAMELEON_CONFIG=/app/config/settings.yaml
EXPOSE 8000
USER root
CMD ["uv", "run", "uvicorn", "chameleon.interfaces.rest_api:app", "--host", "0.0.0.0", "--port", "8000"]
