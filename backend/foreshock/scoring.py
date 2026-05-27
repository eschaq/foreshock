"""
CDC diff + risk scoring (Step 3 — the detection core).

Reads Type 2 signal rows from Airtable, computes per-metric deltas
between the latest capture and prior state, then rolls those deltas
into a weighted 0-100 risk score per vendor.

Weights (CLAUDE.md Section 4):
    leadership stability + legal events  = sharpest failure signals (highest)
    headcount trajectory + sentiment     = trend amplifiers

State bands:   <30 stable   30-60 warning   >=60 critical
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# Metrics whose value is an EVENT (a thing that happened). Presence of a
# row = 1 event. Value is typically free-text ("CTO departure").
EVENT_METRICS = {
    "leadership_change",
    "legal_event",
    "funding_event",
    "outage_incident",
}

# Metrics whose value is a NUMBER (or numeric-string).
NUMERIC_METRICS = {
    "headcount_linkedin",
    "open_roles",
    "glassdoor_rating",
}

# Metrics whose value is a SENTIMENT LABEL (positive/neutral/negative)
# OR a numeric sentiment score (-1/0/+1). Handle both shapes.
SENTIMENT_METRICS = {
    "news_sentiment",
    "sentiment_review",
}

# Per-article news_sentiment rows are aggregated; news_volume is sometimes
# numeric ("10") and sometimes a label ("high", "layoff news").
VOLUME_METRICS = {"news_volume"}

SENTIMENT_LABEL_TO_NUM = {
    "positive": 1.0,
    "neutral": 0.0,
    "negative": -1.0,
}

VOLUME_LABEL_TO_NUM = {
    "low": 0.0,
    "normal": 1.0,
    "high": 2.0,
    "layoff news": 3.0,  # explicit demo label = escalated
}


def _to_float(v: Any) -> float | None:
    """Try to parse a value as float; return None if not numeric."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# CDC diff
# ---------------------------------------------------------------------------

@dataclass
class SourceRef:
    """One in-window evidence row — feeds the trust contract."""
    capture_date: date | None
    value: Any
    source_url: str
    notes: str
    sentiment: str


@dataclass
class MetricDiff:
    """Per-metric snapshot of change over the observation window."""
    metric: str
    latest_value: Any
    latest_date: date | None
    prior_value: Any = None
    prior_date: date | None = None
    oldest_value: Any = None        # for trend metrics (window start)
    oldest_date: date | None = None
    numeric_delta: float | None = None       # latest - prior (numeric)
    numeric_trajectory: float | None = None  # latest - oldest (numeric)
    pct_trajectory: float | None = None      # (latest - oldest) / oldest
    event_count_window: int = 0      # event rows seen in window
    event_values: list[str] = field(default_factory=list)
    n_observations: int = 0
    deteriorating: bool = False      # signal moved in a bad direction
    sources: list[SourceRef] = field(default_factory=list)  # in-window evidence


# Default trend window. 60d catches a full staged arc even when the latest
# observation is itself a few days old; the alert layer (step 4) can tighten
# this for the "what changed since last check" CDC slice.
DEFAULT_WINDOW_DAYS = 60


def build_diff(
    signals: list[dict],
    window_days: int = DEFAULT_WINDOW_DAYS,
    as_of: date | None = None,
) -> dict[str, MetricDiff]:
    """
    Compute per-metric diff for a single vendor.

    `signals` = list of Airtable row `fields` dicts for ONE vendor.
    Returns: {metric_name: MetricDiff}
    """
    as_of = as_of or date.today()
    cutoff = as_of - timedelta(days=window_days)

    # Group rows by metric, sorted ascending by capture_date.
    by_metric: dict[str, list[dict]] = {}
    for row in signals:
        m = row.get("metric")
        if not m:
            continue
        d = _parse_date(row.get("capture_date"))
        if d is None:
            continue
        row = {**row, "_date": d}
        by_metric.setdefault(m, []).append(row)

    diffs: dict[str, MetricDiff] = {}

    for metric, rows in by_metric.items():
        rows.sort(key=lambda r: r["_date"])
        in_window = [r for r in rows if r["_date"] >= cutoff]
        if not rows:
            continue

        latest = rows[-1]
        prior = rows[-2] if len(rows) >= 2 else None
        oldest_in_window = in_window[0] if in_window else rows[0]

        sources = [
            SourceRef(
                capture_date=r["_date"],
                value=r.get("value"),
                source_url=(r.get("source_url") or "").strip(),
                notes=(r.get("notes") or "").strip(),
                sentiment=(r.get("sentiment") or "").strip(),
            )
            for r in in_window
            if r.get("source_url") or r.get("notes")
        ]

        diff = MetricDiff(
            metric=metric,
            latest_value=latest.get("value"),
            latest_date=latest["_date"],
            prior_value=prior.get("value") if prior else None,
            prior_date=prior["_date"] if prior else None,
            oldest_value=oldest_in_window.get("value"),
            oldest_date=oldest_in_window["_date"],
            n_observations=len(rows),
            sources=sources,
        )

        # Numeric metrics — compute deltas + trajectory.
        if metric in NUMERIC_METRICS:
            lv = _to_float(latest.get("value"))
            pv = _to_float(prior.get("value")) if prior else None
            ov = _to_float(oldest_in_window.get("value"))
            if lv is not None and pv is not None:
                diff.numeric_delta = lv - pv
            if lv is not None and ov is not None:
                diff.numeric_trajectory = lv - ov
                if ov != 0:
                    diff.pct_trajectory = (lv - ov) / ov
            # Direction depends on the metric. Headcount/glassdoor: down = bad.
            # open_roles: stagnation isn't directly diagnostic — skip.
            if metric == "headcount_linkedin" and diff.pct_trajectory is not None:
                diff.deteriorating = diff.pct_trajectory <= -0.02   # >=2% loss
            elif metric == "glassdoor_rating" and diff.numeric_trajectory is not None:
                diff.deteriorating = diff.numeric_trajectory <= -0.2  # >=0.2 drop
            elif metric == "open_roles" and diff.pct_trajectory is not None:
                # Hiring contraction is the signal; flag a meaningful drop only
                # (5% week-over-week is noise floor; require 10%+ over window).
                diff.deteriorating = diff.pct_trajectory <= -0.10

        # Sentiment metrics — collapse to numeric scale, average over window.
        elif metric in SENTIMENT_METRICS:
            scores = []
            for r in in_window:
                v = r.get("value")
                num = _to_float(v)
                if num is not None:
                    scores.append(num)
                else:
                    label = (v or "").strip().lower()
                    if label in SENTIMENT_LABEL_TO_NUM:
                        scores.append(SENTIMENT_LABEL_TO_NUM[label])
                    else:
                        sent = (r.get("sentiment") or "").strip().lower()
                        if sent in SENTIMENT_LABEL_TO_NUM:
                            scores.append(SENTIMENT_LABEL_TO_NUM[sent])
            if scores:
                avg = sum(scores) / len(scores)
                diff.numeric_trajectory = avg          # store avg here
                diff.event_count_window = len(scores)  # n datapoints
                diff.deteriorating = avg <= -0.2

        # Volume metrics — labels OR counts.
        elif metric in VOLUME_METRICS:
            v = latest.get("value")
            num = _to_float(v)
            if num is not None:
                diff.numeric_trajectory = num
                # >=8 organic hits = elevated volume; >=15 = high
                diff.deteriorating = num >= 8
            else:
                label = (v or "").strip().lower()
                score = VOLUME_LABEL_TO_NUM.get(label, 0.0)
                diff.numeric_trajectory = score
                diff.deteriorating = score >= 2

        # Event metrics — count events in window, capture descriptions.
        elif metric in EVENT_METRICS:
            diff.event_count_window = len(in_window)
            diff.event_values = [
                str(r.get("value") or "").strip() for r in in_window
                if r.get("value")
            ]
            diff.deteriorating = diff.event_count_window > 0

        diffs[metric] = diff

    return diffs


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

WEIGHTS = {
    "leadership": 0.30,   # sharpest failure signal
    "legal":      0.25,   # sharpest failure signal
    "headcount":  0.17,   # concrete workforce data (was 0.20; ceded 0.03 to its leading-indicator sibling open_roles)
    "sentiment":  0.15,   # trend amplifier
    "open_roles": 0.06,   # leading workforce indicator: hiring contraction precedes layoffs
    "news_vol":   0.07,   # noisiest dimension (was 0.10; ceded 0.03 to open_roles)
}
# Sum = 1.00. leadership + legal stay highest per CLAUDE.md §4. open_roles is
# seated thematically next to headcount: hiring freezes precede layoffs. The
# 0.06 weight is light enough that open_roles dormancy or noisy data doesn't
# destabilize the gradation but meaningful enough to register a real freeze.

STABLE_MAX = 30
WARNING_MAX = 60   # >=60 = critical


@dataclass
class ComponentScore:
    name: str
    score: float        # 0-100
    weight: float
    contribution: float  # score * weight (0-100 scale, summed = total)
    drivers: list[str] = field(default_factory=list)


@dataclass
class VendorRisk:
    vendor_name: str
    total_score: float
    state: str          # stable | warning | critical
    convergence_count: int   # # of deteriorating signal dimensions
    components: list[ComponentScore]
    diffs: dict[str, MetricDiff]


def _leadership_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    d = diffs.get("leadership_change")
    score = 0.0
    drivers: list[str] = []
    if d and d.event_count_window > 0:
        # Per-event penalty, with C-suite bonus.
        for ev in d.event_values:
            base = 35
            low = ev.lower()
            if any(t in low for t in ("ceo", "cto", "cfo", "coo", "cio", "chief")):
                base = 55
                drivers.append(f"C-suite departure: {ev}")
            else:
                drivers.append(f"leadership event: {ev}")
            score += base
        score = min(score, 100.0)
    return ComponentScore("leadership", score, WEIGHTS["leadership"],
                          score * WEIGHTS["leadership"], drivers)


def _legal_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    d = diffs.get("legal_event")
    score = 0.0
    drivers: list[str] = []
    if d and d.event_count_window > 0:
        score = min(100.0, 40.0 * d.event_count_window)
        for ev in d.event_values:
            drivers.append(f"legal event: {ev}")
    return ComponentScore("legal", score, WEIGHTS["legal"],
                          score * WEIGHTS["legal"], drivers)


def _headcount_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    d = diffs.get("headcount_linkedin")
    score = 0.0
    drivers: list[str] = []
    if d and d.pct_trajectory is not None:
        pct = d.pct_trajectory  # e.g. -0.146 = -14.6%
        if pct < 0:
            # 0% -> 0pts, -5% -> 50pts, -10%+ -> 100pts (linear, capped).
            score = min(100.0, (-pct) * 1000.0)
            drivers.append(
                f"headcount {d.oldest_value} -> {d.latest_value} "
                f"({pct*100:+.1f}% over {(d.latest_date - d.oldest_date).days}d)"
            )
    return ComponentScore("headcount", score, WEIGHTS["headcount"],
                          score * WEIGHTS["headcount"], drivers)


def _open_roles_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    """
    Leading-indicator workforce signal. Hiring freezes precede layoffs —
    a sustained drop in open roles is the early foreshock to headcount
    contraction. Stepped bands by contraction depth; upward swings score 0
    (noisy — could be expansion, restructuring, backfill). A single
    observation (no trajectory yet) scores 0.
    """
    d = diffs.get("open_roles")
    score = 0.0
    drivers: list[str] = []
    if d and d.pct_trajectory is not None and d.pct_trajectory < 0:
        pct = d.pct_trajectory
        if pct <= -0.50:
            score, band = 100.0, "hiring freeze (-50% or worse)"
        elif pct <= -0.30:
            score, band = 75.0, "significant contraction (-30% to -49%)"
        elif pct <= -0.10:
            score, band = 50.0, "deteriorating (-10% to -29%)"
        else:
            score, band = 20.0, "minor signal (0% to -9%)"
        drivers.append(
            f"open_roles {d.oldest_value} -> {d.latest_value} "
            f"({pct*100:+.1f}%) — {band}"
        )
    return ComponentScore("open_roles", score, WEIGHTS["open_roles"],
                          score * WEIGHTS["open_roles"], drivers)


def _sentiment_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    """Combine news_sentiment + sentiment_review + glassdoor_rating drop."""
    parts: list[tuple[float, str]] = []

    for m in ("news_sentiment", "sentiment_review"):
        d = diffs.get(m)
        if d and d.numeric_trajectory is not None and d.event_count_window > 0:
            avg = d.numeric_trajectory
            # avg in [-1, +1]: -1 -> 100, 0 -> 50, +1 -> 0
            s = max(0.0, min(100.0, (1.0 - (avg + 1) / 2) * 100.0))
            parts.append((s, f"{m} avg={avg:+.2f} (n={d.event_count_window})"))

    d = diffs.get("glassdoor_rating")
    if d and d.numeric_trajectory is not None and d.numeric_trajectory < 0:
        drop = -d.numeric_trajectory   # positive number
        s = min(100.0, drop * 150.0)   # 0.2 drop -> 30, 0.5 -> 75, >=0.67 -> 100
        parts.append((s, f"glassdoor {d.oldest_value} -> {d.latest_value} "
                         f"(-{drop:.2f})"))

    if not parts:
        return ComponentScore("sentiment", 0.0, WEIGHTS["sentiment"], 0.0, [])

    score = sum(s for s, _ in parts) / len(parts)
    drivers = [text for _, text in parts]
    return ComponentScore("sentiment", score, WEIGHTS["sentiment"],
                          score * WEIGHTS["sentiment"], drivers)


def _news_volume_component(diffs: dict[str, MetricDiff]) -> ComponentScore:
    """
    Volume scoring with explicit label/count discrimination.

    Bug being fixed: a label value ("layoff news") used to map to 99 via
    VOLUME_LABEL_TO_NUM*33, while a numeric count of 8 mapped to only 30.
    A label and a small count carry equivalent epistemic weight; the
    label form just inflated.

    New policy:
      value_type=count   -> score normally per (count-5)*10 rubric
      value_type=label   -> 1) try to extract an embedded number; if found,
                              treat as a count
                            2) otherwise cap at 20 (low-confidence)
    """
    d = diffs.get("news_volume")
    score = 0.0
    drivers: list[str] = []
    if d is not None:
        latest_raw = str(d.latest_value or "").strip()
        clean_num = _to_float(d.latest_value)
        if clean_num is not None:
            # value_type=count
            score = max(0.0, min(100.0, (clean_num - 5) * 10.0))
            if score > 0:
                drivers.append(
                    f"news_volume count={int(clean_num)} "
                    f"(value_type=count)"
                )
        elif latest_raw:
            # value_type=label
            embedded = re.search(r"\d+", latest_raw)
            if embedded:
                extracted = float(embedded.group())
                score = max(0.0, min(100.0, (extracted - 5) * 10.0))
                if score > 0:
                    drivers.append(
                        f"news_volume='{latest_raw}' "
                        f"(value_type=label, parsed count={int(extracted)})"
                    )
            else:
                # Pure label: proportional 0..3 scale capped at 20.
                label_score = VOLUME_LABEL_TO_NUM.get(latest_raw.lower(), 0.0)
                score = min(20.0, label_score * (20.0 / 3.0))
                if score > 0:
                    drivers.append(
                        f"news_volume='{latest_raw}' "
                        f"(value_type=label, low-confidence cap=20)"
                    )
    # Also account for outage_incident here (low weight but routes home).
    d_out = diffs.get("outage_incident")
    if d_out and d_out.event_count_window > 0:
        bonus = min(40.0, 20.0 * d_out.event_count_window)
        score = min(100.0, score + bonus)
        for ev in d_out.event_values:
            drivers.append(f"outage: {ev}")
    return ComponentScore("news_vol", score, WEIGHTS["news_vol"],
                          score * WEIGHTS["news_vol"], drivers)


def score_vendor(vendor_name: str, signals: list[dict],
                 window_days: int = DEFAULT_WINDOW_DAYS) -> VendorRisk:
    diffs = build_diff(signals, window_days=window_days)

    components = [
        _leadership_component(diffs),
        _legal_component(diffs),
        _headcount_component(diffs),
        _open_roles_component(diffs),
        _sentiment_component(diffs),
        _news_volume_component(diffs),
    ]
    total = sum(c.contribution for c in components)

    if total >= WARNING_MAX:
        state = "critical"
    elif total >= STABLE_MAX:
        state = "warning"
    else:
        state = "stable"

    # Convergence: how many independent signal types are deteriorating.
    convergence_signals = {
        "leadership_change", "legal_event", "headcount_linkedin",
        "open_roles", "glassdoor_rating", "news_sentiment",
        "sentiment_review", "news_volume", "outage_incident",
        "funding_event",
    }
    convergence_count = sum(
        1 for m, d in diffs.items()
        if m in convergence_signals and d.deteriorating
    )

    return VendorRisk(
        vendor_name=vendor_name,
        total_score=round(total, 1),
        state=state,
        convergence_count=convergence_count,
        components=components,
        diffs=diffs,
    )


# ---------------------------------------------------------------------------
# Airtable fetch helper
# ---------------------------------------------------------------------------

def fetch_signals_for_vendor(table, vendor_name: str) -> list[dict]:
    """Pull all signal rows for one vendor from a pyairtable Table."""
    formula = f"{{vendor_name}}='{vendor_name}'"
    return [r["fields"] for r in table.all(formula=formula)]
