"""
Smoke test: hosted Bright Data MCP connector.

Proves three things before we build anything else:
  1. The hosted MCP URL authenticates with BRIGHTDATA_API_TOKEN.
  2. A fast base tool (search_engine) returns real data.
  3. We can see the shape of what comes back, so we know how to parse it next.

Free-tier base tools only — no polling web_data_* extractors.
Run:  .venv/bin/python scripts/test_brightdata_mcp.py
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN")
if not TOKEN:
    sys.exit("BRIGHTDATA_API_TOKEN missing from backend/.env")

MCP_URL = f"https://mcp.brightdata.com/mcp?token={TOKEN}"


async def main() -> None:
    print(f"Connecting to Bright Data MCP (hosted) ...")
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("  init OK\n")

            # 1. Auth check — list tools.
            tools = await session.list_tools()
            print(f"Auth OK. {len(tools.tools)} tools exposed by the server.")
            base = [t.name for t in tools.tools if t.name in {"search_engine", "scrape_as_markdown", "discover"}]
            print(f"Free-tier base tools visible: {base}\n")

            # 2. Fast call — search for fresh Stripe signals.
            query = "Stripe news 2026 layoffs lawsuit funding"
            print(f"Calling search_engine  query={query!r}")
            result = await session.call_tool(
                "search_engine",
                arguments={"query": query, "engine": "google"},
            )

            # 3. Shape inspection.
            print(f"\nisError: {result.isError}")
            print(f"content blocks: {len(result.content)}")
            for i, block in enumerate(result.content):
                kind = type(block).__name__
                text = getattr(block, "text", None)
                if text is None:
                    print(f"\n[{i}] {kind} (non-text) -> {block!r}")
                    continue
                print(f"\n[{i}] {kind}  len={len(text)} chars")
                print("-" * 60)
                print(text[:3000])
                if len(text) > 3000:
                    print(f"... [truncated {len(text) - 3000} more chars]")


if __name__ == "__main__":
    asyncio.run(main())
