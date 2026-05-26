"""
CLI for the demo's live-pull moment (step 7).

Usage:
  .venv/bin/python scripts/run_live_pull.py --seeded                  # safety net
  .venv/bin/python scripts/run_live_pull.py --seeded --dry-run        # preview rows
  .venv/bin/python scripts/run_live_pull.py --live                    # genuine pull
  .venv/bin/python scripts/run_live_pull.py --live --save-seed        # genuine + capture fixture
  .venv/bin/python scripts/run_live_pull.py --reset                   # undo last run

The dashboard reflects the change on next refresh (no server restart needed —
the summary cache is keyed by signal_count so new rows auto-invalidate it).
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
from pyairtable import Api

from foreshock.alerts import evaluate_alert
from foreshock.live_pull import (
    LivePullResult,
    reset_live_pull_rows,
    run_live_pull,
)
from foreshock.scoring import fetch_signals_for_vendor, score_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]


def vendor_snapshot(table, name: str) -> dict:
    signals = fetch_signals_for_vendor(table, name)
    risk = score_vendor(name, signals)
    alert = evaluate_alert(risk)
    legal_count = sum(
        1 for s in signals if s.get("metric") == "legal_event"
    )
    leadership_count = sum(
        1 for s in signals if s.get("metric") == "leadership_change"
    )
    return {
        "score": risk.total_score,
        "state": risk.state,
        "convergence_count": risk.convergence_count,
        "signal_count": len(signals),
        "legal_event_count": legal_count,
        "leadership_change_count": leadership_count,
        "alert_fired": alert is not None,
        "components": {c.name: round(c.contribution, 1) for c in risk.components},
    }


def print_snapshot(label: str, snap: dict) -> None:
    print(f"  {label}")
    print(f"    score={snap['score']:>5.1f}  state={snap['state'].upper():<9} "
          f"convergence={snap['convergence_count']}  "
          f"signals={snap['signal_count']}  "
          f"alert={'FIRED' if snap['alert_fired'] else 'silent'}")
    comps = snap["components"]
    print(f"    components: leadership={comps.get('leadership', 0):.1f}  "
          f"legal={comps.get('legal', 0):.1f}  "
          f"headcount={comps.get('headcount', 0):.1f}  "
          f"sentiment={comps.get('sentiment', 0):.1f}  "
          f"news_vol={comps.get('news_vol', 0):.1f}")
    print(f"    event counts: legal_event={snap['legal_event_count']}  "
          f"leadership_change={snap['leadership_change_count']}")


def print_planned_rows(result: LivePullResult) -> None:
    print(f"  REAL-VENDOR ROWS ({len(result.real_vendor_rows)}):")
    for r in result.real_vendor_rows:
        print(f"    [{r['metric']}] {(r.get('value') or '')[:50]:<50} "
              f"url={(r.get('source_url') or '')[:60]}")
    print(f"  VERIDIAN FINALE ROWS ({len(result.veridian_rows)}):")
    for r in result.veridian_rows:
        print(f"    [{r['metric']}] {(r.get('value') or '')[:80]}")


def banner(text: str) -> None:
    print()
    print("=" * 84)
    print(text)
    print("=" * 84)


async def main_async(args) -> None:
    api = Api(AT_KEY)
    table = api.table(AT_BASE, "signals")

    if args.reset:
        banner("RESET — deleting rows tagged 'live-pull-beat:'")
        n = reset_live_pull_rows()
        print(f"Deleted {n} rows.")
        return

    mode = "live" if args.live else "seeded"
    banner(f"LIVE PULL  mode={mode}  "
           f"{'(dry-run)' if args.dry_run else ''}  "
           f"{'(save-seed)' if args.save_seed else ''}")

    # Snapshot BEFORE
    print("\nSnapshot BEFORE pull (Veridian + Stripe):")
    veridian_before = vendor_snapshot(table, "Veridian Pay")
    stripe_before = vendor_snapshot(table, "Stripe")
    print_snapshot("Veridian Pay", veridian_before)
    print()
    print_snapshot("Stripe", stripe_before)

    # Execute
    print(f"\nFetching real-vendor signal via {mode} path ...")
    result = await run_live_pull(
        mode=mode,
        write=not args.dry_run,
        save_seed=args.save_seed,
    )
    print(f"Mode: {result.mode}  capture_date={result.capture_date}  "
          f"rows_planned={result.total_rows}  "
          f"rows_written={len(result.rows_written_ids)}  "
          f"saved_seed={result.saved_seed}")

    print("\nPlanned rows:")
    print_planned_rows(result)

    if args.dry_run:
        print("\n(dry-run: not writing to Airtable, snapshot AFTER skipped)")
        return

    # Snapshot AFTER
    print("\nSnapshot AFTER pull (Veridian + Stripe):")
    veridian_after = vendor_snapshot(table, "Veridian Pay")
    stripe_after = vendor_snapshot(table, "Stripe")
    print_snapshot("Veridian Pay", veridian_after)
    print()
    print_snapshot("Stripe", stripe_after)

    # Diff summary
    banner("VERIDIAN DIFF")
    ver_d_score = veridian_after["score"] - veridian_before["score"]
    print(f"  score        {veridian_before['score']:.1f}  ->  "
          f"{veridian_after['score']:.1f}  (Δ {ver_d_score:+.1f})")
    print(f"  state        {veridian_before['state'].upper()}  ->  "
          f"{veridian_after['state'].upper()}")
    print(f"  convergence  {veridian_before['convergence_count']}  ->  "
          f"{veridian_after['convergence_count']}")
    print(f"  legal_event  {veridian_before['legal_event_count']}  ->  "
          f"{veridian_after['legal_event_count']}")
    print(f"  leadership   {veridian_before['leadership_change_count']}  ->  "
          f"{veridian_after['leadership_change_count']}")
    comp_diff = {
        k: round(
            veridian_after['components'].get(k, 0)
            - veridian_before['components'].get(k, 0), 1)
        for k in {*veridian_before['components'], *veridian_after['components']}
    }
    print(f"  component Δ: {comp_diff}")


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--live", action="store_true",
                       help="real Bright Data MCP call")
    group.add_argument("--seeded", action="store_true",
                       help="use cached fixture; zero network dependency")
    group.add_argument("--reset", action="store_true",
                       help="delete every row this script has written")
    ap.add_argument("--dry-run", action="store_true",
                    help="show planned rows without writing to Airtable")
    ap.add_argument("--save-seed", action="store_true",
                    help="with --live: overwrite the seeded fixture")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
