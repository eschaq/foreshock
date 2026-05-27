"""Test scrape_as_markdown against SEC's HTML browse-edgar page."""
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

# HTML filings list — browse-edgar returns an HTML table of recent filings.
HTML_LIST_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
    "&CIK=0001640147&type=8-K&dateb=&owner=include&count=40"
)


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()
            print(f"Calling scrape_as_markdown on browse-edgar HTML URL:")
            print(f"  {HTML_LIST_URL}\n")
            res = await session.call_tool("scrape_as_markdown",
                                          arguments={"url": HTML_LIST_URL})
            print(f"isError: {res.isError}")
            if res.content:
                t = res.content[0].text or ""
                print(f"text_len: {len(t)}")
                print(f"\n--- first 3000 chars ---")
                print(t[:3000])
                print(f"\n--- last 500 chars ---")
                print(t[-500:])


asyncio.run(main())
