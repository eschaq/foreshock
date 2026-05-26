"""
Alert trigger (Step 4 — the convergence detection layer).

Sits on top of scoring.score_vendor(). Reads a VendorRisk and decides
whether an alert should fire, what type ("convergence" vs single-metric),
and packages the evidence into a payload that step 5 (AI summary) and
step 6 (dashboard) will consume.

Hero alert = CONVERGENCE: multiple deteriorating signals at once.
The payload carries source_urls per converging signal so every claim
in the downstream AI summary remains tied to its source row
(CLAUDE.md Section 1 — the trust contract).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .scoring import (
    STABLE_MAX,
    WARNING_MAX,
    MetricDiff,
    SourceRef,
    VendorRisk,
)

# Minimum number of deteriorating signal dimensions to call it "convergence."
# Below this, a critical score is still alerted but tagged single_metric.
CONVERGENCE_MIN = 2


@dataclass
class ConvergenceSignal:
    """One deteriorating signal that contributed to the alert."""
    metric: str
    summary: str               # human-readable: "headcount -14.6% over 28d"
    latest_value: Any
    latest_date: str | None    # ISO date
    source_urls: list[str]     # for the trust contract (citations)
    evidence: list[dict]       # full SourceRef-as-dict list, for step 5


@dataclass
class Alert:
    vendor_name: str
    fired_at: str              # ISO timestamp (UTC)
    alert_type: str            # "convergence" | "single_metric"
    state: str                 # "critical" | "warning"
    score: float
    threshold: float           # the band crossed (60 for critical, 30 for warning)
    convergence_count: int
    signals: list[ConvergenceSignal]
    component_breakdown: list[dict]   # name, score, weight, contribution, drivers
    headline: str              # one-line demo-ready summary

    def to_dict(self) -> dict:
        return asdict(self)


def _describe_diff(d: MetricDiff) -> str:
    """One-line human summary of why this metric is deteriorating."""
    m = d.metric
    if m == "headcount_linkedin" and d.pct_trajectory is not None:
        days = (d.latest_date - d.oldest_date).days if (
            d.latest_date and d.oldest_date) else 0
        return (f"headcount {d.oldest_value} → {d.latest_value} "
                f"({d.pct_trajectory*100:+.1f}% over {days}d)")
    if m == "glassdoor_rating" and d.numeric_trajectory is not None:
        return (f"glassdoor {d.oldest_value} → {d.latest_value} "
                f"({d.numeric_trajectory:+.2f})")
    if m == "leadership_change":
        return f"{d.event_count_window} leadership event(s): " + \
               "; ".join(d.event_values)
    if m == "legal_event":
        return f"{d.event_count_window} legal event(s): " + \
               "; ".join(d.event_values)
    if m == "funding_event":
        return f"{d.event_count_window} funding event(s): " + \
               "; ".join(d.event_values)
    if m == "outage_incident":
        return f"{d.event_count_window} outage(s): " + \
               "; ".join(d.event_values)
    if m == "news_sentiment" and d.numeric_trajectory is not None:
        return (f"news sentiment avg {d.numeric_trajectory:+.2f} "
                f"(n={d.event_count_window})")
    if m == "sentiment_review" and d.numeric_trajectory is not None:
        return (f"review sentiment avg {d.numeric_trajectory:+.2f} "
                f"(n={d.event_count_window})")
    if m == "news_volume":
        return f"news_volume = {d.latest_value!r}"
    return f"{m}: {d.latest_value!r}"


def _convergence_signal(d: MetricDiff) -> ConvergenceSignal:
    urls = []
    seen = set()
    for s in d.sources:
        u = s.source_url
        if u and u not in seen:
            urls.append(u)
            seen.add(u)
    evidence = [
        {
            "capture_date": (s.capture_date.isoformat()
                             if s.capture_date else None),
            "value": s.value,
            "source_url": s.source_url,
            "notes": s.notes,
            "sentiment": s.sentiment,
        }
        for s in d.sources
    ]
    return ConvergenceSignal(
        metric=d.metric,
        summary=_describe_diff(d),
        latest_value=d.latest_value,
        latest_date=d.latest_date.isoformat() if d.latest_date else None,
        source_urls=urls,
        evidence=evidence,
    )


def _headline(vendor: str, alert_type: str, state: str, score: float,
              signals: list[ConvergenceSignal]) -> str:
    if alert_type == "convergence":
        metrics = ", ".join(s.metric for s in signals)
        return (f"CONVERGENCE on {vendor}: {len(signals)} signals crossing "
                f"({metrics}) — score {score:.1f} {state.upper()}")
    if signals:
        return (f"{state.upper()} on {vendor}: {signals[0].metric} "
                f"— score {score:.1f}")
    return f"{state.upper()} on {vendor}: score {score:.1f}"


def evaluate_alert(risk: VendorRisk) -> Alert | None:
    """
    Decide whether `risk` warrants an alert. Returns None if stable.

    - state == "critical"  -> alert fires
    - state == "warning"   -> alert fires only if it's a convergence
                              (multi-signal warnings = early foreshock)
    - state == "stable"    -> no alert (return None)
    """
    if risk.state == "stable":
        return None

    deteriorating = [d for d in risk.diffs.values() if d.deteriorating]
    deteriorating.sort(
        key=lambda d: (d.latest_date or None, d.metric),
        reverse=True,
    )
    signals = [_convergence_signal(d) for d in deteriorating]

    is_convergence = len(signals) >= CONVERGENCE_MIN

    # Warning band only fires if it's a convergence — avoids noisy
    # single-metric warnings (a single mixed-sentiment day shouldn't page anyone).
    if risk.state == "warning" and not is_convergence:
        return None

    alert_type = "convergence" if is_convergence else "single_metric"
    threshold = WARNING_MAX if risk.state == "critical" else STABLE_MAX

    component_breakdown = [
        {
            "name": c.name,
            "score": c.score,
            "weight": c.weight,
            "contribution": c.contribution,
            "drivers": list(c.drivers),
        }
        for c in risk.components
    ]

    return Alert(
        vendor_name=risk.vendor_name,
        fired_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        alert_type=alert_type,
        state=risk.state,
        score=risk.total_score,
        threshold=float(threshold),
        convergence_count=risk.convergence_count,
        signals=signals,
        component_breakdown=component_breakdown,
        headline=_headline(risk.vendor_name, alert_type, risk.state,
                           risk.total_score, signals),
    )
