"""
SEC EDGAR signal class — pulls recent 8-K filings directly from SEC's
free submissions API (data.sec.gov), bypassing Bright Data MCP.

Why direct, not MCP. Bright Data's `scrape_as_markdown` is HTML→markdown
only and returns empty for application/json endpoints; the HTML fallback
(`/cgi-bin/browse-edgar`) is blocked by Bright Data's robots-tier
policy. SEC's submissions API is explicitly designed for programmatic
access and their fair-use policy invites direct calls — we just need a
contactable User-Agent. The narrative split: Bright Data fronts locked
commercial sources (news, Glassdoor, LinkedIn); regulatory APIs go
direct because they're built for it.

Single-fetch design. SEC submissions JSON inlines both the `items`
field (e.g. "5.02,9.01") and `primaryDocDescription` per filing — the
per-filing `-index.htm` fetch the original spec suggested would 3x
latency without yielding new data.

Item mapping (Wave 2):
    5.02 -> leadership_change   (officer / director departure or appointment)
    1.01 -> legal_event         (material definitive agreement — M&A signal)
    6.04 -> legal_event         (bankruptcy filing)

Other items are ignored. The Claude validator (`foreshock/validator.py`)
gates the rows downstream, same as news-sourced event candidates.

Vendor eligibility: `vendor["cik"]` field on REAL_VENDORS. Private vendors
(Stripe, Plaid) and the demo vendor (Veridian) have `cik=None` and are
skipped — `capture_edgar_for_vendor` is a no-op for them.
"""
from __future__ import annotations

import asyncio
import time
from datetime import date, timedelta
from typing import Any, Callable, Optional

import requests
from mcp import ClientSession


# 8-K item -> internal metric. Items not listed here are dropped.
ITEM_TO_METRIC: dict[str, str] = {
    "5.02": "leadership_change",
    "1.01": "legal_event",
    "6.04": "legal_event",
}

# SEC's official short titles per item — used as fallback when a filing's
# `primaryDocDescription` is sparse (often just "8-K" or "FORM 8-K").
# https://www.sec.gov/about/forms/form8-k.pdf
ITEM_TITLE: dict[str, str] = {
    "5.02": "Departure of Directors / Certain Officers",
    "1.01": "Entry into a Material Definitive Agreement",
    "6.04": "Bankruptcy or Receivership",
}


def _readable_desc(raw_desc: str, item: str) -> str:
    """Fall back to SEC's official item title if the doc description is
    just the form name (very common for 8-Ks)."""
    d = (raw_desc or "").strip()
    if not d or d.upper() in {"8-K", "FORM 8-K"}:
        return ITEM_TITLE.get(item, "(see filing)")
    return d

DEFAULT_LOOKBACK_DAYS = 30
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

# SEC fair-use policy: identify the caller + provide a real contact.
# https://www.sec.gov/os/accessing-edgar-data
SEC_USER_AGENT = "Foreshock/1.0 contact@foreshock.ai"
SEC_REQUEST_TIMEOUT = 15.0  # seconds

EmitFn = Callable[[dict], None]


# ---------------------------------------------------------------------------
# Direct HTTP fetch (SEC submissions API)
# ---------------------------------------------------------------------------

def _sync_fetch_submissions(cik_padded: str) -> dict:
    """Blocking GET to SEC submissions API. Returns parsed JSON dict."""
    url = SUBMISSIONS_URL.format(cik=cik_padded)
    resp = requests.get(
        url,
        headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=SEC_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_submissions(
    session: Optional[ClientSession], cik_padded: str
) -> dict:
    """
    Async wrapper around `_sync_fetch_submissions`. The `session`
    parameter is accepted (and ignored) for signature compatibility with
    other capture-class functions — EDGAR doesn't use MCP.
    """
    return await asyncio.to_thread(_sync_fetch_submissions, cik_padded)


# ---------------------------------------------------------------------------
# Parsing + row construction
# ---------------------------------------------------------------------------

def _index_url(cik_padded: str, accession_no: str) -> str:
    """
    SEC archive URL for a filing's human-readable index page.

    The spec suggested `/{cik}/{accessionNumber}.txt`, but SEC's archive
    is actually laid out as
        /Archives/edgar/data/{cik_int}/{accession_stripped}/{accession}-index.htm
    so we build a working clickable URL. The .txt full-submission is at
    the same directory + `.txt` if a raw artifact is ever needed.
    """
    cik_int = str(int(cik_padded))  # strip leading zeros for the URL path
    no_dashes = accession_no.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{no_dashes}/"
        f"{accession_no}-index.htm"
    )


def parse_recent_8ks(
    submissions: dict,
    days: int = DEFAULT_LOOKBACK_DAYS,
    as_of: Optional[date] = None,
) -> list[dict]:
    """
    Walk `filings.recent` and return one dict per 8-K filed within `days`
    whose `items` field includes at least one targeted item.
    """
    as_of = as_of or date.today()
    cutoff = as_of - timedelta(days=days)

    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return []

    forms = recent.get("form", []) or []
    accs = recent.get("accessionNumber", []) or []
    dates = recent.get("filingDate", []) or []
    items_list = recent.get("items", []) or []
    descs = recent.get("primaryDocDescription", []) or []

    out: list[dict] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            filing_date = date.fromisoformat(dates[i])
        except (ValueError, IndexError):
            continue
        if filing_date < cutoff:
            continue
        items_str = items_list[i] if i < len(items_list) else ""
        items = [x.strip() for x in (items_str or "").split(",") if x.strip()]
        targeted = [x for x in items if x in ITEM_TO_METRIC]
        if not targeted:
            continue
        out.append({
            "accession_number": accs[i],
            "filing_date": filing_date,
            "items": items,
            "targeted_items": targeted,
            "description": (descs[i] if i < len(descs) else "") or "",
        })
    return out


def build_edgar_rows(
    vendor: dict,
    cik_padded: str,
    filings: list[dict],
    capture_date: str,
) -> list[dict]:
    """
    One Airtable row per (filing, targeted_item) pair. Multi-item filings
    fan out — a single 8-K that fires both 5.02 and 1.01 produces two rows
    (one leadership_change, one legal_event), each citing the same source.
    """
    base = {
        "capture_date": capture_date,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
    }
    rows: list[dict] = []
    for f in filings:
        index_url = _index_url(cik_padded, f["accession_number"])
        for item in f["targeted_items"]:
            metric = ITEM_TO_METRIC[item]
            desc = _readable_desc(f["description"], item)
            value_text = f"SEC 8-K Item {item} — {desc}"
            rows.append({
                **base,
                "metric": metric,
                "value": value_text[:90],
                "unit": "event",
                "source_url": index_url,
                "sentiment": "negative" if metric == "legal_event" else "neutral",
                "notes": (
                    f"edgar-8k: Item {item} — {desc}; "
                    f"filed {f['filing_date'].isoformat()}; "
                    f"accession {f['accession_number']}"
                )[:255],
            })
    return rows


# ---------------------------------------------------------------------------
# Top-level per-vendor capture
# ---------------------------------------------------------------------------

async def capture_edgar_for_vendor(
    session: Optional[ClientSession],
    vendor: dict,
    capture_date: str,
    emit_event: Optional[EmitFn] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict:
    """
    Pull EDGAR 8-Ks for one vendor. No-op if vendor has no `cik`.
    Mirrors the per-class emission contract used by capture_real_vendor.

    `session` is accepted for signature parity with other capture-class
    functions but ignored — EDGAR goes direct to data.sec.gov.
    """
    def emit(p: dict) -> None:
        if emit_event is not None:
            emit_event(p)

    cik_padded = vendor.get("cik")
    if not cik_padded:
        return {
            "vendor": vendor["name"],
            "rows": [],
            "filings_found": 0,
            "items_matched": 0,
            "skipped_reason": "no CIK configured (private or fictional)",
        }

    query_label = f"SEC EDGAR 8-K CIK{cik_padded}"
    emit({
        "step": "pull",
        "vendor": vendor["name"],
        "tool": "sec-submissions-api",
        "class": "edgar_8k",
        "query": query_label,
        "status": "firing",
    })

    t0 = time.monotonic()
    try:
        submissions = await fetch_submissions(session, cik_padded)
    except Exception as e:
        emit({
            "step": "pull",
            "vendor": vendor["name"],
            "tool": "scrape_as_markdown",
            "class": "edgar_8k",
            "query": query_label,
            "status": "failed",
            "error": str(e),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "path": "direct-sec-api",
        })
        return {
            "vendor": vendor["name"], "rows": [],
            "filings_found": 0, "items_matched": 0, "error": str(e),
        }

    filings = parse_recent_8ks(submissions, days=lookback_days)
    rows = build_edgar_rows(vendor, cik_padded, filings, capture_date)
    duration_ms = int((time.monotonic() - t0) * 1000)

    emit({
        "step": "pull",
        "vendor": vendor["name"],
        "tool": "sec-submissions-api",
        "class": "edgar_8k",
        "query": query_label,
        "status": "done",
        "filings_found": len(filings),
        "items_matched": len(rows),
        "duration_ms": duration_ms,
        "path": "direct-sec-api",
    })

    return {
        "vendor": vendor["name"],
        "rows": rows,
        "filings_found": len(filings),
        "items_matched": len(rows),
    }
