"""Diagnostic: what does Bright Data actually return for a JSON URL?"""
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

URL = "https://data.sec.gov/submissions/CIK0001640147.json"


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # List available tools so we know what's there
            tools = await session.list_tools()
            relevant = [t.name for t in tools.tools
                        if any(k in t.name.lower() for k in ("scrape", "fetch", "url"))]
            print(f"Tools containing scrape/fetch/url: {relevant}")
            print()

            print(f"Calling scrape_as_markdown on:\n  {URL}\n")
            res = await session.call_tool("scrape_as_markdown", arguments={"url": URL})
            print(f"isError: {res.isError}")
            print(f"content items: {len(res.content) if res.content else 0}")
            for i, c in enumerate(res.content or []):
                t = getattr(c, "text", "<no text attr>")
                print(f"  [{i}] type={getattr(c, 'type', '?')}, "
                      f"text_len={len(t) if isinstance(t, str) else 'N/A'}")
                if isinstance(t, str) and t:
                    print(f"  [{i}] first 500 chars: {t[:500]!r}")
                    print(f"  [{i}] last 200 chars: {t[-200:]!r}")


asyncio.run(main())
