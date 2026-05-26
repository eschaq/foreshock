"""
Step 4 smoke test: alert trigger against live Airtable data.

Runs scoring.score_vendor() then alerts.evaluate_alert() on Veridian Pay
and Stripe. Expected:
    Veridian Pay -> CONVERGENCE alert (5 signals, score >=60)
    Stripe       -> no alert (stable)

Run:  .venv/bin/python scripts/test_alerts.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.alerts import Alert, evaluate_alert
from foreshock.scoring import fetch_signals_for_vendor, score_vendor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]
TABLE = "signals"

VENDORS = ["Veridian Pay", "Stripe"]


def banner(text: str, char: str = "=") -> None:
    print()
    print(char * 80)
    print(text)
    print(char * 80)


def print_alert(alert: Alert) -> None:
    print(f"HEADLINE: {alert.headline}\n")
    print(f"fired_at        : {alert.fired_at}")
    print(f"alert_type      : {alert.alert_type}")
    print(f"state           : {alert.state}")
    print(f"score           : {alert.score}  (threshold {alert.threshold})")
    print(f"convergence_cnt : {alert.convergence_count}")
    print(f"# signals       : {len(alert.signals)}\n")

    print("Converging signals (the trust contract — each with source_urls):")
    for i, s in enumerate(alert.signals, 1):
        print(f"  [{i}] {s.metric}")
        print(f"      summary   : {s.summary}")
        print(f"      latest    : {s.latest_value!r} @ {s.latest_date}")
        if s.source_urls:
            print(f"      sources   : {len(s.source_urls)} url(s)")
            for u in s.source_urls[:3]:
                print(f"                  - {u}")
            if len(s.source_urls) > 3:
                print(f"                  ... +{len(s.source_urls)-3} more")
        else:
            print(f"      sources   : (none — synthetic event)")
        if s.evidence:
            first = s.evidence[0]
            note = first.get("notes") or ""
            if note:
                print(f"      first note: {note[:80]}")
    print()


def main() -> None:
    print("Step 4: alert trigger smoke test")
    print(f"Base: {AT_BASE}  Table: {TABLE}")

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)

    results: dict[str, Alert | None] = {}
    for vendor in VENDORS:
        banner(f"VENDOR: {vendor}")
        signals = fetch_signals_for_vendor(table, vendor)
        risk = score_vendor(vendor, signals)
        print(f"score={risk.total_score} state={risk.state.upper()} "
              f"convergence={risk.convergence_count}\n")

        alert = evaluate_alert(risk)
        results[vendor] = alert
        if alert is None:
            print("(no alert — vendor is stable)")
        else:
            print_alert(alert)

    banner("FULL VERIDIAN ALERT PAYLOAD (JSON, for step 5 + 6)", char="#")
    ver = results["Veridian Pay"]
    if ver:
        print(json.dumps(ver.to_dict(), indent=2, default=str))

    banner("VERDICT", char="#")
    ok = True
    if results["Veridian Pay"] is None:
        print("FAIL: Veridian Pay should have fired an alert"); ok = False
    elif results["Veridian Pay"].alert_type != "convergence":
        print(f"FAIL: Veridian alert_type should be 'convergence', "
              f"got {results['Veridian Pay'].alert_type}"); ok = False
    if results["Stripe"] is not None:
        print(f"FAIL: Stripe should not fire an alert, got "
              f"{results['Stripe'].alert_type}"); ok = False
    if ok:
        print("PASS: Veridian fired CONVERGENCE alert; Stripe stayed silent")


if __name__ == "__main__":
    main()
