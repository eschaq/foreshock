"""
One-time retroactive dedup cleanup.

For 2026-05-27 only: find legal_event / leadership_change rows in
Airtable that share the same (vendor_name, metric, source_url) triple,
keep the earliest createdTime in each group, delete the rest. Reports
before/after counts and per-vendor deletions.

Pair to the dedup guard added to `foreshock.agent.run_agent_pipeline` —
this cleans up the rows already written before the guard existed.

Usage:
  .venv/bin/python -m scripts.dedup_cleanup_20260527 --dry-run
  .venv/bin/python -m scripts.dedup_cleanup_20260527 --execute
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime

from dotenv import load_dotenv
from pyairtable import Api

CAPTURE_DATE = "2026-05-27"
TABLE_NAME = "signals"
EVENT_METRICS = ("legal_event", "leadership_change")


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
    if not api_key or not base_id:
        print("ERROR: AIRTABLE_API_KEY / AIRTABLE_BASE_ID not set")
        return 1

    dry_run = "--execute" not in sys.argv
    if dry_run:
        print("=== DRY RUN — no deletes will happen ===")
        print("    re-run with --execute to actually delete\n")

    api = Api(api_key)
    table = api.table(base_id, TABLE_NAME)

    # Airtable date fields don't compare to strings with `=`; format then compare.
    formula = (
        f"AND("
        f"DATETIME_FORMAT({{capture_date}},'YYYY-MM-DD')='{CAPTURE_DATE}',"
        f"OR({{metric}}='legal_event',{{metric}}='leadership_change'))"
    )
    records = table.all(formula=formula)
    print(f"fetched {len(records)} event rows with capture_date={CAPTURE_DATE}")

    # Group by (vendor_name, metric, source_url)
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for rec in records:
        f = rec.get("fields", {})
        key = (
            f.get("vendor_name", ""),
            f.get("metric", ""),
            f.get("source_url", ""),
        )
        groups[key].append(rec)

    print(f"grouped into {len(groups)} unique (vendor, metric, source_url) keys")

    # Identify duplicate groups
    duplicates: list[dict] = []  # records to delete
    per_vendor_deletes: dict[str, int] = defaultdict(int)
    for key, recs in groups.items():
        if len(recs) <= 1:
            continue
        # Sort by createdTime ascending; keep [0], delete the rest.
        # createdTime is ISO-8601 — string sort is correct.
        recs_sorted = sorted(recs, key=lambda r: r.get("createdTime", ""))
        kept = recs_sorted[0]
        to_delete = recs_sorted[1:]
        vendor, metric, src = key
        print(
            f"  dup × {len(recs)}: {vendor} / {metric}  "
            f"keeping {kept['id']} ({kept.get('createdTime', '?')}),  "
            f"deleting {len(to_delete)}  "
            f"[source={src[:60]!r}]"
        )
        duplicates.extend(to_delete)
        per_vendor_deletes[vendor] += len(to_delete)

    print(f"\nrows to delete: {len(duplicates)}")
    print("per-vendor breakdown:")
    if per_vendor_deletes:
        for v in sorted(per_vendor_deletes):
            print(f"  {v:20s}  -{per_vendor_deletes[v]}")
    else:
        print("  (no duplicates found)")

    if dry_run or not duplicates:
        print("\n[dry-run] no deletes executed.")
        return 0

    # Execute deletes
    print(f"\ndeleting {len(duplicates)} rows…")
    ids = [r["id"] for r in duplicates]
    # pyairtable supports batch_delete in chunks of 10
    batch = 10
    deleted_total = 0
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        table.batch_delete(chunk)
        deleted_total += len(chunk)
        print(f"  deleted {deleted_total}/{len(ids)}")
    print(f"\ndone. deleted {deleted_total} rows.")
    print(f"timestamp: {datetime.utcnow().isoformat()}Z")
    return 0


if __name__ == "__main__":
    sys.exit(main())
