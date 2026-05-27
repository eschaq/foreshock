"""Inspect scrape_as_markdown input schema for options."""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
BD_TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                if t.name in ("scrape_as_markdown", "scrape_batch"):
                    print(f"\n=== {t.name} ===")
                    print(f"Description (full):\n{t.description}\n")
                    print(f"Input schema:\n{json.dumps(t.inputSchema, indent=2)}")


asyncio.run(main())
