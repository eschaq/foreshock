"""
What-if analysis (NO Airtable writes).

Simulates promoting the audit-surfaced real-but-untagged events to actual
event rows in-memory, then re-runs scoring.score_vendor to show the
score / state / convergence impact.

  Scenario A: + Stripe CTO David Singleton departure  -> Stripe
  Scenario B: + Labaton class action + TCPA complaint -> Twilio
  Scenario C: both A and B

Run:  .venv/bin/python scripts/whatif_promote_events.py
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.scoring import VendorRisk, fetch_signals_for_vendor, score_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TODAY = date.today().isoformat()


def _stripe_promotion() -> list[dict]:
    return [{
        "capture_date": TODAY,
        "vendor_name": "Stripe",
        "vendor_type": "Payments",
        "is_demo_vendor": False,
        "metric": "leadership_change",
        "value": "Stripe CTO David Singleton to step down after seven years",
        "unit": "event",
        "source_url": "(simulated promotion — would inherit news_sentiment row's URL)",
        "sentiment": "negative",
        "notes": "promoted from validated [leadership] sentiment row",
    }]


def _twilio_promotion() -> list[dict]:
    return [
        {
            "capture_date": TODAY,
            "vendor_name": "Twilio",
            "vendor_type": "Comms/2FA",
            "is_demo_vendor": False,
            "metric": "legal_event",
            "value": "Labaton class action solicitation re: Twilio",
            "unit": "event",
            "source_url": "(simulated promotion)",
            "sentiment": "negative",
            "notes": "promoted from validated [lawsuit] sentiment row",
        },
        {
            "capture_date": TODAY,
            "vendor_name": "Twilio",
            "vendor_type": "Comms/2FA",
            "is_demo_vendor": False,
            "metric": "legal_event",
            "value": "New TCPA Complaint Claims OpenAI and Twilio are Liable",
            "unit": "event",
            "source_url": "(simulated promotion)",
            "sentiment": "negative",
            "notes": "promoted from validated [lawsuit] sentiment row",
        },
    ]


def _components_str(r: VendorRisk) -> str:
    parts = [f"{c.name}={c.contribution:.1f}" for c in r.components if c.contribution > 0]
    return ", ".join(parts) if parts else "—"


def _diff(baseline: VendorRisk, sim: VendorRisk, label: str) -> None:
    delta = sim.total_score - baseline.total_score
    state_change = (
        f"{baseline.state.upper()} -> {sim.state.upper()}"
        if baseline.state != sim.state
        else f"{baseline.state.upper()} (unchanged)"
    )
    conv_change = (
        f"{baseline.convergence_count} -> {sim.convergence_count}"
        if baseline.convergence_count != sim.convergence_count
        else f"{baseline.convergence_count} (unchanged)"
    )
    print(f"  {label}")
    print(f"    score        {baseline.total_score:>5.1f}  ->  {sim.total_score:>5.1f}  "
          f"(Δ {delta:+.1f})")
    print(f"    state        {state_change}")
    print(f"    convergence  {conv_change}")
    print(f"    components   {_components_str(sim)}")
    print()


def banner(text: str) -> None:
    print()
    print("=" * 76)
    print(text)
    print("=" * 76)


def main() -> None:
    api = Api(AT_KEY)
    table = api.table(AT_BASE, "signals")

    print(f"What-if simulation (capture_date for synthetic rows = {TODAY})")
    print("No Airtable writes — pure in-memory re-scoring.\n")

    stripe = fetch_signals_for_vendor(table, "Stripe")
    twilio = fetch_signals_for_vendor(table, "Twilio")

    base_s = score_vendor("Stripe", stripe)
    base_t = score_vendor("Twilio", twilio)

    banner("BASELINE  (current Airtable state)")
    for v, r in [("Stripe", base_s), ("Twilio", base_t)]:
        print(f"  {v:<8} score={r.total_score:>5.1f}  state={r.state.upper():<8}  "
              f"convergence={r.convergence_count}")
        print(f"           components: {_components_str(r)}")
    print()

    banner("SCENARIO A — promote Stripe CTO Singleton departure to leadership_change")
    sim_s_a = score_vendor("Stripe", stripe + _stripe_promotion())
    _diff(base_s, sim_s_a, "Stripe")

    banner("SCENARIO B — promote Labaton + TCPA Twilio lawsuits to legal_event")
    sim_t_b = score_vendor("Twilio", twilio + _twilio_promotion())
    _diff(base_t, sim_t_b, "Twilio")

    banner("SCENARIO C — both A and B")
    _diff(base_s, sim_s_a, "Stripe")
    _diff(base_t, sim_t_b, "Twilio")

    banner("SUMMARY")
    rows = [
        ("baseline",    base_s, base_t),
        ("Scenario A",  sim_s_a, base_t),
        ("Scenario B",  base_s,  sim_t_b),
        ("Scenario C",  sim_s_a, sim_t_b),
    ]
    print(f"  {'Scenario':<14} | {'Stripe score / state / conv':<32} | "
          f"{'Twilio score / state / conv':<32}")
    print("  " + "-" * 84)
    for label, s, t in rows:
        s_str = f"{s.total_score:>5.1f} {s.state.upper():<8} conv={s.convergence_count}"
        t_str = f"{t.total_score:>5.1f} {t.state.upper():<8} conv={t.convergence_count}"
        print(f"  {label:<14} | {s_str:<32} | {t_str:<32}")
    print()

    # Editorial line on the gradation story
    print("Reference bands: <30 stable | 30-60 warning | >=60 critical")


if __name__ == "__main__":
    main()
