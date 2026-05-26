"""
Post-hoc validator for today's banked event rows.

Pulls every legal_event + leadership_change row from the signals table
that was captured today against a real (non-demo) vendor, asks Claude
to confirm each is a GENUINE event at that vendor (not a similarly-named
entity, share sale, pay disclosure, opinion piece, etc.), and DELETES
the rejects.

The corresponding news_sentiment row for the same URL is independent and
stays — only the event tag goes away.

Run:  .venv/bin/python scripts/clean_todays_events.py
      .venv/bin/python scripts/clean_todays_events.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.validator import get_default_client, validate_event

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"

EVENT_METRICS = ("legal_event", "leadership_change")


def candidate_title(fields: dict) -> str:
    """Reconstruct the original title from the stored notes/value."""
    notes = fields.get("notes") or ""
    for prefix in ("auto-detected: ", "validated ("):
        if notes.startswith(prefix):
            # strip prefix; if it was "validated (reason): title" we keep title.
            if prefix == "auto-detected: ":
                return notes[len(prefix):].strip()
            # validated form: "validated (reason): title"
            after_close = notes.split("): ", 1)
            if len(after_close) == 2:
                return after_close[1].strip()
    # fall back to value (which is the title truncated to 90 chars)
    return (fields.get("value") or "").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="validate + print verdicts, but DO NOT delete")
    args = ap.parse_args()

    today = date.today().isoformat()
    print(f"Validating today's event rows (capture_date={today})")
    print(f"  mode: {'DRY RUN — no deletes' if args.dry_run else 'LIVE — rejects will be deleted'}\n")

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    metric_or = ", ".join(f"{{metric}}='{m}'" for m in EVENT_METRICS)
    formula = (
        f"AND("
        f"DATESTR({{capture_date}})='{today}', "
        f"OR({metric_or}), "
        f"NOT({{is_demo_vendor}})"
        f")"
    )
    records = table.all(formula=formula)
    print(f"Found {len(records)} candidate event rows for real vendors.\n")

    if not records:
        print("Nothing to validate.")
        return

    client = get_default_client()

    accepted: list[dict] = []
    rejected: list[dict] = []

    print(f"  {'#':<3} {'vendor':<12} {'metric':<18} {'verdict':<8} reason / title")
    print("  " + "-" * 110)
    for i, rec in enumerate(records, 1):
        f = rec["fields"]
        vendor = f.get("vendor_name", "?")
        metric = f.get("metric", "?")
        title = candidate_title(f)

        result = validate_event(client, vendor, metric, title)
        entry = {
            "id": rec["id"],
            "vendor": vendor,
            "metric": metric,
            "title": title,
            "source_url": f.get("source_url", ""),
            "reason": result.reason,
            "valid": result.valid,
        }
        verdict = "KEEP" if result.valid else "REJECT"
        (accepted if result.valid else rejected).append(entry)
        title_short = (title[:70] + "...") if len(title) > 70 else title
        print(f"  {i:<3} {vendor:<12} {metric:<18} {verdict:<8} "
              f"{result.reason} | {title_short}")

    print()
    print(f"Summary: {len(accepted)} KEPT, {len(rejected)} REJECTED")
    print()

    if accepted:
        print("--- KEPT (validated as real events) ---")
        for e in accepted:
            print(f"  [{e['vendor']}] {e['metric']}: {e['title'][:80]}")
            print(f"      reason: {e['reason']}")
            print(f"      url:    {e['source_url'][:100]}")
        print()

    if rejected:
        print("--- REJECTED (false positives) ---")
        for e in rejected:
            print(f"  [{e['vendor']}] {e['metric']}: {e['title'][:80]}")
            print(f"      reason: {e['reason']}")
            print(f"      url:    {e['source_url'][:100]}")
        print()

    if args.dry_run:
        print("(dry-run: not deleting)")
        return

    if rejected:
        ids = [e["id"] for e in rejected]
        print(f"Deleting {len(ids)} rejected event rows ...")
        # pyairtable supports batch_delete
        deleted = table.batch_delete(ids)
        print(f"Deleted: {len(deleted)} records.")
    else:
        print("Nothing to delete.")

    # Final per-vendor event-row tally for today.
    print()
    print("--- Post-cleanup event counts for today, per vendor ---")
    remaining = table.all(formula=formula)
    from collections import Counter
    by_v: dict[str, Counter] = {}
    for r in remaining:
        f = r["fields"]
        v = f.get("vendor_name", "?")
        m = f.get("metric", "?")
        by_v.setdefault(v, Counter())[m] += 1
    if not by_v:
        print("  (no event rows remain for real vendors today — expected:")
        print("   real vendors should be stable, no leadership/legal events)")
    else:
        for v, counter in sorted(by_v.items()):
            parts = ", ".join(f"{m}={c}" for m, c in counter.items())
            print(f"  {v}: {parts}")


if __name__ == "__main__":
    main()
