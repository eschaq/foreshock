"""
Audit + repair misleading [leadership] / [lawsuit] prefixes in signal notes.

When the per-class capture runs a keyword search like "Plaid CEO ... departs",
Google returns a mix — some real, some off-topic. Every hit becomes a
news_sentiment row whose notes are prefixed with the QUERY CLASS that
returned it (e.g., "[leadership] Qlik's Capone departs..."). These
prefixes don't feed the scoring (only metric=leadership_change /
legal_event rows do), but they would mislead a viewer of a future Vendor
Detail View into thinking the row IS a leadership event at the vendor.

This script:
  1. Walks every news_sentiment row for REAL vendors that has a
     [leadership] or [lawsuit] prefix in notes.
  2. Asks Claude (via validator.classify_signal) what the row actually is.
  3. If the verdict matches the existing prefix -> leaves it.
     If the verdict is news/layoff/leadership/lawsuit -> rewrites the
     prefix to match.
     If the verdict is "unrelated" -> rewrites to [off-topic] so detail-view
     consumers can see what was filtered.

Skips Veridian Pay (is_demo_vendor) and confirmed event rows
(metric != news_sentiment).

Run:
    .venv/bin/python scripts/audit_signal_prefixes.py --dry-run
    .venv/bin/python scripts/audit_signal_prefixes.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.validator import classify_signal, get_default_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"

# Event-type prefixes that make false claims when wrong. (news/layoff are
# query-class tags but not event-type claims — out of scope.)
TARGET_PREFIXES = {"leadership", "lawsuit"}

PREFIX_RX = re.compile(r"^\[([A-Za-z_-]+)\]\s*(.*)$", re.DOTALL)


def parse_prefix(notes: str) -> tuple[str | None, str]:
    """Return (current_class_lower, title_remainder). (None, notes) if no prefix."""
    m = PREFIX_RX.match(notes or "")
    if not m:
        return None, (notes or "")
    return m.group(1).strip().lower(), m.group(2).strip()


def rewrite_notes(verdict_class: str, title: str) -> str:
    """Build the new notes string from a class verdict + title."""
    label = "off-topic" if verdict_class == "unrelated" else verdict_class
    return f"[{label}] {title}"[:255]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="show verdicts but do NOT update Airtable")
    args = ap.parse_args()

    print("Auditing [leadership] / [lawsuit] prefixes in news_sentiment notes")
    print(f"  scope: real vendors only (is_demo_vendor != true)")
    print(f"  target prefixes: {sorted(TARGET_PREFIXES)}")
    print(f"  mode: {'DRY RUN' if args.dry_run else 'LIVE — will update rows'}\n")

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    formula = "AND({metric}='news_sentiment', NOT({is_demo_vendor}))"
    records = table.all(formula=formula)
    print(f"Fetched {len(records)} news_sentiment rows for real vendors.\n")

    # Filter to those with target prefixes
    candidates: list[dict] = []
    prefix_counts: Counter = Counter()
    for rec in records:
        notes = rec["fields"].get("notes", "") or ""
        cur, title = parse_prefix(notes)
        if cur is None:
            continue
        prefix_counts[cur] += 1
        if cur in TARGET_PREFIXES:
            candidates.append({
                "id": rec["id"],
                "vendor": rec["fields"].get("vendor_name", "?"),
                "metric": rec["fields"].get("metric", "?"),
                "current_class": cur,
                "title": title,
                "notes_original": notes,
            })

    print(f"Prefix distribution across all news_sentiment rows:")
    for p, c in sorted(prefix_counts.items()):
        marker = "  <-- audit target" if p in TARGET_PREFIXES else ""
        print(f"  [{p}]: {c}{marker}")
    print(f"\nAudit candidates: {len(candidates)} rows\n")

    if not candidates:
        print("Nothing to audit.")
        return

    client = get_default_client()

    keep: list[dict] = []
    reclass: list[dict] = []      # prefix changes to a still-positive class
    off_topic: list[dict] = []    # prefix becomes [off-topic]
    parse_errors: list[dict] = []

    print(f"  {'#':<3} {'vendor':<11} {'was':<11} -> {'now':<11} "
          f"{'reason / title':<60}")
    print("  " + "-" * 110)
    for i, c in enumerate(candidates, 1):
        result = classify_signal(
            client,
            vendor=c["vendor"],
            current_class=c["current_class"],
            title=c["title"],
        )
        c["verdict_class"] = result.cls
        c["verdict_reason"] = result.reason

        new_class = result.cls
        if new_class == "parse_error":
            parse_errors.append(c)
        elif new_class == c["current_class"]:
            keep.append(c)
        elif new_class == "unrelated":
            off_topic.append(c)
        else:
            reclass.append(c)

        title_short = (c["title"][:55] + "...") if len(c["title"]) > 58 else c["title"]
        arrow_target = "off-topic" if new_class == "unrelated" else new_class
        verdict_label = (
            "KEEP" if new_class == c["current_class"]
            else "PARSE_ERR" if new_class == "parse_error"
            else arrow_target.upper()
        )
        print(f"  {i:<3} {c['vendor']:<11} [{c['current_class']:<9}] -> "
              f"[{arrow_target:<9}] {result.reason} | {title_short}")

    print()
    print(f"Summary: KEEP={len(keep)}  RECLASS={len(reclass)}  "
          f"OFF_TOPIC={len(off_topic)}  PARSE_ERROR={len(parse_errors)}")
    print()

    # Per-vendor breakdown
    print("Per-vendor verdict breakdown:")
    per_vendor: dict[str, Counter] = {}
    for c in candidates:
        v = c["vendor"]
        per_vendor.setdefault(v, Counter())[c["verdict_class"]] += 1
    for v in sorted(per_vendor):
        parts = ", ".join(f"{k}={n}" for k, n in sorted(per_vendor[v].items()))
        print(f"  {v:<12} {parts}")
    print()

    if reclass:
        print(f"--- {len(reclass)} RECLASSIFIED (prefix corrected) ---")
        for c in reclass:
            print(f"  [{c['vendor']}] [{c['current_class']}] -> "
                  f"[{c['verdict_class']}]: {c['title'][:80]}")
            print(f"      reason: {c['verdict_reason']}")
        print()

    if off_topic:
        print(f"--- {len(off_topic)} MARKED OFF-TOPIC ---")
        for c in off_topic:
            print(f"  [{c['vendor']}] [{c['current_class']}] -> [off-topic]: "
                  f"{c['title'][:80]}")
            print(f"      reason: {c['verdict_reason']}")
        print()

    if keep:
        print(f"--- {len(keep)} LEFT ALONE (prefix correct) ---")
        for c in keep:
            print(f"  [{c['vendor']}] [{c['current_class']}]: {c['title'][:80]}")
            print(f"      reason: {c['verdict_reason']}")
        print()

    if parse_errors:
        print(f"--- {len(parse_errors)} PARSE ERRORS (skipped) ---")
        for c in parse_errors:
            print(f"  [{c['vendor']}] [{c['current_class']}]: {c['title'][:80]}")
            print(f"      reason: {c['verdict_reason']}")
        print()

    if args.dry_run:
        print("(dry-run: not writing any updates)")
        return

    updates = reclass + off_topic
    if not updates:
        print("No prefix updates required.")
        return

    print(f"Updating {len(updates)} rows in Airtable ...")
    batch_payload = [
        {"id": c["id"], "fields": {"notes": rewrite_notes(c["verdict_class"], c["title"])}}
        for c in updates
    ]
    table.batch_update(batch_payload, typecast=True)
    print(f"Updated {len(batch_payload)} records.")


if __name__ == "__main__":
    main()
