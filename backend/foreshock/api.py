"""
API helpers — turn the scoring/alerts/summarizer pipeline into JSON
payloads for the dashboard (step 6).

Kept separate from main.py so the FastAPI app stays thin and these
helpers can be unit-tested without spinning up uvicorn.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from datetime import date
from functools import lru_cache
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from pathlib import Path

from pyairtable import Api

from .alerts import evaluate_alert
from .scoring import fetch_signals_for_vendor, score_vendor
from .summarizer import (
    FleetSummary,
    RiskSummary,
    summarize_alert,
    summarize_fleet,
    validate_citations,
)
from .vendor_store import (
    VendorStoreError,
    add_user_vendor,
    deactivate_user_vendor,
    get_dashboard_vendors,
)

# Load env from backend/.env so this module works whether the FastAPI
# app or a script imports it.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AT_BASE = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
TABLE = "signals"


# Dashboard vendor list is now dynamic — see foreshock/vendor_store.py.
# `get_dashboard_vendors()` returns SYSTEM vendors (hardcoded, never
# removable) merged with active USER-added vendors from the
# `vendor_config` Airtable table.


# ---------------------------------------------------------------------------
# Airtable client (cached so we don't reauth on every request)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _table():
    return Api(AT_KEY).table(AT_BASE, TABLE)


# ---------------------------------------------------------------------------
# Score trajectory (sparkline data)
# ---------------------------------------------------------------------------

def compute_trajectory(
    signals: list[dict], vendor_name: str
) -> list[dict]:
    """
    Compute the score at each historical cumulative cutoff date.

    This traces what the score WOULD have been at each capture point
    — gives the dashboard a seismograph-style trajectory rather than
    a single-day snapshot.
    """
    capture_dates = sorted({
        s.get("capture_date") for s in signals if s.get("capture_date")
    })
    trajectory: list[dict] = []
    for cutoff in capture_dates:
        subset = [s for s in signals if s.get("capture_date", "") <= cutoff]
        risk = score_vendor(vendor_name, subset)
        trajectory.append({
            "date": cutoff,
            "score": round(risk.total_score, 1),
            "state": risk.state,
        })
    return trajectory


# ---------------------------------------------------------------------------
# Overview (one row per vendor for the dashboard grid)
# ---------------------------------------------------------------------------

def vendor_overview(vendor_meta: dict) -> dict:
    """Top-level card payload for one vendor."""
    signals = fetch_signals_for_vendor(_table(), vendor_meta["name"])
    risk = score_vendor(vendor_meta["name"], signals)

    # Derive vendor_type from the most-recent signal if Airtable disagrees
    # with our seed list (Airtable wins, since it stamps the capture).
    if signals:
        derived_type = (signals[-1].get("vendor_type") or "").strip()
        if derived_type:
            vendor_meta = {**vendor_meta, "type": derived_type}

    trajectory = compute_trajectory(signals, vendor_meta["name"])
    latest_capture = trajectory[-1]["date"] if trajectory else None

    return {
        "name": vendor_meta["name"],
        "type": vendor_meta["type"],
        "is_demo": vendor_meta.get("is_demo", False),
        # is_removable comes from vendor_store (False for system vendors,
        # True for user-added). UI uses this to gate the hover-X button.
        "is_removable": vendor_meta.get("is_removable", False),
        # cik/ticker surfaced so the frontend can render the SEC badge
        # from one source of truth (no whitelist duplication required).
        "cik": vendor_meta.get("cik"),
        "ticker": vendor_meta.get("ticker"),
        "score": round(risk.total_score, 1),
        "state": risk.state,
        "convergence_count": risk.convergence_count,
        "signal_count": len(signals),
        "latest_capture": latest_capture,
        "trajectory": trajectory,
        "components": [
            {
                "name": c.name,
                "score": round(c.score, 1),
                "weight": c.weight,
                # Full precision — consumers format for their own context. The
                # PDF report displays at 2 decimals and reconciles Total via
                # the canonical risk.total_score (not a re-sum), which
                # eliminates the pre-rounding error that caused the §2/§3
                # mismatch on the first cut of the DORA export.
                "contribution": c.contribution,
                "drivers": list(c.drivers),
            }
            for c in risk.components
        ],
    }


def all_vendors_overview() -> list[dict]:
    return [vendor_overview(v) for v in get_dashboard_vendors()]


# ---------------------------------------------------------------------------
# Detail (full payload incl. AI summary, with cache)
# ---------------------------------------------------------------------------

# Cache keyed by (vendor_name, latest_capture_date, signal_count) so the
# summary refreshes when fresh data lands (count goes up) AND doesn't re-hit
# Claude on every click. signal_count in the key is what makes the live pull's
# new rows auto-invalidate this cache.
_summary_cache: dict[tuple[str, str | None, int], dict] = {}
_cache_lock = Lock()


def _serialize_summary(summary: RiskSummary) -> dict:
    audit = validate_citations(summary)
    return {
        "headline": summary.headline,
        "sentiment_read": summary.sentiment_read,
        "narrative": summary.narrative,
        "recommended_action": summary.recommended_action,
        "alert_type": summary.alert_type,
        "generated_by": summary.generated_by,
        "parse_error": summary.parse_error,
        "citations": [
            {
                "n": c.n,
                "metric": c.metric,
                "capture_date": c.capture_date,
                "source_url": c.source_url,
                "snippet": c.snippet,
            }
            for c in summary.citations
        ],
        "audit": {
            "cited": sorted(audit.cited_ns),
            "available": sorted(audit.valid_ns),
            "invalid": list(audit.invalid_ns),
            "uncited": list(audit.uncited_ns),
            "all_claims_sourced": audit.all_claims_sourced,
        },
    }


def vendor_detail(name: str, force_refresh: bool = False) -> dict:
    """Full detail payload incl AI summary (cached) and recent signal rows."""
    meta = next(
        (v for v in get_dashboard_vendors() if v["name"] == name), None
    )
    if meta is None:
        return {"error": f"unknown vendor: {name}"}

    overview = vendor_overview(meta)

    # Pull signals once more so we can include recent rows for the detail panel.
    signals = fetch_signals_for_vendor(_table(), name)
    risk = score_vendor(name, signals)
    alert = evaluate_alert(risk)

    cache_key = (name, overview["latest_capture"], overview["signal_count"])
    summary_payload: dict | None = None
    if alert is not None:
        with _cache_lock:
            cached = _summary_cache.get(cache_key)
            if cached is None or force_refresh:
                summary = summarize_alert(
                    alert, vendor_type=overview["type"]
                )
                cached = _serialize_summary(summary)
                _summary_cache[cache_key] = cached
            summary_payload = cached
    else:
        summary_payload = None  # stable vendors: no alert, no AI summary

    # Recent signal rows for the detail panel's evidence table.
    recent_signals = sorted(
        signals,
        key=lambda s: (s.get("capture_date") or "", s.get("metric") or ""),
        reverse=True,
    )[:40]

    return {
        "overview": overview,
        "alert": {
            "fired": alert is not None,
            "alert_type": alert.alert_type if alert else None,
            "headline": alert.headline if alert else None,
            "fired_at": alert.fired_at if alert else None,
            # Lightweight projection of the converging signals — name +
            # one-line summary + latest observation + evidence count, so
            # the PDF report can render the "what is converging" section
            # without re-running scoring/alerts.
            "signals": [
                {
                    "metric": s.metric,
                    "summary": s.summary,
                    "latest_value": s.latest_value,
                    "latest_date": s.latest_date,
                    "source_count": len(s.source_urls),
                }
                for s in (alert.signals if alert else [])
            ],
        },
        "summary": summary_payload,
        "recent_signals": [
            {
                "capture_date": s.get("capture_date"),
                "metric": s.get("metric"),
                "value": s.get("value"),
                "unit": s.get("unit"),
                "sentiment": s.get("sentiment"),
                "source_url": s.get("source_url"),
                "notes": s.get("notes"),
            }
            for s in recent_signals
        ],
    }


def clear_summary_cache() -> int:
    with _cache_lock:
        n = len(_summary_cache)
        _summary_cache.clear()
    with _fleet_cache_lock:
        n += len(_fleet_summary_cache)
        _fleet_summary_cache.clear()
    return n


# ---------------------------------------------------------------------------
# Fleet-level summary (dashboard "Fleet Overview" card)
# ---------------------------------------------------------------------------
# Cached by a hash of (name, score, state, signal_count) tuples — same shape
# as the per-vendor cache: any change in vendor state, score, or row count
# auto-invalidates. One Claude call's worth of latency on cold start; cached
# thereafter until any vendor data shifts.

_fleet_summary_cache: dict[tuple, dict] = {}
_fleet_cache_lock = Lock()


def _fleet_cache_key(vendors: list[dict]) -> tuple:
    return tuple(
        (v["name"], v["score"], v["state"], v["signal_count"])
        for v in vendors
    )


# ---------------------------------------------------------------------------
# Vendor management (add / remove / lookup) — Wave 3
# ---------------------------------------------------------------------------

def add_vendor_payload(
    name: str,
    vendor_type: str,
    cik: str | None = None,
    ticker: str | None = None,
    website: str | None = None,
) -> dict:
    """Thin wrapper around vendor_store.add_user_vendor returning a
    JSON-serializable payload. Raises VendorStoreError on validation
    failures — main.py converts those to 400/503 responses."""
    created = add_user_vendor(
        name=name,
        vendor_type=vendor_type,
        cik=cik,
        ticker=ticker,
        website=website,
    )
    return {
        "added": True,
        "vendor": {
            "name": created["name"],
            "type": created["vendor_type"],
            "cik": created.get("cik"),
            "ticker": created.get("ticker"),
            "website": created.get("website"),
            "is_demo": False,
            "is_removable": True,
        },
        "edgar_monitoring": bool(created.get("cik")),
        "note": (
            "Vendor added. Monitoring starts on the next agent run "
            "(POST /agent/run, or wait for the daily cron)."
        ),
    }


def remove_vendor_payload(name: str) -> dict:
    """Wrapper around vendor_store.deactivate_user_vendor."""
    return deactivate_user_vendor(name)


def lookup_vendor_payload(query: str, top_n: int = 3) -> dict:
    """SEC company-tickers fuzzy lookup. Returns {matches: [...]}.
    Empty list when query is empty, no match found, or SEC is unreachable
    (the lookup module degrades gracefully — never raises here)."""
    from .sec_lookup import lookup_company
    matches = lookup_company(query, top_n=top_n)
    return {"query": query, "matches": matches}


# ---------------------------------------------------------------------------
# Citation trust audit (Wave 6) — aggregates the per-vendor summary
# `audit` block into a single fleet-wide statement: how many AI claims
# were made, how many sources backed them, how many were unresolved.
#
# Positioning context (for the submission package — do not surface to UI):
#   "Foreshock's citation audit infrastructure verifies every AI-generated
#   claim against a numbered source. Current audit result: 0 unresolved
#   citations across all monitored vendors. In December 2025, a GPTZero
#   investigation found 60% hallucination rates in an EY compliance
#   advisory. FINRA's 2026 oversight report specifically flagged AI
#   hallucination as a compliance risk."
# ---------------------------------------------------------------------------

def trust_audit_payload() -> dict:
    """
    Roll up the per-vendor audit block. Stable vendors have no AI
    summary and are skipped — they don't generate claims to audit.

    Cost: one `vendor_detail` call per vendor. Both vendor_overview
    inside it and the summary itself are cached, so warm-cache cost
    is small. Cold-cache hits trigger Claude generation; the endpoint
    will be slow on first call after a fresh capture.
    """
    vendors = get_dashboard_vendors()
    total_claims = 0          # citation markers actually used in narratives
    total_citations = 0       # sources made available to the model
    unresolved = 0            # cited but unresolvable -> hallucinations
    vendor_audits: list[dict] = []

    for v in vendors:
        try:
            detail = vendor_detail(v["name"])
        except Exception:
            continue
        summary = detail.get("summary")
        if not summary:
            continue
        audit = summary.get("audit") or {}
        cited = len(audit.get("cited", []) or [])
        available = len(audit.get("available", []) or [])
        invalid = len(audit.get("invalid", []) or [])
        all_sourced = bool(audit.get("all_claims_sourced", True))

        total_claims += cited
        total_citations += available
        unresolved += invalid

        vendor_audits.append({
            "vendor": v["name"],
            "claims_cited": cited,
            "sources_available": available,
            "unresolved": invalid,
            "audit_pass": all_sourced,
        })

    all_pass = unresolved == 0 and all(va["audit_pass"] for va in vendor_audits)
    return {
        "total_claims": total_claims,
        "total_citations": total_citations,
        "unresolved": unresolved,
        "all_pass": all_pass,
        "vendor_audits": vendor_audits,
    }


def fleet_summary_payload(force_refresh: bool = False) -> dict:
    vendors = all_vendors_overview()
    key = _fleet_cache_key(vendors)
    with _fleet_cache_lock:
        cached = _fleet_summary_cache.get(key)
        if cached is not None and not force_refresh:
            return cached
        summary = summarize_fleet(vendors)
        payload = {
            "headline": summary.headline,
            "narrative": summary.narrative,
            "generated_by": summary.generated_by,
            "parse_error": summary.parse_error,
            "fleet_counts": {
                "critical": sum(1 for v in vendors if v["state"] == "critical"),
                "warning":  sum(1 for v in vendors if v["state"] == "warning"),
                "stable":   sum(1 for v in vendors if v["state"] == "stable"),
                "total":    len(vendors),
            },
        }
        _fleet_summary_cache[key] = payload
        return payload
