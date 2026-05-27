"""
Wave 2 smoke test: SEC EDGAR pull for all 3 EDGAR-eligible vendors.
Reports vendors processed, 8-Ks found, items matched, rows that WOULD
be written. Pass `--write` to actually batch_create the rows in Airtable.

Run:
    .venv/bin/python scripts/test_edgar.py                  # dry run, 30d
    .venv/bin/python scripts/test_edgar.py --days 365       # wider lookback
    .venv/bin/python scripts/test_edgar.py --write          # promote (30d)
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.capture import REAL_VENDORS
from foreshock.edgar import capture_edgar_for_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"


def emit(payload: dict) -> None:
    """Print SSE-shaped events the way the FlowPanel would render them."""
    step = payload.get("step", "?")
    vendor = payload.get("vendor", "?")
    klass = payload.get("class", "")
    status = payload.get("status", "")
    extras = []
    for k in ("filings_found", "items_matched", "duration_ms", "error"):
        if k in payload:
            extras.append(f"{k}={payload[k]}")
    print(f"  [{step}] {vendor} {klass:<10} {status:<8} " + " ".join(extras))


async def main() -> None:
    write_mode = "--write" in sys.argv
    lookback = 30
    if "--days" in sys.argv:
        lookback = int(sys.argv[sys.argv.index("--days") + 1])
    today = date.today().isoformat()
    vendors_with_cik = [v for v in REAL_VENDORS if v.get("cik")]
    skipped = [v["name"] for v in REAL_VENDORS if not v.get("cik")]

    print(f"Wave 2 — EDGAR smoke test ({today}, lookback={lookback}d)")
    print(f"Eligible vendors: {[v['name'] for v in vendors_with_cik]}")
    print(f"Skipped (no CIK): {skipped}")
    print(f"Write mode: {'ENABLED — will promote rows' if write_mode else 'dry-run (use --write to promote)'}")
    print()

    results: list[dict] = []
    # EDGAR doesn't need MCP — go direct. No streamablehttp_client needed.
    for vendor in vendors_with_cik:
        print(f"--- {vendor['name']} (CIK {vendor['cik']}) ---")
        result = await capture_edgar_for_vendor(
            None, vendor, today, emit_event=emit, lookback_days=lookback,
        )
        results.append(result)
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  filings_found={result['filings_found']} "
                  f"items_matched={result['items_matched']}")
            for row in result["rows"]:
                print(f"    -> {row['metric']:<18} "
                      f"value={row['value'][:80]!r}")
                print(f"       source={row['source_url']}")
        print()

    total_filings = sum(r.get("filings_found", 0) for r in results)
    total_items = sum(r.get("items_matched", 0) for r in results)
    all_rows = [row for r in results for row in r.get("rows", [])]

    print("=" * 64)
    print(f"SUMMARY: {len(vendors_with_cik)} vendors processed, "
          f"{total_filings} 8-Ks found, {total_items} items matched, "
          f"{len(all_rows)} candidate rows built.")

    if not all_rows:
        print("No candidate rows — nothing to promote.")
        return

    if write_mode:
        api = Api(AT_KEY)
        table = api.table(AT_BASE, TABLE)
        # Soft dedup against existing (vendor, metric, source_url) keys —
        # mirrors the agent.py dedup guard. Skip rows already in Airtable.
        existing = table.all(
            fields=["vendor_name", "metric", "source_url"],
            formula="OR({metric}='legal_event', {metric}='leadership_change')",
        )
        existing_keys = {
            (rec["fields"].get("vendor_name", ""),
             rec["fields"].get("metric", ""),
             rec["fields"].get("source_url", ""))
            for rec in existing
        }
        to_write = [
            r for r in all_rows
            if (r["vendor_name"], r["metric"], r.get("source_url", "")) not in existing_keys
        ]
        skipped_existing = len(all_rows) - len(to_write)
        print(f"Dedup: {skipped_existing} rows already in Airtable, "
              f"{len(to_write)} new rows to write.")
        if to_write:
            created = table.batch_create(to_write, typecast=True)
            print(f"Wrote {len(created)} rows.")


if __name__ == "__main__":
    asyncio.run(main())
