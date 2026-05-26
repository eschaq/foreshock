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
from .summarizer import RiskSummary, summarize_alert, validate_citations

# Load env from backend/.env so this module works whether the FastAPI
# app or a script imports it.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AT_BASE = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
TABLE = "signals"


# Six vendors that appear on the dashboard. Ordered so critical/warning land
# first; the frontend can re-sort by score. Veridian flagged as demo so the UI
# can tag it transparently.
DASHBOARD_VENDORS: list[dict] = [
    {"name": "Veridian Pay", "type": "Payments/BaaS", "is_demo": True},
    {"name": "Twilio", "type": "Comms/2FA", "is_demo": False},
    {"name": "Stripe", "type": "Payments", "is_demo": False},
    {"name": "Plaid", "type": "Bank Data", "is_demo": False},
    {"name": "Snowflake", "type": "Data Infra", "is_demo": False},
    {"name": "AWS", "type": "Cloud Infra", "is_demo": False},
]


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
                "contribution": round(c.contribution, 1),
                "drivers": list(c.drivers),
            }
            for c in risk.components
        ],
    }


def all_vendors_overview() -> list[dict]:
    return [vendor_overview(v) for v in DASHBOARD_VENDORS]


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
    meta = next((v for v in DASHBOARD_VENDORS if v["name"] == name), None)
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
        return n
