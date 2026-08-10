"""验证 MCP Server 工具发现与调用链路。
作为 MCP stdio client 启动 server，列出工具并调用 scrape_url。
"""

from __future__ import annotations

import asyncio

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "chameleon.interfaces.mcp_server"],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) 列出所有工具
            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"发现 MCP 工具: {len(tool_names)} 个 → {tool_names}")

            # 2) 调用 scrape_url — 抓 httpbin.org/get
            result = await session.call_tool("scrape_url", {
                "url": "https://httpbin.org/get",
                "output_format": "json",
                "mode": "auto",
            })
            print(f"\nscrape_url 结果 (前 800 字符):")
            text = str(result)
            print(text[:800])


if __name__ == "__main__":
    asyncio.run(main())
