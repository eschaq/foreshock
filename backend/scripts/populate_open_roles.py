"""
Bring the open_roles dimension to life.

What this does:
  1. DELETES the legacy empty open_roles placeholder rows (5 rows with
     `value=""` left by the original test_airtable_write.py seeding).
  2. PULLS a single live open_roles observation for each of the 5 real
     vendors via Bright Data MCP (`search_engine`, careers/jobs/hiring
     query, recency-filtered, disambiguated query_name). Writes one
     Type 2 row per vendor with today's capture_date.
  3. WRITES Veridian's staged 30-day open_roles arc — a hiring freeze
     that mirrors the existing headcount decline (480 → 410). Five
     historical dates matching the rest of the Veridian arc.

Run:  .venv/bin/python scripts/populate_open_roles.py
      .venv/bin/python scripts/populate_open_roles.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pyairtable import Api

from foreshock.capture import REAL_VENDORS, capture_open_roles_for_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BD_TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"
TABLE = "signals"


# Veridian's open_roles freeze arc — mirrors the existing headcount decline
# (480→410 over 28 days). Drops faster than headcount because hiring freezes
# precede layoffs (the leading-indicator behavior open_roles is meant to catch).
#
# Trajectory: 38 → 8 over 28 days = -79% — should fire the open_roles
# component at ~100/100 with the new 0.06 weight (≈ +6 to total score).
VERIDIAN_ARC = [
    {"capture_date": "2026-04-23", "value": 38, "sentiment": "neutral",
     "notes": "STUBBED open_roles day-30 baseline healthy (~38 active postings)"},
    {"capture_date": "2026-05-02", "value": 32, "sentiment": "neutral",
     "notes": "STUBBED open_roles day-21 first crack (-16% from baseline)"},
    {"capture_date": "2026-05-09", "value": 22, "sentiment": "negative",
     "notes": "STUBBED open_roles day-14 warning (-42% from baseline)"},
    {"capture_date": "2026-05-16", "value": 14, "sentiment": "negative",
     "notes": "STUBBED open_roles day-7 escalating hiring slowdown (-63%)"},
    {"capture_date": "2026-05-21", "value": 8, "sentiment": "negative",
     "notes": "STUBBED open_roles day-2 hiring freeze (-79% from baseline)"},
]


def build_veridian_rows() -> list[dict]:
    return [
        {
            "capture_date": r["capture_date"],
            "vendor_name": "Veridian Pay",
            "vendor_type": "Payments/BaaS",
            "is_demo_vendor": True,
            "metric": "open_roles",
            "value": str(r["value"]),
            "unit": "postings",
            "source_url": "DEMO-SCENARIO",
            "sentiment": r["sentiment"],
            "notes": r["notes"],
        }
        for r in VERIDIAN_ARC
    ]


def find_legacy_empty_rows(table) -> list[dict]:
    """Find open_roles rows whose value field is empty/missing."""
    rows = table.all(formula="{metric}='open_roles'")
    return [
        r for r in rows
        if not (r["fields"].get("value") or "").strip()
    ]


async def pull_real_vendor_rows(capture_date: str) -> list[dict]:
    """Fire one MCP careers query per real vendor; return Type 2 rows."""
    rows: list[dict] = []
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for v in REAL_VENDORS:
                print(f"  pulling {v['name']:<10} careers query "
                      f"({v.get('query_name', v['name'])})...")
                row = await capture_open_roles_for_vendor(
                    session, v, capture_date=capture_date
                )
                rows.append(row)
                print(f"      -> open_roles = {row['value']}")
    return rows


async def main_async(args) -> None:
    today = date.today().isoformat()
    print(f"populate_open_roles  capture_date={today}  "
          f"mode={'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    # 1. Find legacy empty rows
    print("[1/4] Finding legacy empty open_roles rows...")
    legacy = find_legacy_empty_rows(table)
    print(f"      found {len(legacy)} legacy rows to delete:")
    for r in legacy:
        f = r["fields"]
        print(f"        {f.get('vendor_name','?'):<12} "
              f"{f.get('capture_date','?')}  "
              f"notes={(f.get('notes') or '')[:50]}")

    # 2. Pull real-vendor live counts
    print()
    print("[2/4] Pulling careers queries for real vendors via MCP...")
    real_rows = await pull_real_vendor_rows(capture_date=today)

    # 3. Build Veridian staged arc
    print()
    print("[3/4] Building Veridian staged hiring-freeze arc...")
    veridian_rows = build_veridian_rows()
    for r in veridian_rows:
        print(f"      Veridian Pay {r['capture_date']}  value={r['value']:<3}  "
              f"sentiment={r['sentiment']:<8}  ({r['notes'][:55]})")

    if args.dry_run:
        print()
        print(f"(dry-run: would delete {len(legacy)} legacy rows, "
              f"write {len(real_rows) + len(veridian_rows)} new rows)")
        return

    # 4. Apply changes
    print()
    print("[4/4] Applying changes to Airtable...")
    if legacy:
        table.batch_delete([r["id"] for r in legacy])
        print(f"      deleted {len(legacy)} legacy rows")

    all_new = real_rows + veridian_rows
    created = table.batch_create(all_new, typecast=True)
    print(f"      created {len(created)} new open_roles rows")

    # Bust the summary cache so the dashboard regenerates Claude narratives
    # that may now want to mention the new open_roles signals.
    print("      busting summary cache via /cache/summaries/clear...")
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:8000/cache/summaries/clear",
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            print(f"      -> {resp.read().decode()}")
    except Exception as e:
        print(f"      -> cache-clear skipped (backend not reachable): {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="show planned actions, write nothing")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
