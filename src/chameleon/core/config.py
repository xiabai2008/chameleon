"""配置系统：默认值 < YAML 文件 < 环境变量（CHAMELEON_ 前缀）< 显式传入。"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class ProxyConfig(BaseModel):
    """代理池配置。"""

    enabled: bool = False
    pool_type: str = "static"  # static | redis
    static_list: list[str] = Field(default_factory=list)
    redis_url: str = ""
    health_check_interval: int = 300
    min_score: int = 30
    default_score: int = 50


class EngineConfig(BaseModel):
    """引擎配置。"""

    http_timeout: float = 15.0
    browser_timeout: float = 45.0
    max_retries: int = 3
    min_content_length: int = 500
    browser_pool_size: int = 2
    browser_headless: bool = True


class BehaviorConfig(BaseModel):
    """行为模拟配置。"""

    min_interval: float = 2.0
    max_interval: float = 10.0
    scroll_steps: int = 5
    scroll_delay: float = 0.8


class CrawlConfig(BaseModel):
    """深度爬取配置。"""

    default_max_pages: int = 50
    default_max_depth: int = 3
    concurrency: int = 8
    per_domain_qps: float = 2.0
    respect_robots: bool = True


class CaptchaConfig(BaseModel):
    """验证码处理配置。"""

    provider: str = "ddddocr"  # ddddocr | capsolver | twocaptcha | none
    api_key: str = ""
    auto_retry: int = 2


class SecurityConfig(BaseModel):
    """安全配置。"""

    api_key: str = ""
    enable_ssrf_protection: bool = True
    url_whitelist: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int = 120


class Settings(BaseSettings):
    """全局配置，env 前缀 CHAMELEON_。"""

    model_config = SettingsConfigDict(
        env_prefix="CHAMELEON_",
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    app_name: str = "chameleon"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False

    proxy: ProxyConfig = ProxyConfig()
    engine: EngineConfig = EngineConfig()
    behavior: BehaviorConfig = BehaviorConfig()
    crawl: CrawlConfig = CrawlConfig()
    captcha: CaptchaConfig = CaptchaConfig()
    security: SecurityConfig = SecurityConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = os.environ.get("CHAMELEON_CONFIG", "config/settings.yaml")
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        if Path(yaml_path).is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=Path(yaml_path), yaml_file_encoding="utf-8"))
        sources.append(file_secret_settings)
        return tuple(sources)


settings = Settings()
