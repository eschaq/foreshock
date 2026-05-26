"""
Event validator (gate between heuristic event-detection and the schema).

The keyword-based event detectors in `capture.py` cast a wide net —
they fire whenever a vendor name co-occurs with a role + departure verb
(for leadership_change) or a legal term (for legal_event). That catches
real events but also pulls in:

  - similarly-named but unrelated entities ("Stripe Communications" is a
    PR/creative agency, NOT Stripe Inc.)
  - executive share sales, pay disclosures, comp committee filings
  - interviews + opinion pieces by current execs (no departure)
  - Reddit/forum threads tagged with a vendor's name
  - regulatory entity-listing pages

Because leadership_change is the highest-weighted dimension in scoring
(0.30), each false positive distorts the Veridian-critical / real-stable
contrast AND breaks the trust contract (sourced citations).

This module wraps a single tight Claude call that returns
`(valid: bool, reason: str)` for one candidate event row.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from anthropic import Anthropic

# CLAUDE.md spec: Sonnet 4.5 (current latest in the 4.x line = Sonnet 4.6).
MODEL = "claude-sonnet-4-6"

EVENT_TYPE_HUMAN = {
    "leadership_change": "leadership departure",
    "legal_event": "legal action",
}

_PROMPT = """You are an evidence validator for a vendor-risk monitoring system. Your job is to reject false positives from keyword-based event detection.

VENDOR: {vendor}
CANDIDATE EVENT TYPE: {event_type_human}
SEARCH RESULT TITLE: {title}
DESCRIPTION: {description}

Question: Is this a GENUINE {event_type_human} at the company "{vendor}" itself?

REJECT (valid=false) when ANY of these apply:
- The title refers to a similarly-named but UNRELATED entity (e.g., "Stripe Communications" is a PR/creative agency, NOT Stripe Inc. the payments company)
- For leadership_departure: it is actually a share/stock sale, insider transaction, pay or compensation disclosure, interview, quote, opinion, current-role announcement, or speculation about a future departure
- For legal_action: it is a forum/Reddit/StackOverflow post, opinion piece, general industry coverage, regulatory-entity LISTING page, or commentary
- The vendor is mentioned only in passing or as backdrop for an event happening to someone else (a customer, partner, competitor)

ACCEPT (valid=true) ONLY when the title clearly describes:
- For leadership_departure: a named executive leaving the company (resignation, exit, replacement, termination, retirement)
- For legal_action: a lawsuit filed against the vendor, court ruling, settlement, regulator action against the vendor, or formal investigation of the vendor

Return STRICT JSON only, no preamble, no code fences:
{{"valid": true|false, "reason": "<= 12 words"}}
"""


@dataclass
class ValidationResult:
    valid: bool
    reason: str
    raw: str = ""   # raw Claude text, kept for debugging


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        # strip ```json ... ``` or ``` ... ```
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


def validate_event(
    client: Anthropic,
    vendor: str,
    event_type: str,
    title: str,
    description: str = "",
) -> ValidationResult:
    """One Claude call. event_type must be 'leadership_change' or 'legal_event'."""
    type_human = EVENT_TYPE_HUMAN.get(event_type, event_type)
    prompt = _PROMPT.format(
        vendor=vendor,
        event_type_human=type_human,
        title=title.strip() or "(empty)",
        description=(description or "").strip() or "(no description)",
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text if msg.content else ""
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        return ValidationResult(
            valid=bool(data.get("valid", False)),
            reason=str(data.get("reason", "") or "")[:200],
            raw=raw,
        )
    except json.JSONDecodeError:
        return ValidationResult(
            valid=False,
            reason=f"parse_error: {text[:80]}",
            raw=raw,
        )


def get_default_client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# classify_signal — pick the accurate class for a sentiment-row title.
#
# Used by the audit script that fixes misleading [leadership]/[lawsuit]
# prefixes in news_sentiment notes (which the future detail view will expose).
# ---------------------------------------------------------------------------

VALID_CLASSES = {"leadership", "lawsuit", "layoff", "news", "unrelated"}

_CLASSIFY_PROMPT = """You are reclassifying a news search result for a vendor-risk monitoring system. The result was originally tagged with a query class, but the tag may be wrong because the keyword search returned off-topic noise.

VENDOR: {vendor}
ORIGINAL TAG: {current_class}
SEARCH RESULT TITLE: {title}
DESCRIPTION: {description}

Pick the ACCURATE class. Choose EXACTLY ONE:

- "leadership": describes a real EXECUTIVE DEPARTURE at the vendor (resignation, exit, replacement, termination, retirement). NOT pay disclosures, share/stock sales, interviews, quotes, org charts, or speculation.
- "lawsuit": describes a real LEGAL ACTION against the vendor (lawsuit filed, court ruling, settlement, regulator action, formal investigation). NOT Reddit threads, opinion pieces, generic entity/Wikipedia pages.
- "layoff": describes actual LAYOFFS, job cuts, or workforce reductions at the vendor.
- "news": describes the vendor in general news (product launches, partnerships, financial coverage, executive interviews/quotes, industry coverage where vendor IS a primary subject). Catch-all for vendor-relevant news that isn't leadership/lawsuit/layoff.
- "unrelated": vendor is NOT the primary subject — refers to a similarly-named DIFFERENT company (e.g., "Stripe Communications" PR agency vs Stripe Inc.), an event at a DIFFERENT vendor that just mentions this one, or vendor appears only in passing.

Return STRICT JSON only, no preamble, no code fences:
{{"class": "leadership|lawsuit|layoff|news|unrelated", "reason": "<= 12 words"}}
"""


@dataclass
class ClassificationResult:
    cls: str            # one of VALID_CLASSES (or "parse_error")
    reason: str
    raw: str = ""


def classify_signal(
    client: Anthropic,
    vendor: str,
    current_class: str,
    title: str,
    description: str = "",
) -> ClassificationResult:
    """Reclassify a sentiment row's title into the accurate class."""
    prompt = _CLASSIFY_PROMPT.format(
        vendor=vendor,
        current_class=current_class,
        title=title.strip() or "(empty)",
        description=(description or "").strip() or "(no description)",
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text if msg.content else ""
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
        cls = str(data.get("class", "")).strip().lower()
        if cls not in VALID_CLASSES:
            return ClassificationResult(
                cls="parse_error",
                reason=f"unknown class: {cls!r}",
                raw=raw,
            )
        return ClassificationResult(
            cls=cls,
            reason=str(data.get("reason", "") or "")[:200],
            raw=raw,
        )
    except json.JSONDecodeError:
        return ClassificationResult(
            cls="parse_error",
            reason=f"json parse failed: {text[:80]}",
            raw=raw,
        )
