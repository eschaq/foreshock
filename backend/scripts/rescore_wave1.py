"""
Wave 1 re-score: apply new scoring logic to all 6 vendors, report
deltas against the pre-Wave-1 baseline, flag any state changes.

Baseline values come from SPEC.md (current scoreboard pre-Wave-1).

Run:  .venv/bin/python scripts/rescore_wave1.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.scoring import fetch_signals_for_vendor, score_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"

# Pre-Wave-1 baseline: scores from pre-Wave-1 code applied to CURRENT
# Airtable data (captured 2026-05-27 via `git stash` round-trip). This
# isolates Wave 1 impact from data drift since SPEC.md was last updated.
BASELINE = {
    "Veridian Pay": {"score": 68.2, "state": "critical", "conv": 6},
    "Twilio":       {"score": 46.3, "state": "warning",  "conv": 3},
    "Stripe":       {"score": 31.3, "state": "warning",  "conv": 2},
    "Plaid":        {"score": 37.3, "state": "warning",  "conv": 4},
    "Snowflake":    {"score": 43.3, "state": "warning",  "conv": 4},
    "AWS":          {"score": 28.3, "state": "stable",   "conv": 3},
}


def main() -> None:
    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    print(f"{'vendor':<14} {'old':>6} {'new':>6} {'delta':>7} "
          f"{'old_state':<10} {'new_state':<10} {'state Δ':<10} "
          f"{'old_conv':>4} {'new_conv':>4}")
    print("-" * 86)

    state_changes: list[str] = []
    component_diffs: list[tuple[str, list[tuple[str, float]]]] = []

    for vendor, base in BASELINE.items():
        signals = fetch_signals_for_vendor(table, vendor)
        risk = score_vendor(vendor, signals)
        delta = risk.total_score - base["score"]
        state_marker = "→ CHANGED" if risk.state != base["state"] else ""
        if state_marker:
            state_changes.append(
                f"{vendor}: {base['state']} → {risk.state} "
                f"(score {base['score']} → {risk.total_score})"
            )

        print(f"{vendor:<14} {base['score']:>6.1f} {risk.total_score:>6.1f} "
              f"{delta:>+7.2f} {base['state']:<10} {risk.state:<10} "
              f"{state_marker:<8} {base['conv']:>4d} {risk.convergence_count:>4d}")

        # Track per-component scores so we can explain the delta.
        component_diffs.append(
            (vendor, [(c.name, c.score, c.contribution, c.drivers) for c in risk.components])
        )

    print()
    print("State changes:")
    if state_changes:
        for ch in state_changes:
            print(f"  ⚠ {ch}")
    else:
        print("  (none)")

    print()
    print("Per-vendor component breakdown (new scores):")
    for vendor, comps in component_diffs:
        print(f"\n  {vendor}")
        for name, score, contrib, drivers in comps:
            d = "; ".join(drivers) if drivers else "—"
            print(f"    {name:<12} score={score:>5.1f} contrib={contrib:>5.2f}  {d}")


if __name__ == "__main__":
    main()
