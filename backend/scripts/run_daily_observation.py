"""
Manual daily observation runner (CLI).

Thin wrapper around `foreshock.observation` — the pull helpers are now
the single source of truth in that module, shared with the unattended
`foreshock.agent` daily pipeline. This script just orchestrates a
one-off run and prints a human-readable summary.

Run:  .venv/bin/python scripts/run_daily_observation.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pyairtable import Api

from foreshock.capture import QUERY_CLASSES, REAL_VENDORS
from foreshock.observation import (
    build_veridian_open_roles_row,
    capture_real_vendor,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BD_TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
ANTH_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"
TABLE = "signals"


def baseline(table) -> tuple[int, dict[str, int]]:
    from collections import Counter
    rows = table.all()
    return len(rows), dict(
        Counter(r["fields"].get("vendor_name", "?") for r in rows)
    )


async def main_async() -> None:
    today = date.today().isoformat()
    print(f"Daily observation run — capture_date={today}")
    print(f"  vendors        : {[v['name'] for v in REAL_VENDORS]} + Veridian Pay")
    print(f"  query classes  : {[q['class'] for q in QUERY_CLASSES]} + open_roles")
    print(f"  expected calls : {len(REAL_VENDORS)} vendors × "
          f"({len(QUERY_CLASSES)} classes + 1 careers) = "
          f"{len(REAL_VENDORS) * (len(QUERY_CLASSES) + 1)} MCP calls")
    print(f"  fallback chain : search_engine → retry → "
          f"scrape_as_markdown + AI-parse")
    print()

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    print("[1/4] Snapshot BEFORE")
    before_total, before_by_vendor = baseline(table)
    print(f"      total rows: {before_total}")
    for v, c in sorted(before_by_vendor.items()):
        print(f"        {v}: {c}")
    print()

    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=ANTH_KEY) if ANTH_KEY else None

    fallback_log: list = []
    all_results: list[dict] = []

    print("[2/4] Capturing real vendors via Bright Data MCP (live mode)")
    start = time.monotonic()
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for v in REAL_VENDORS:
                # No emit_event callback — script gets the original silent
                # behavior; events are only emitted when called from agent.py.
                result = await capture_real_vendor(
                    session, v, today, anthropic_client, fallback_log
                )
                all_results.append(result)
                # Print one line per query for human-readable progress
                for cls, count in result["per_class_counts"].items():
                    path = result["fallback_paths"][cls]
                    print(f"    [{v['name']:<10}] {cls:<11} -> "
                          f"{count} results via {path}")
                print(f"    [{v['name']:<10}] open_roles  -> "
                      f"{result['open_roles_value']} hits via "
                      f"{result['open_roles_path']}")
                print()
    elapsed = time.monotonic() - start
    print(f"      real-vendor capture took {elapsed:.1f}s")
    print()

    print(f"[3/4] Veridian Pay staged open_roles continuation")
    veridian_row = build_veridian_open_roles_row(today)
    print(f"      open_roles = {veridian_row['value']} "
          f"({veridian_row['notes'][:80]})")
    print()

    print("[4/4] APPEND-writing Type 2 rows to Airtable")
    all_rows: list[dict] = [veridian_row]
    for r in all_results:
        all_rows.extend(r["rows"])
    created = table.batch_create(all_rows, typecast=True)
    print(f"      created {len(created)} new rows")
    print()

    # Summary table
    print("=" * 84)
    print("PER-VENDOR SUMMARY")
    print("=" * 84)
    print(f"  {'vendor':<13} {'sent':>5} {'lgl':>4} {'lead':>5} "
          f"{'open':>5} {'nvol':>5}  {'paths'}")
    print("  " + "-" * 80)
    for r in all_results:
        paths_summary = ",".join(
            "S" if p == "search_engine"
            else "R" if "retry" in p
            else "F" if "fallback" in p or "scrape" in p
            else "X"
            for p in list(r["fallback_paths"].values()) + [r["open_roles_path"]]
        )
        print(f"  {r['vendor']:<13} {r['sentiment_count']:>5} "
              f"{r['legal_count']:>4} {r['leadership_count']:>5} "
              f"{r['open_roles_value']:>5} {r['news_volume_value']:>5}  {paths_summary}")
    print(f"  {'Veridian Pay':<13} {'-':>5} {'-':>4} {'-':>5} "
          f"{veridian_row['value']:>5} {'-':>5}  STAGED")
    print()
    print("  paths legend: S=search_engine | R=retry | F=fallback (scrape+AI) | X=failed")
    print()
    print(f"Fallback events: {len(fallback_log)}")
    for ev in fallback_log:
        print(f"  - {ev['label']} ({ev['path']}, "
              f"results={ev.get('count', '—')})")

    # Final snapshot
    after_total, after_by_vendor = baseline(table)
    print()
    print("Post-write totals:")
    print(f"  {'vendor':<14} {'before':>7} {'after':>7} {'delta':>7}")
    print("  " + "-" * 50)
    for v in sorted(set(list(before_by_vendor) + list(after_by_vendor))):
        b = before_by_vendor.get(v, 0)
        a = after_by_vendor.get(v, 0)
        print(f"  {v:<14} {b:>7} {a:>7} {a-b:>+7}")
    print()
    print(f"  Total: {before_total} -> {after_total} "
          f"(delta {after_total - before_total:+d})")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
