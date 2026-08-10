"""代理池管理脚本：导入/导出/探活/评分管理。

用法:
    uv run python scripts/proxy_pool_mgmt.py import proxies.csv    # 导入代理列表
    uv run python scripts/proxy_pool_mgmt.py healthcheck            # 全量探活
    uv run python scripts/proxy_pool_mgmt.py status                 # 查看池状态
    uv run python scripts/proxy_pool_mgmt.py add http://proxy:8080  # 添加单个代理

生产环境配置:
    1. 设置 settings.yaml proxy.enabled=true, pool_type=redis
    2. docker-compose up -d redis  # 启动 Redis
    3. 导入代理池: uv run python scripts/proxy_pool_mgmt.py import proxies.csv
    4. 确认 DNS 访问 (httpbin.org/gstatic.com 需可达)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

# 添加项目根到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chameleon.anti_detection.proxy_manager import ProxyManager
from chameleon.core.config import ProxyConfig


def build_config(args: argparse.Namespace) -> ProxyConfig:
    return ProxyConfig(
        enabled=True,
        pool_type=args.pool_type,
        static_list=[],
        redis_url=args.redis_url,
        health_check_interval=args.health_interval,
        min_score=args.min_score,
        default_score=args.default_score,
    )


async def cmd_import(config: ProxyConfig, args: argparse.Namespace) -> None:
    mgr = ProxyManager(config)
    with open(args.file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            proxy = row.get("proxy") or row.get("url") or row.get("address", "").strip()
            if not proxy:
                continue
            region = row.get("region", "").strip() or None
            await mgr.add(proxy, region=region)
            count += 1
    print(f"Imported {count} proxies")
    await mgr.close()


async def cmd_healthcheck(config: ProxyConfig, args: argparse.Namespace) -> None:
    mgr = ProxyManager(config)
    await mgr.health_check_once()

    alive = sum(1 for p in mgr._pool.values() if p.alive)  # noqa: SLF001
    total = len(mgr._pool)  # noqa: SLF001
    print(f"Health check: {alive}/{total} alive")

    for info in mgr._pool.values():  # noqa: SLF001
        status = "✓" if info.alive else "✗"
        print(f"  {status} {info.proxy} score={info.score} latency={info.response_time_ms}ms")

    await mgr.close()


async def cmd_status(config: ProxyConfig) -> None:
    mgr = ProxyManager(config)
    pool = mgr._pool  # noqa: SLF001
    if not pool:
        print("Proxy pool is empty")
        return

    alive = sum(1 for p in pool.values() if p.alive)
    print(f"Pool: {alive}/{len(pool)} alive")
    print(f"{'Proxy':<40} {'Score':<8} {'Alive':<6} {'Region':<10}")
    print("-" * 70)
    for info in pool.values():
        print(f"{info.proxy:<40} {info.score:<8} {str(info.alive):<6} {info.region or '-':<10}")

    await mgr.close()


async def cmd_add(config: ProxyConfig, args: argparse.Namespace) -> None:
    mgr = ProxyManager(config)
    await mgr.add(args.proxy, region=args.region)
    print(f"Added {args.proxy}" + (f" (region={args.region})" if args.region else ""))
    await mgr.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chameleon 代理池管理")
    sub = parser.add_subparsers(dest="command")

    # 公共配置
    for cmd_name in ["import", "healthcheck", "status", "add"]:
        s = sub.add_parser(cmd_name)
        s.add_argument("--pool-type", default="redis", choices=["static", "redis"])
        s.add_argument("--redis-url", default="redis://localhost:6379/0")
        s.add_argument("--health-interval", type=int, default=300)
        s.add_argument("--min-score", type=int, default=30)
        s.add_argument("--default-score", type=int, default=50)

    sub.add_parser("status")

    imp = sub.add_parser("import")
    imp.add_argument("file", help="CSV with proxy,region columns")

    hc = sub.add_parser("healthcheck")

    add = sub.add_parser("add")
    add.add_argument("proxy", help="http://host:port")
    add.add_argument("--region", default=None)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    config = build_config(args)

    if args.command == "import":
        asyncio.run(cmd_import(config, args))
    elif args.command == "healthcheck":
        asyncio.run(cmd_healthcheck(config, args))
    elif args.command == "status":
        asyncio.run(cmd_status(config))
    elif args.command == "add":
        asyncio.run(cmd_add(config, args))


if __name__ == "__main__":
    main()
