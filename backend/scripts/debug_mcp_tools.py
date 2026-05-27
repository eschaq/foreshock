"""List all Bright Data MCP tools and short descriptions."""
import asyncio
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
            print(f"Total tools: {len(tools.tools)}\n")
            for t in tools.tools:
                desc = (t.description or "").split("\n")[0][:100]
                print(f"  {t.name:<40} {desc}")


asyncio.run(main())
