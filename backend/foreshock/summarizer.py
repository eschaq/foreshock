"""
AI risk summary (Step 5 — synthesis with receipts).

Pipeline lands here:  scoring -> alerts -> THIS.

Consumes an `Alert` payload from `alerts.evaluate_alert()` — the SCORED
DIFF SUMMARY, not raw Airtable rows (CLAUDE.md Sec 2: "summary-only
pattern; never pass raw rows; pass scored diff summary") — and produces
a sourced GRC-analyst risk briefing.

Trust contract (CLAUDE.md Sec 1):
  Every factual claim in the narrative MUST cite [N] indices that resolve
  to real source_urls from the alert's evidence. `validate_citations()`
  flags any [N] that doesn't resolve.

Claude (Sonnet) owns SENTIMENT here — it forms its own read of the
evidence text rather than trusting the keyword-heuristic labels in row
data (those stay for scoring as a proxy).

Graceful degradation: with no ANTHROPIC_API_KEY (or any client failure),
returns a deterministic summary assembled from the structured signals.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from anthropic import Anthropic, APIError

from .alerts import Alert, ConvergenceSignal
from .validator import _strip_fences

# CLAUDE.md spec'd "Sonnet 4.5". Current latest in the Sonnet 4.x line is 4.6
# — we use it; same model already in use by validator.py.
MODEL = "claude-sonnet-4-6"

# How many evidence rows per signal to expose to Claude. Keeps the prompt
# focused and the citation list manageable for the dashboard.
MAX_EVIDENCE_PER_SIGNAL = 4


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Citation:
    n: int                  # 1-based citation index used in narrative as [N]
    metric: str             # which converging signal this citation belongs to
    capture_date: str | None
    source_url: str
    snippet: str            # short note for display in the dashboard's source list


@dataclass
class RiskSummary:
    vendor_name: str
    state: str              # critical | warning | stable
    score: float
    alert_type: str
    headline: str
    sentiment_read: str     # Claude's narrative sentiment (replaces heuristic)
    narrative: str          # 2-3 paragraphs, GRC voice, [N]-cited
    recommended_action: str # one paragraph, [N]-cited
    citations: list[Citation]
    generated_by: str       # model name OR "deterministic-fallback"
    parse_error: str = ""   # populated if Claude returned malformed JSON


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a GRC (Governance / Risk / Compliance) analyst at a mid-market fintech. You write tight, sourced vendor risk briefings that get filed into the third-party risk register that supports DORA (Digital Operational Resilience Act) compliance.

You follow these rules without exception:

1. CITATIONS ARE NOT OPTIONAL. Every factual claim is followed by [N] (or [N,M] for multi-source) where N references the SOURCES list provided. If you can't cite it, you don't write it. Never invent a source number — only use indices that appear in SOURCES.

2. YOU ARE THE SENTIMENT AUTHORITY. The evidence rows carry a "sentiment" hint that came from a keyword heuristic — treat it as a noisy prior, not a verdict. Read the article titles and notes and form your own judgment.

3. NO EXTRAPOLATION. If the evidence says "CTO is leaving," you don't add "this likely signals deeper instability" unless another cited row supports that. Stick to what's actually in the sources.

4. DORA REFERENCES. Mention DORA only when the signal genuinely warrants it — concentration on a critical ICT vendor, notification thresholds, exit-plan triggers. Don't sprinkle compliance jargon to look serious.

5. VOICE. GRC-analyst: clear, decisive, businesslike. No hedging ("might", "could potentially"), no marketing language, no exclamation marks. Write for a one-person compliance team who has 90 seconds to read this before their next meeting."""


USER_TEMPLATE = """Vendor: {vendor_name}{vendor_type_clause}
Risk score: {score:.1f} / 100   (state: {state}, threshold crossed: {threshold:.0f})
Alert type: {alert_type}   Convergence: {convergence_count} deteriorating signal dimensions
Fired at: {fired_at}

CONVERGING SIGNALS (the scored diff that triggered this alert):

{signals_block}

SOURCES (you MUST cite these by [N] in every factual claim):

{sources_block}

Produce STRICT JSON — no code fences, no preamble — with exactly these four string fields:

{{
  "headline": "one decisive sentence, ≤ 25 words, with at least one [N] citation",
  "sentiment_read": "2-3 sentences. Your independent read of the sentiment direction (overall negative / mixed / positive) and the specific signals driving it, each with [N] citations. Do not parrot the heuristic 'sentiment' labels in the evidence — judge for yourself from the titles and notes.",
  "narrative": "2-3 short paragraphs (separate with \\n\\n). Paragraph 1: what changed and the timeline of the change, citing sources. Paragraph 2: why it matters for a fintech that uses this vendor — concentration risk, operational dependency, contract exposure. Paragraph 3 (only if warranted): DORA implication — third-party risk register update, notification trigger, exit-plan check. Every factual claim ends with [N] or [N,M].",
  "recommended_action": "one paragraph of concrete next steps for a one-person GRC team. Each action references the signal(s) that justify it via [N]."
}}"""


def _build_signals_and_sources(
    alert: Alert,
) -> tuple[str, str, list[Citation]]:
    """Flatten alert signals into a numbered SOURCES list + a readable signals block."""
    citations: list[Citation] = []
    signals_lines: list[str] = []

    n = 0
    for sig in alert.signals:
        ev_list = sig.evidence[:MAX_EVIDENCE_PER_SIGNAL]
        sig_indices: list[int] = []
        for ev in ev_list:
            n += 1
            sig_indices.append(n)
            url = (ev.get("source_url") or "").strip()
            citations.append(Citation(
                n=n,
                metric=sig.metric,
                capture_date=ev.get("capture_date"),
                source_url=url or "(no public source — staged demo signal)",
                snippet=(ev.get("notes") or ev.get("value") or "")[:240],
            ))

        idx_str = ",".join(str(i) for i in sig_indices)
        signals_lines.append(f"- {sig.metric}: {sig.summary}")
        signals_lines.append(
            f"  latest: {sig.latest_value!r} @ {sig.latest_date}   "
            f"evidence: [{idx_str}]"
        )
        for ev in ev_list:
            note = (ev.get("notes") or "")[:140]
            signals_lines.append(
                f"      {ev.get('capture_date')}: {note}"
            )

    sources_lines: list[str] = []
    for c in citations:
        sources_lines.append(
            f"[{c.n}] metric={c.metric}  date={c.capture_date}  url={c.source_url}"
        )
        if c.snippet:
            sources_lines.append(f"     evidence: {c.snippet}")

    return ("\n".join(signals_lines), "\n".join(sources_lines), citations)


# ---------------------------------------------------------------------------
# Claude pass
# ---------------------------------------------------------------------------

def _call_claude(
    client: Anthropic,
    alert: Alert,
    vendor_type: str,
    signals_block: str,
    sources_block: str,
) -> tuple[dict, str]:
    """Return (parsed_json, raw_text). Raises on transport-level failure."""
    vendor_type_clause = f" ({vendor_type})" if vendor_type else ""
    user_msg = USER_TEMPLATE.format(
        vendor_name=alert.vendor_name,
        vendor_type_clause=vendor_type_clause,
        score=alert.score,
        state=alert.state.upper(),
        threshold=alert.threshold,
        alert_type=alert.alert_type,
        convergence_count=alert.convergence_count,
        fired_at=alert.fired_at,
        signals_block=signals_block,
        sources_block=sources_block,
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = msg.content[0].text if msg.content else ""
    cleaned = _strip_fences(raw)
    data = json.loads(cleaned)
    return data, raw


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

_ACTION_BY_STATE = {
    "critical": (
        "Convene the vendor risk committee within 48 hours. Activate the "
        "documented contingency or exit plan for this provider, and confirm "
        "DORA-aligned third-party register reflects the elevated risk tier. "
        "Notify the relationship owner; pause any new spend or scope expansion."
    ),
    "warning": (
        "Add to weekly monitoring cadence. Reach the vendor relationship "
        "lead for a status read on the signals below; refresh the third-party "
        "risk register entry. No escalation required unless additional signals "
        "land in the next 7 days."
    ),
    "stable": (
        "Maintain routine monitoring cadence. No action required."
    ),
}


def _deterministic_summary(
    alert: Alert, citations: list[Citation], reason: str = ""
) -> RiskSummary:
    metric_names = [s.metric for s in alert.signals[:4]]
    metric_str = ", ".join(metric_names) if metric_names else "no signals"

    # Build citation index per signal for the narrative.
    cites_by_metric: dict[str, list[int]] = {}
    for c in citations:
        cites_by_metric.setdefault(c.metric, []).append(c.n)

    def cite(metric: str) -> str:
        ns = cites_by_metric.get(metric, [])
        return "[" + ",".join(str(n) for n in ns[:3]) + "]" if ns else ""

    headline = (
        f"{alert.vendor_name} at {alert.state.upper()} (score {alert.score:.1f}): "
        f"{alert.convergence_count} converging signals — {metric_str} "
        + (cite(metric_names[0]) if metric_names else "")
    ).strip()

    # Sentiment read — aggregate heuristic sentiments across evidence.
    neg = pos = neu = 0
    for sig in alert.signals:
        for ev in sig.evidence:
            s = (ev.get("sentiment") or "").lower()
            if s == "negative":
                neg += 1
            elif s == "positive":
                pos += 1
            elif s == "neutral":
                neu += 1
    total = neg + pos + neu
    if total == 0:
        sentiment_read = "Insufficient sentiment evidence in the provided signals."
    elif neg > pos + neu:
        sentiment_read = (
            f"Negative across the converging signals "
            f"(neg={neg}, neu={neu}, pos={pos}). Heuristic read only — "
            f"AI pass unavailable."
        )
    elif neg > pos:
        sentiment_read = (
            f"Mixed-to-negative (neg={neg}, neu={neu}, pos={pos}). "
            f"Heuristic read only."
        )
    else:
        sentiment_read = (
            f"Mixed (neg={neg}, neu={neu}, pos={pos}). Heuristic read only."
        )

    paragraphs = []
    for sig in alert.signals:
        c = cite(sig.metric)
        paragraphs.append(f"{sig.summary} {c}.".strip())
    narrative = " ".join(paragraphs)
    if reason:
        narrative = narrative + f"\n\n(Note: deterministic fallback used because {reason}.)"

    action = _ACTION_BY_STATE.get(alert.state, _ACTION_BY_STATE["warning"])
    # Stamp citations onto recommended_action so the trust contract holds.
    action_cite = "[" + ",".join(str(c.n) for c in citations[:3]) + "]" if citations else ""
    recommended_action = f"{action} {action_cite}".strip()

    return RiskSummary(
        vendor_name=alert.vendor_name,
        state=alert.state,
        score=alert.score,
        alert_type=alert.alert_type,
        headline=headline,
        sentiment_read=sentiment_read,
        narrative=narrative,
        recommended_action=recommended_action,
        citations=citations,
        generated_by="deterministic-fallback",
        parse_error=reason,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def summarize_alert(
    alert: Alert,
    client: Optional[Anthropic] = None,
    vendor_type: str = "",
) -> RiskSummary:
    """
    Produce a sourced GRC risk briefing for an alert.

    `vendor_type` (optional): augments the prompt header (e.g., "Payments").
    The Alert payload doesn't carry it; pass it in if known.

    No ANTHROPIC_API_KEY -> deterministic fallback. Any Claude / parse error
    -> deterministic fallback (with the error noted in parse_error).
    """
    signals_block, sources_block, citations = _build_signals_and_sources(alert)

    if client is None and os.environ.get("ANTHROPIC_API_KEY"):
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if client is None:
        return _deterministic_summary(
            alert, citations, reason="ANTHROPIC_API_KEY not set"
        )

    try:
        data, raw = _call_claude(
            client, alert, vendor_type, signals_block, sources_block
        )
    except json.JSONDecodeError as e:
        return _deterministic_summary(
            alert, citations, reason=f"Claude returned non-JSON: {e!s}"
        )
    except APIError as e:
        return _deterministic_summary(
            alert, citations, reason=f"Anthropic API error: {e!s}"
        )
    except Exception as e:  # last-resort: never break the pipeline
        return _deterministic_summary(
            alert, citations, reason=f"unexpected error: {type(e).__name__}: {e!s}"
        )

    return RiskSummary(
        vendor_name=alert.vendor_name,
        state=alert.state,
        score=alert.score,
        alert_type=alert.alert_type,
        headline=str(data.get("headline", "")).strip(),
        sentiment_read=str(data.get("sentiment_read", "")).strip(),
        narrative=str(data.get("narrative", "")).strip(),
        recommended_action=str(data.get("recommended_action", "")).strip(),
        citations=citations,
        generated_by=MODEL,
    )


# ---------------------------------------------------------------------------
# Trust-contract validator
# ---------------------------------------------------------------------------

# Matches [1], [1,2], [1, 2, 3] etc. — one or more comma-separated ints in [].
_CITE_RX = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@dataclass
class CitationAudit:
    cited_ns: set[int]                 # citation indices that appear in the text
    valid_ns: set[int]                 # indices that exist in summary.citations
    invalid_ns: list[int]              # cited but not in valid -- hallucinations
    uncited_ns: list[int]              # exist but not cited -- low-cost (just unused)
    all_claims_sourced: bool           # True iff invalid_ns is empty
    citation_density: dict[str, int]   # per-field count of citation occurrences


def validate_citations(summary: RiskSummary) -> CitationAudit:
    """Parse [N] tags across the summary; confirm each resolves to a citation."""
    fields = {
        "headline": summary.headline,
        "sentiment_read": summary.sentiment_read,
        "narrative": summary.narrative,
        "recommended_action": summary.recommended_action,
    }
    cited_ns: set[int] = set()
    density: dict[str, int] = {}
    for name, text in fields.items():
        count = 0
        for m in _CITE_RX.finditer(text or ""):
            for chunk in m.group(1).split(","):
                cited_ns.add(int(chunk.strip()))
            count += 1
        density[name] = count

    valid_ns = {c.n for c in summary.citations}
    invalid_ns = sorted(cited_ns - valid_ns)
    uncited_ns = sorted(valid_ns - cited_ns)

    return CitationAudit(
        cited_ns=cited_ns,
        valid_ns=valid_ns,
        invalid_ns=invalid_ns,
        uncited_ns=uncited_ns,
        all_claims_sourced=(len(invalid_ns) == 0),
        citation_density=density,
    )
