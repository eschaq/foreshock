"""
Step 4.5 — daily recency-filtered capture for all 5 real vendors.

Runs `foreshock.capture.capture_all` (Bright Data MCP search_engine, 4
query classes × 5 vendors, after:2026-01-01 recency operator) and
APPEND-writes the produced Type 2 rows to the `signals` Airtable table.

Never overwrites — capture_date stamps today, every row is new.

Verifies before/after row counts per vendor so we can confirm:
  - new rows landed (delta > 0 per real vendor)
  - existing rows untouched (Veridian arc + yesterday's Stripe rows unchanged)
  - source URLs look recent (sampling)

Run:  .venv/bin/python scripts/run_daily_capture.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.capture import REAL_VENDORS, capture_all

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BD_TOKEN = os.environ["BRIGHTDATA_API_TOKEN"]
AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"
TABLE = "signals"
AFTER = "2026-01-01"


def snapshot(table) -> tuple[int, dict[str, int]]:
    rows = table.all()
    return len(rows), dict(Counter(
        r["fields"].get("vendor_name", "UNKNOWN") for r in rows
    ))


async def main() -> None:
    today = date.today().isoformat()
    print(f"Step 4.5: recency-filtered capture for all 5 real vendors")
    print(f"  capture_date = {today}")
    print(f"  after        = {AFTER}")
    print(f"  vendors      = {[v['name'] for v in REAL_VENDORS]}")
    print(f"  query classes per vendor: news, lawsuit, layoff, leadership")
    print(f"  expected MCP calls: 4 × 5 = 20\n")

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    print("[1/4] Snapshot BEFORE capture")
    before_total, before_by_vendor = snapshot(table)
    print(f"      total rows: {before_total}")
    for v, c in sorted(before_by_vendor.items()):
        print(f"        {v}: {c}")
    print()

    print("[2/4] Running capture (sequential — ~2-4s per MCP call) ...")
    captures = await capture_all(MCP_URL, REAL_VENDORS, after=AFTER, top_n=5)
    print()
    print(f"      {'vendor':<14} {'per-class counts':<48} "
          f"{'rows':>5} {'legal':>5} {'leader':>6}")
    print("      " + "-" * 90)
    total_rows = 0
    for cap in captures:
        per_class = ", ".join(f"{k}={v}" for k, v in cap.per_class_counts.items())
        total_rows += len(cap.rows)
        print(f"      {cap.vendor_name:<14} {per_class:<48} "
              f"{len(cap.rows):>5} "
              f"{cap.events_detected.get('legal', 0):>5} "
              f"{cap.events_detected.get('leadership', 0):>6}")
    print(f"      total rows to write: {total_rows}\n")

    print("[3/4] APPEND-writing Type 2 rows to signals ...")
    all_rows: list[dict] = []
    for cap in captures:
        all_rows.extend(cap.rows)
    created = table.batch_create(all_rows, typecast=True)
    print(f"      created {len(created)} records\n")

    print("[4/4] Verification — snapshot AFTER capture")
    after_total, after_by_vendor = snapshot(table)
    print(f"      total rows: {before_total} -> {after_total} "
          f"(delta {after_total - before_total:+d})\n")

    print(f"      {'vendor':<18} {'before':>7} {'after':>7} {'delta':>7}")
    print("      " + "-" * 50)
    all_vendors = sorted(set(list(before_by_vendor) + list(after_by_vendor)))
    for v in all_vendors:
        b = before_by_vendor.get(v, 0)
        a = after_by_vendor.get(v, 0)
        marker = "  <-- demo vendor (should be unchanged)" if v == "Veridian Pay" else ""
        print(f"      {v:<18} {b:>7} {a:>7} {a-b:>+7}{marker}")
    print()

    # Recency sampling: pull today's rows and show one news_sentiment per vendor
    print("--- Sample today's news_sentiment row per vendor (check 2026 URLs) ---")
    today_rows = table.all(formula=f"DATESTR({{capture_date}})='{today}'")
    by_v: dict[str, list[dict]] = defaultdict(list)
    for r in today_rows:
        f = r["fields"]
        by_v[f.get("vendor_name", "?")].append(f)

    for v in [vd["name"] for vd in REAL_VENDORS]:
        rows = by_v.get(v, [])
        sentiment_rows = [r for r in rows if r.get("metric") == "news_sentiment"]
        vol_rows = [r for r in rows if r.get("metric") == "news_volume"]
        ev_legal = [r for r in rows if r.get("metric") == "legal_event"]
        ev_lead = [r for r in rows if r.get("metric") == "leadership_change"]
        print(f"  [{v}] today: {len(rows)} rows "
              f"({len(sentiment_rows)} sentiment, "
              f"{len(vol_rows)} volume, "
              f"{len(ev_legal)} legal_event, "
              f"{len(ev_lead)} leadership_change)")
        if vol_rows:
            print(f"       volume: {vol_rows[0].get('notes', '')[:100]}")
        if sentiment_rows:
            sr = sentiment_rows[0]
            print(f"       sample: {sr.get('notes', '')[:100]}")
            print(f"               -> {sr.get('source_url', '')[:90]}")
        for ev in (ev_legal + ev_lead)[:2]:
            print(f"       EVENT [{ev.get('metric')}]: {ev.get('value', '')[:80]}")
    print()

    # Integrity sanity check
    print("--- Integrity check ---")
    untouched = (
        before_by_vendor.get("Veridian Pay", 0)
        == after_by_vendor.get("Veridian Pay", 0)
    )
    if untouched:
        print("  OK Veridian Pay row count unchanged "
              f"({before_by_vendor.get('Veridian Pay', 0)} -> "
              f"{after_by_vendor.get('Veridian Pay', 0)})")
    else:
        print("  WARN Veridian Pay count CHANGED — investigate.")

    pre_existing_real = {"Stripe", "Plaid", "Snowflake", "Twilio", "AWS"}
    monotonic = all(
        after_by_vendor.get(v, 0) >= before_by_vendor.get(v, 0)
        for v in pre_existing_real
    )
    if monotonic:
        print("  OK All real-vendor row counts only INCREASED (Type 2 append-only).")
    else:
        print("  WARN Some real-vendor count DECREASED — investigate.")


if __name__ == "__main__":
    asyncio.run(main())
