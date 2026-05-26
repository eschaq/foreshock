"""
Step 2 smoke test: Bright Data pull -> Airtable Type 2 append-write.

Pulls fresh Stripe news signals via the hosted Bright Data MCP server,
parses the JSON-in-text-block from search_engine, extracts news_volume +
per-article news_sentiment, and APPENDS new timestamped rows to the
`signals` table. Type 2 / never overwrite (CLAUDE.md Section 4).

Stripe only — proves the write path end to end before generalizing.

Run:  .venv/bin/python scripts/test_airtable_write.py
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pyairtable import Api

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BD_TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
AT_KEY = os.environ["AIRTABLE_API_KEY"]
# Defensive: .env may contain the full URL path (app.../tbl.../viw...).
# Take the leading appXXXX segment only.
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"
TABLE = "signals"

VENDOR = {
    "vendor_name": "Stripe",
    "vendor_type": "Payments",
    "is_demo_vendor": False,
    "query": "Stripe news 2026 layoffs lawsuit funding",
}

# Simple keyword sentiment heuristic. Good enough to prove the write path;
# Claude-driven scoring lives in step 5 (AI summary).
NEG = {
    "layoff", "laid off", "lay off", "cut", "cuts", "fired", "lawsuit",
    "sued", "suit ", "breach", "hack", "outage", "fraud", "scandal",
    "investigation", "fine ", "penalty", "resign", "departure", "downturn",
    "decline", "plunge", "slash", "axe", "struggle", "downgrade", "bloodbath",
}
POS = {
    "growth", "raise", "raised", "funding round", "hire", "hiring", "expand",
    "launch", "partner", "acquired", "acquisition", "profit", "milestone",
    "success", "beat", "valuation", "ipo",
}


def score_sentiment(text: str) -> tuple[int, str]:
    t = " " + text.lower() + " "
    neg = sum(1 for w in NEG if w in t)
    pos = sum(1 for w in POS if w in t)
    diff = pos - neg
    if diff < 0:
        return -1, "negative"
    if diff > 0:
        return 1, "positive"
    return 0, "neutral"


async def fetch_organic() -> list[dict]:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_engine",
                arguments={"query": VENDOR["query"], "engine": "google"},
            )
    if result.isError:
        sys.exit(f"MCP error: {result.content}")
    payload = json.loads(result.content[0].text)
    return payload.get("organic", [])


def build_rows(organic: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    base = {
        "capture_date": today,
        "vendor_name": VENDOR["vendor_name"],
        "vendor_type": VENDOR["vendor_type"],
        "is_demo_vendor": VENDOR["is_demo_vendor"],
    }
    rows: list[dict] = []
    # Per-article sentiment rows — preserves source_url for Claude citations.
    for item in organic:
        text = f"{item.get('title', '')} {item.get('description', '')}"
        value, label = score_sentiment(text)
        rows.append({
            **base,
            "metric": "news_sentiment",
            "value": value,
            "unit": "score",
            "source_url": item.get("link", ""),
            "sentiment": label,
            "notes": (item.get("title") or "")[:255],
        })
    # Aggregate news_volume row.
    query_url = "https://www.google.com/search?q=" + VENDOR["query"].replace(" ", "+")
    rows.append({
        **base,
        "metric": "news_volume",
        "value": len(organic),
        "unit": "count",
        "source_url": query_url,
        "sentiment": "",
        "notes": f"organic results for query: {VENDOR['query']}",
    })
    return rows


async def main() -> None:
    print("Step 2: Bright Data MCP -> Airtable Type 2 append-write\n")

    print(f"Base ID resolved to: {AT_BASE}")
    print(f"Table: {TABLE}\n")

    print("[1/4] Pulling Stripe news via search_engine ...")
    organic = await fetch_organic()
    print(f"      got {len(organic)} organic results\n")

    print("[2/4] Building Type 2 rows ...")
    rows = build_rows(organic)
    print(f"      built {len(rows)} rows "
          f"({len(rows) - 1} news_sentiment + 1 news_volume)\n")

    print("[3/4] APPEND-writing to Airtable signals ...")
    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)
    created = table.batch_create(rows, typecast=True)
    print(f"      created {len(created)} records\n")

    print("[4/4] Verifying — re-querying signals table for Stripe today ...")
    today = date.today().isoformat()
    # Airtable formula: capture_date is a Date field; compare via DATESTR.
    formula = f"AND({{vendor_name}}='Stripe', DATESTR({{capture_date}})='{today}')"
    fetched = table.all(formula=formula)
    print(f"      query returned {len(fetched)} Stripe rows with "
          f"capture_date={today}\n")

    print("New rows just landed in Airtable:")
    print(f"  {'metric':<16} {'value':>5} {'sent.':<9} source_url")
    print("  " + "-" * 100)
    for r in fetched:
        f = r["fields"]
        print(f"  {f.get('metric',''):<16} {str(f.get('value','')):>5} "
              f"{f.get('sentiment',''):<9} {(f.get('source_url') or '')[:70]}")


if __name__ == "__main__":
    asyncio.run(main())
