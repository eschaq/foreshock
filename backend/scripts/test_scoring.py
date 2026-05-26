"""
Step 3 smoke test: CDC diff + risk scoring against live Airtable data.

Pulls all signal rows for Veridian Pay (demo vendor, staged 30-day arc)
and Stripe (real 2026 data), runs the diff+scoring logic, and prints
the per-metric diffs + per-component scores + final state.

Expected at build time (per CLAUDE.md Section 5):
    Veridian Pay -> CRITICAL    (converging foreshocks)
    Stripe       -> STABLE      (healthy fintech, mixed news noise)

Run:  .venv/bin/python scripts/test_scoring.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

# Make `foreshock` package importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.scoring import (
    MetricDiff,
    VendorRisk,
    fetch_signals_for_vendor,
    score_vendor,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"

VENDORS = ["Veridian Pay", "Stripe"]


def _fmt_date(d: date | None) -> str:
    return d.isoformat() if d else "—"


def print_diff_table(diffs: dict[str, MetricDiff]) -> None:
    print(f"  {'metric':<22} {'latest':<22} {'prior':<22} "
          f"{'trajectory':<14} {'n':<3} {'deteriorating'}")
    print("  " + "-" * 110)
    for metric in sorted(diffs.keys()):
        d = diffs[metric]
        latest = f"{d.latest_value} @ {_fmt_date(d.latest_date)}"
        prior = (f"{d.prior_value} @ {_fmt_date(d.prior_date)}"
                 if d.prior_value is not None else "—")
        if d.pct_trajectory is not None:
            traj = f"{d.pct_trajectory*100:+.1f}%"
        elif d.numeric_trajectory is not None:
            traj = f"{d.numeric_trajectory:+.2f}"
        elif d.event_count_window:
            traj = f"{d.event_count_window} events"
        else:
            traj = "—"
        flag = "YES" if d.deteriorating else ""
        print(f"  {metric:<22} {latest:<22} {prior:<22} {traj:<14} "
              f"{d.n_observations:<3} {flag}")


def print_components(risk: VendorRisk) -> None:
    print(f"  {'component':<12} {'score':>6} {'weight':>7} "
          f"{'contrib':>8}  drivers")
    print("  " + "-" * 110)
    for c in risk.components:
        drivers = "; ".join(c.drivers) if c.drivers else "—"
        print(f"  {c.name:<12} {c.score:>6.1f} {c.weight:>7.2f} "
              f"{c.contribution:>8.2f}  {drivers}")
    print("  " + "-" * 110)
    print(f"  {'TOTAL':<12} {' ':>6} {' ':>7} {risk.total_score:>8.1f}  "
          f"(convergence_count = {risk.convergence_count})")


def banner(text: str, char: str = "=") -> None:
    print()
    print(char * 80)
    print(text)
    print(char * 80)


def main() -> None:
    print("Step 3: CDC diff + risk scoring smoke test")
    print(f"Base: {AT_BASE}  Table: {TABLE}\n")

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    results: list[VendorRisk] = []
    for vendor in VENDORS:
        banner(f"VENDOR: {vendor}")
        signals = fetch_signals_for_vendor(table, vendor)
        print(f"Fetched {len(signals)} signal rows.\n")

        risk = score_vendor(vendor, signals)
        results.append(risk)

        print("--- Per-metric diff ---")
        print_diff_table(risk.diffs)
        print()
        print("--- Component scores ---")
        print_components(risk)
        print()
        print(f">>> {vendor} STATE = {risk.state.upper()} "
              f"(score {risk.total_score})")

    banner("SUMMARY", char="#")
    for r in results:
        marker = {"critical": "[!!]", "warning": "[! ]", "stable": "[ok]"}[r.state]
        print(f"  {marker}  {r.vendor_name:<20} score={r.total_score:>5.1f}  "
              f"state={r.state.upper():<8}  convergence={r.convergence_count}")
    print()

    # Sanity assertions for the build-day target.
    by_name = {r.vendor_name: r for r in results}
    ok = True
    if by_name["Veridian Pay"].state != "critical":
        print("FAIL: Veridian Pay should be CRITICAL")
        ok = False
    if by_name["Stripe"].state != "stable":
        print("FAIL: Stripe should be STABLE "
              f"(got {by_name['Stripe'].state})")
        ok = False
    if ok:
        print("PASS: Veridian=critical, Stripe=stable")


if __name__ == "__main__":
    main()
