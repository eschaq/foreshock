"""
Step 2.5 — prove search_engine returns RECENT results, not 2022-era stale ones.

Why: freshness IS the product (CLAUDE.md Sec 1 / hackathon theme). The earlier
pull's top hits were 4-year-old Stripe layoff stories, which would gut the demo.

Strategy:
  1. Introspect search_engine input schema (look for native recency params).
  2. Dump the FIRST organic record fully (look for a `date` field).
  3. Run with Google's `after:` operator in the query — portable, no tool-specific
     params required.
  4. Parse the date prefix Google emits in snippets and tally how many are 2026.

Run:  .venv/bin/python scripts/test_recency_filter.py
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
URL = f"https://mcp.brightdata.com/mcp?token={TOKEN}"

# Recency via Google operators (portable). after: filters by indexed date.
QUERY = "Stripe news layoffs lawsuit funding after:2026-01-01"

# Google snippet date prefix:  "Apr 15, 2026 — ..."  or  "5 days ago — ..."
ABS_DATE_RX = re.compile(r"(\w+\s+\d{1,2},\s+(\d{4}))\s+[—-]")
REL_DATE_RX = re.compile(r"(\d+\s+(?:day|week|month|hour)s?\s+ago)\s+[—-]", re.I)


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- 1. schema introspection ---
            tools = await session.list_tools()
            se = next(t for t in tools.tools if t.name == "search_engine")
            print("search_engine inputSchema:")
            print(json.dumps(se.inputSchema, indent=2))
            print()

            # --- 2. + 3. call with recency-constrained query ---
            print(f"Query: {QUERY!r}\n")
            result = await session.call_tool(
                "search_engine",
                arguments={"query": QUERY, "engine": "google"},
            )
            if result.isError:
                sys.exit(f"MCP error: {result.content}")
            payload = json.loads(result.content[0].text)
            organic = payload.get("organic", [])

            # Dump first record fully so we can see if a `date` field exists.
            if organic:
                print("First organic record (full shape):")
                print(json.dumps(organic[0], indent=2))
                print()

            # --- 4. tally + display ---
            print(f"Got {len(organic)} organic results.\n")
            print(f"{'#':<3} {'date':<24} title")
            print("-" * 110)
            year_counts: dict[str, int] = {}
            for i, item in enumerate(organic, 1):
                desc = item.get("description") or ""
                title = (item.get("title") or "")[:75]
                link = (item.get("link") or "")[:95]

                year = None
                m_abs = ABS_DATE_RX.search(desc)
                m_rel = REL_DATE_RX.search(desc)
                if m_abs:
                    date_str = m_abs.group(1)
                    year = m_abs.group(2)
                elif m_rel:
                    date_str = m_rel.group(1)
                    year = "recent"  # "5 days ago" -> by definition recent
                else:
                    date_str = "—"
                    year = "unknown"
                year_counts[year] = year_counts.get(year, 0) + 1

                print(f"{i:<3} {date_str:<24} {title}")
                print(f"    {link}")

            print("\nYear breakdown:", dict(sorted(year_counts.items())))
            recent = year_counts.get("2026", 0) + year_counts.get("recent", 0)
            print(f"Recent (2026 or relative): {recent}/{len(organic)}")


if __name__ == "__main__":
    asyncio.run(main())
