"""
Capture layer (Step 2 generalized to all 5 real vendors).

For each vendor we run FOUR class-scoped Google searches via Bright Data
MCP's `search_engine` tool with an `after:` recency operator — cleaner
signal-to-metric mapping than one mashed query, and 2026-only results.

Per vendor per day, this module produces Type 2 append-only rows:

    1  news_volume row     (unique URLs across all classes; per-class
                            breakdown in notes for the narration / step 5)
    ~  news_sentiment rows (top_n per class, deduped by URL, class tag in
                            notes; sentiment uses a keyword heuristic — step
                            5's Claude pass replaces this)
    0+ legal_event rows    (only when a lawsuit-class hit's title+description
                            mentions the vendor AND a legal term — conservative)
    0+ leadership_change   (only when a leadership-class hit mentions the
                            vendor AND a C-role AND a departure verb)

The function returns row dicts shaped for Airtable batch_create — the
writer (script or future scheduler) decides when to land them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# Validator signature: (vendor_name, event_type, title, description) -> (valid, reason).
# Kept abstract so capture.py doesn't import the Anthropic SDK directly.
ValidatorFn = Callable[[str, str, str, str], tuple[bool, str]]


REAL_VENDORS: list[dict] = [
    {"name": "Stripe", "type": "Payments"},
    {"name": "Plaid", "type": "Bank Data"},
    {"name": "Snowflake", "type": "Data Infra"},
    {"name": "Twilio", "type": "Comms/2FA"},
    {"name": "AWS", "type": "Cloud Infra"},
]


# Query templates run against Google via search_engine. Recency operator
# `after:YYYY-MM-DD` is appended at call time (portable; doesn't depend on
# a per-tool recency parameter — see test_recency_filter.py).
QUERY_CLASSES: list[dict] = [
    {
        "class": "news",
        "template": "{vendor} news",
    },
    {
        "class": "lawsuit",
        "template": "{vendor} lawsuit OR sued OR settles OR court",
    },
    {
        "class": "layoff",
        "template": '{vendor} layoffs OR "job cuts" OR "workforce reduction"',
    },
    {
        "class": "leadership",
        "template": (
            '{vendor} CEO OR CTO OR CFO OR chairman '
            '"steps down" OR resigns OR departs'
        ),
    },
]


# Keyword sentiment heuristic — placeholder until step 5 (Claude takes over).
# Lifted from test_airtable_write.py to keep one source of truth.
NEG_TERMS = {
    "layoff", "laid off", "lay off", "cut", "cuts", "fired", "lawsuit",
    "sued", "suit ", "breach", "hack", "outage", "fraud", "scandal",
    "investigation", "fine ", "penalty", "resign", "departure", "downturn",
    "decline", "plunge", "slash", "axe", "struggle", "downgrade", "bloodbath",
}
POS_TERMS = {
    "growth", "raise", "raised", "funding round", "hire", "hiring", "expand",
    "launch", "partner", "acquired", "acquisition", "profit", "milestone",
    "success", "beat", "valuation", "ipo",
}


# Event-detection patterns (conservative — require vendor + signal in same blob).
LEGAL_TERMS = {
    "lawsuit", "sued", "settles", "settlement", "court", "indicted",
    "charges", "subpoena", "regulator", "fines", "penalty", "antitrust",
}
LEADERSHIP_ROLES = {
    "ceo", "cto", "cfo", "coo", "cio", "cmo", "chairman",
    "president", "founder", "head of",
}
LEADERSHIP_VERBS = {
    "departs", "departure", "steps down", "resign", "resigns",
    "exits", "ousted", "fired", "replaces",
}


def score_sentiment_heuristic(text: str) -> tuple[int, str]:
    """Return (numeric_score, label). Placeholder until step 5 (Claude)."""
    t = " " + text.lower() + " "
    neg = sum(1 for w in NEG_TERMS if w in t)
    pos = sum(1 for w in POS_TERMS if w in t)
    diff = pos - neg
    if diff < 0:
        return -1, "negative"
    if diff > 0:
        return 1, "positive"
    return 0, "neutral"


def _detect_legal(title: str, desc: str, vendor: str) -> bool:
    blob = f" {title.lower()} {desc.lower()} "
    if vendor.lower() not in blob:
        return False
    return any(t in blob for t in LEGAL_TERMS)


def _detect_leadership(title: str, desc: str, vendor: str) -> bool:
    blob = f" {title.lower()} {desc.lower()} "
    if vendor.lower() not in blob:
        return False
    has_role = any(r in blob for r in LEADERSHIP_ROLES)
    has_verb = any(v in blob for v in LEADERSHIP_VERBS)
    return has_role and has_verb


async def _call_search(session: ClientSession, query: str) -> list[dict]:
    """One search_engine call; raises on MCP error."""
    result = await session.call_tool(
        "search_engine",
        arguments={"query": query, "engine": "google"},
    )
    if result.isError:
        raise RuntimeError(f"MCP error for {query!r}: {result.content}")
    payload = json.loads(result.content[0].text)
    return payload.get("organic", [])


@dataclass
class VendorCapture:
    vendor_name: str
    vendor_type: str
    capture_date: str
    per_class_counts: dict[str, int]     # organic-result count per query class
    rows: list[dict] = field(default_factory=list)
    events_detected: dict[str, int] = field(default_factory=dict)
    events_rejected: list[dict] = field(default_factory=list)  # validator output


async def capture_vendor(
    session: ClientSession,
    vendor: dict,
    after: str = "2026-01-01",
    top_n: int = 5,
    capture_date: str | None = None,
    validator: ValidatorFn | None = None,
) -> VendorCapture:
    """Run all query classes for ONE vendor and produce Type 2 row dicts."""
    today = capture_date or date.today().isoformat()
    base = {
        "capture_date": today,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
    }

    seen_urls: set[str] = set()
    sentiment_rows: list[dict] = []
    legal_rows: list[dict] = []
    leadership_rows: list[dict] = []
    rejected_events: list[dict] = []
    per_class_counts: dict[str, int] = {}

    for qc in QUERY_CLASSES:
        query = f"{qc['template'].format(vendor=vendor['name'])} after:{after}"
        organic = await _call_search(session, query)
        per_class_counts[qc["class"]] = len(organic)

        for item in organic[:top_n]:
            link = (item.get("link") or "").strip()
            if not link:
                continue
            title = item.get("title") or ""
            desc = item.get("description") or ""

            # Sentiment row — one per UNIQUE URL across all classes.
            if link not in seen_urls:
                seen_urls.add(link)
                value, label = score_sentiment_heuristic(f"{title} {desc}")
                sentiment_rows.append({
                    **base,
                    "metric": "news_sentiment",
                    "value": str(value),
                    "unit": "score",
                    "source_url": link,
                    "sentiment": label,
                    "notes": f"[{qc['class']}] {title}"[:255],
                })

            # Event candidates — keyword match is the FILTER, not the verdict.
            # When a `validator` callback is supplied (Claude validation), only
            # validated candidates are kept; rejections are recorded for audit.
            for kind, predicate, bucket in (
                ("legal_event",
                 qc["class"] == "lawsuit" and _detect_legal(title, desc, vendor["name"]),
                 legal_rows),
                ("leadership_change",
                 qc["class"] == "leadership" and _detect_leadership(title, desc, vendor["name"]),
                 leadership_rows),
            ):
                if not predicate:
                    continue
                if validator is not None:
                    valid, reason = validator(vendor["name"], kind, title, desc)
                    if not valid:
                        rejected_events.append({
                            "metric": kind,
                            "title": title,
                            "source_url": link,
                            "reason": reason,
                        })
                        continue
                    note_prefix = f"validated ({reason})"
                else:
                    note_prefix = "auto-detected"
                bucket.append({
                    **base,
                    "metric": kind,
                    "value": (title[:90] or f"{kind} signal"),
                    "unit": "event",
                    "source_url": link,
                    "sentiment": "negative",
                    "notes": f"{note_prefix}: {title}"[:255],
                })

    # Aggregate news_volume row — total unique URLs across all classes.
    # Per-class breakdown lives in notes so step 5 / dashboard can narrate it.
    breakdown = ", ".join(f"{k}={v}" for k, v in per_class_counts.items())
    volume_row = {
        **base,
        "metric": "news_volume",
        "value": str(len(seen_urls)),
        "unit": "count",
        "source_url": (
            f"https://www.google.com/search?q="
            f"{vendor['name'].replace(' ', '+')}+news"
        ),
        "sentiment": "",
        "notes": f"unique_urls={len(seen_urls)}; per_class: {breakdown}"[:255],
    }

    rows = sentiment_rows + legal_rows + leadership_rows + [volume_row]

    return VendorCapture(
        vendor_name=vendor["name"],
        vendor_type=vendor["type"],
        capture_date=today,
        per_class_counts=per_class_counts,
        rows=rows,
        events_detected={
            "legal": len(legal_rows),
            "leadership": len(leadership_rows),
        },
        events_rejected=rejected_events,
    )


async def capture_all(
    mcp_url: str,
    vendors: list[dict],
    after: str = "2026-01-01",
    top_n: int = 5,
    capture_date: str | None = None,
    validator: ValidatorFn | None = None,
) -> list[VendorCapture]:
    """Open one MCP session, run capture for each vendor sequentially."""
    captures: list[VendorCapture] = []
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for v in vendors:
                cap = await capture_vendor(
                    session, v, after=after, top_n=top_n,
                    capture_date=capture_date, validator=validator,
                )
                captures.append(cap)
    return captures
