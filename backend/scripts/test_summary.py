"""
Step 5 smoke test: AI risk summary on Veridian (critical) + Stripe (warning).

Pipeline: fetch signals -> score -> evaluate_alert -> summarize_alert.
The summarizer takes the SCORED DIFF SUMMARY (no raw rows) and produces
a sourced GRC narrative. We then run the citation auditor to confirm
every [N] in the narrative resolves to a real source_url.

Run:  .venv/bin/python scripts/test_summary.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from pyairtable import Api

from foreshock.alerts import evaluate_alert
from foreshock.scoring import fetch_signals_for_vendor, score_vendor
from foreshock.summarizer import (
    RiskSummary,
    summarize_alert,
    validate_citations,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ["AIRTABLE_API_KEY"]
AT_BASE = os.environ["AIRTABLE_BASE_ID"].split("/")[0]


def banner(text: str, char: str = "=") -> None:
    print()
    print(char * 84)
    print(text)
    print(char * 84)


def vendor_type_from_signals(signals: list[dict]) -> str:
    for s in signals:
        vt = s.get("vendor_type")
        if vt:
            return vt
    return ""


def print_summary(summary: RiskSummary) -> None:
    print(f"VENDOR     : {summary.vendor_name}")
    print(f"STATE      : {summary.state.upper()}   score={summary.score}   "
          f"alert_type={summary.alert_type}")
    print(f"GENERATED  : {summary.generated_by}")
    if summary.parse_error:
        print(f"FALLBACK   : {summary.parse_error}")
    print()
    print("HEADLINE:")
    print(f"  {summary.headline}")
    print()
    print("SENTIMENT READ (Claude's own — heuristic was placeholder):")
    print(f"  {summary.sentiment_read}")
    print()
    print("NARRATIVE:")
    for para in summary.narrative.split("\n\n"):
        print(f"  {para}")
        print()
    print("RECOMMENDED ACTION:")
    print(f"  {summary.recommended_action}")


def print_sources(summary: RiskSummary) -> None:
    print()
    print(f"SOURCES ({len(summary.citations)} citations):")
    for c in summary.citations:
        print(f"  [{c.n}]  metric={c.metric}  date={c.capture_date}")
        print(f"        url:    {c.source_url}")
        if c.snippet:
            print(f"        note:   {c.snippet[:100]}")


def print_audit(summary: RiskSummary) -> None:
    audit = validate_citations(summary)
    print()
    print("TRUST-CONTRACT AUDIT:")
    print(f"  cited indices    : {sorted(audit.cited_ns)}")
    print(f"  available indices: {sorted(audit.valid_ns)}")
    print(f"  invalid (hallucinated) cites: "
          f"{audit.invalid_ns if audit.invalid_ns else 'NONE'}")
    print(f"  uncited (unused) sources    : {audit.uncited_ns}")
    print(f"  per-field citation density  : {audit.citation_density}")
    if audit.all_claims_sourced:
        print(f"  >>> PASS: every [N] in the narrative resolves to a real source.")
    else:
        print(f"  >>> FAIL: {len(audit.invalid_ns)} citation(s) don't resolve.")


def run(vendor: str, table) -> None:
    signals = fetch_signals_for_vendor(table, vendor)
    print(f"Loaded {len(signals)} signal rows for {vendor}.")

    risk = score_vendor(vendor, signals)
    print(f"Risk: {risk.total_score} {risk.state.upper()}  "
          f"convergence={risk.convergence_count}")

    alert = evaluate_alert(risk)
    if alert is None:
        print(f"(no alert fired — vendor is stable; skipping summary)")
        return

    print(f"Alert: {alert.alert_type} with {len(alert.signals)} signals.\n")

    vt = vendor_type_from_signals(signals)
    summary = summarize_alert(alert, vendor_type=vt)

    print_summary(summary)
    print_sources(summary)
    print_audit(summary)


def main() -> None:
    api = Api(AT_KEY)
    table = api.table(AT_BASE, "signals")

    banner("VERIDIAN PAY (critical — converged staged signals)", char="=")
    run("Veridian Pay", table)

    banner("STRIPE (warning — recently-promoted real CTO departure)", char="=")
    run("Stripe", table)


if __name__ == "__main__":
    main()
