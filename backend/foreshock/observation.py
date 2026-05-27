"""
Pull-pipeline helpers.

Single home for the daily-observation pull logic — the search_engine
calls with retry → scrape_as_markdown fallback chain, the per-vendor
loop, and the row-builders. Used by:

  - `scripts/run_daily_observation.py` (CLI runner; thin wrapper)
  - `foreshock/agent.py`                (the unattended daily agent;
                                         orchestrates Pull → Clean →
                                         Promote with SSE event emission)

Per the "do not duplicate" rule, both call-sites import from here.
The CLI script gets the original behavior (no events emitted) by
passing `emit_event=None` (default); the agent passes a callback that
pushes events onto its SSE queue.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
from datetime import date
from typing import Any, Callable, Optional

from anthropic import Anthropic
from mcp import ClientSession

from .capture import (
    QUERY_CLASSES,
    REAL_VENDORS,
    detect_legal_event,
    detect_leadership_event,
    score_sentiment_heuristic,
)
from .edgar import capture_edgar_for_vendor
from .validator import _strip_fences

AFTER = "2026-01-01"
TOP_N = 5
NOTES_TAG = "daily-observation"

# Veridian's open_roles staged continuation — the hiring-freeze arc.
# 38 → 32 → 22 → 14 → 8 → 4 over 34 days (-89%); pegs the open_roles
# component at the score cap. Demo data only; never goes through MCP.
VERIDIAN_OPEN_ROLES_TODAY = 4


# ---------------------------------------------------------------------------
# MCP call with retry → scrape_as_markdown fallback
# ---------------------------------------------------------------------------

async def _try_search_engine(session: ClientSession, query: str) -> list[dict]:
    """Single attempt at search_engine. Raises on error; returns organic[]."""
    result = await session.call_tool(
        "search_engine", arguments={"query": query, "engine": "google"}
    )
    if result.isError:
        raise RuntimeError(f"MCP isError: {result.content}")
    payload = json.loads(result.content[0].text)
    return payload.get("organic", [])


async def _try_scrape_fallback(
    session: ClientSession, query: str, anthropic_client: Anthropic
) -> list[dict]:
    """
    Fallback path: scrape Google SERP as markdown via scrape_as_markdown,
    then ask AI to extract a search_engine-shaped organic[] list from it.
    """
    google_url = (
        "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    )
    result = await session.call_tool(
        "scrape_as_markdown", arguments={"url": google_url}
    )
    if result.isError:
        raise RuntimeError(f"scrape_as_markdown isError: {result.content}")
    markdown = result.content[0].text or ""

    prompt = (
        "Below is markdown from a Google search results page. Extract up to "
        "10 top organic results as a JSON array. Each entry is "
        '{"link": "<url>", "title": "<title>", "description": "<snippet>"}.'
        " Skip ads, knowledge panels, 'People also ask' blocks. Return "
        "STRICT JSON only, no preamble, no code fences.\n\n"
        f"MARKDOWN:\n{markdown[:6000]}"
    )
    msg = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _strip_fences(msg.content[0].text if msg.content else "[]")
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


async def search_with_fallback(
    session: ClientSession,
    query: str,
    anthropic_client: Optional[Anthropic],
    fallback_log: list,
    label: str,
) -> tuple[list[dict], str]:
    """
    search_engine → retry → scrape_as_markdown + AI parse.
    Returns (organic, path-used). Always returns a list (possibly empty).
    """
    # Attempt 1: direct search_engine
    try:
        organic = await _try_search_engine(session, query)
        return organic, "search_engine"
    except Exception as e:
        pass  # fall through to retry

    # Attempt 2: retry after a brief pause (transient backend issues)
    await asyncio.sleep(2.0)
    try:
        organic = await _try_search_engine(session, query)
        return organic, "search_engine (retry)"
    except Exception as e:
        pass  # fall through to scrape fallback

    # Attempt 3: scrape_as_markdown fallback
    if anthropic_client is None:
        fallback_log.append({"label": label, "query": query,
                             "path": "all-failed (no AI key)"})
        return [], "all-failed"
    try:
        organic = await _try_scrape_fallback(session, query, anthropic_client)
        fallback_log.append({"label": label, "query": query,
                             "path": "scrape_as_markdown+ai",
                             "count": len(organic)})
        return organic, "scrape_as_markdown+ai"
    except Exception as e:
        fallback_log.append({"label": label, "query": query,
                             "path": f"all-failed: {e!s}"})
        return [], "all-failed"


# ---------------------------------------------------------------------------
# Row builders — same shapes as capture.py so the schema stays uniform
# ---------------------------------------------------------------------------

def build_news_class_rows(
    vendor: dict, qc: dict, organic: list[dict],
    capture_date: str, seen_urls: set[str],
    fallback_path: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Per-class results → (sentiment_rows, legal_rows, leadership_rows)."""
    base = {
        "capture_date": capture_date,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
    }
    sentiment_rows: list[dict] = []
    legal_rows: list[dict] = []
    leadership_rows: list[dict] = []
    path_tag = "" if fallback_path == "search_engine" else f" [via {fallback_path}]"

    for item in organic[:TOP_N]:
        link = (item.get("link") or "").strip()
        if not link:
            continue
        title = (item.get("title") or "").strip()
        desc = (item.get("description") or "").strip()

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
                "notes": (
                    f"{NOTES_TAG}: [{qc['class']}]{path_tag} {title}"
                )[:255],
            })

        # Event candidates — conservative match; will be Claude-validated
        # downstream in the agent's Clean step.
        if qc["class"] == "lawsuit" and detect_legal_event(title, desc, vendor["name"]):
            legal_rows.append({
                **base,
                "metric": "legal_event",
                "value": (title[:90] or "legal signal"),
                "unit": "event",
                "source_url": link,
                "sentiment": "negative",
                "notes": f"{NOTES_TAG}: auto-detected{path_tag}: {title}"[:255],
            })
        if qc["class"] == "leadership" and detect_leadership_event(title, desc, vendor["name"]):
            leadership_rows.append({
                **base,
                "metric": "leadership_change",
                "value": (title[:90] or "leadership signal"),
                "unit": "event",
                "source_url": link,
                "sentiment": "negative",
                "notes": f"{NOTES_TAG}: auto-detected{path_tag}: {title}"[:255],
            })

    return sentiment_rows, legal_rows, leadership_rows


def build_news_volume_row(
    vendor: dict, per_class_counts: dict[str, int],
    capture_date: str, unique_url_count: int,
    fallback_paths: dict[str, str],
) -> dict:
    breakdown = ", ".join(f"{k}={v}" for k, v in per_class_counts.items())
    paths = ", ".join(f"{k}:{v}" for k, v in fallback_paths.items())
    return {
        "capture_date": capture_date,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
        "metric": "news_volume",
        "value": str(unique_url_count),
        "unit": "count",
        "source_url": (
            "https://www.google.com/search?q="
            + vendor["name"].replace(" ", "+") + "+news"
        ),
        "sentiment": "",
        "notes": (
            f"{NOTES_TAG}: unique_urls={unique_url_count}; "
            f"per_class: {breakdown}; paths: {paths}"
        )[:255],
    }


def build_open_roles_row(
    vendor: dict, organic_count: int, capture_date: str,
    fallback_path: str,
) -> dict:
    query_name = vendor.get("query_name") or vendor["name"]
    return {
        "capture_date": capture_date,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
        "metric": "open_roles",
        "value": str(organic_count),
        "unit": "postings",
        "source_url": (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(
                f'{query_name} jobs OR careers OR hiring OR "open position"'
            )
        )[:500],
        "sentiment": "",
        "notes": (
            f"{NOTES_TAG}: careers/jobs/hiring URL count for {vendor['name']} "
            f"({organic_count} hits via {fallback_path})"
        )[:255],
    }


def build_veridian_open_roles_row(capture_date: str) -> dict:
    return {
        "capture_date": capture_date,
        "vendor_name": "Veridian Pay",
        "vendor_type": "Payments/BaaS",
        "is_demo_vendor": True,
        "metric": "open_roles",
        "value": str(VERIDIAN_OPEN_ROLES_TODAY),
        "unit": "postings",
        "source_url": "DEMO-SCENARIO",
        "sentiment": "negative",
        "notes": (
            f"STUBBED open_roles hiring freeze continues "
            f"(value={VERIDIAN_OPEN_ROLES_TODAY}; "
            f"trajectory: 38→32→22→14→8→{VERIDIAN_OPEN_ROLES_TODAY} "
            f"= -89% from baseline)"
        )[:255],
    }


# ---------------------------------------------------------------------------
# Per-vendor capture — optional event emission for live-streaming consumers
# ---------------------------------------------------------------------------

# Event-emitter signature. Synchronous (queue.put_nowait under the hood).
# When None, capture runs silently (matches the original script behavior).
EmitFn = Callable[[dict], None]


async def capture_real_vendor(
    session: ClientSession,
    vendor: dict,
    capture_date: str,
    anthropic_client: Optional[Anthropic],
    fallback_log: list,
    emit_event: Optional[EmitFn] = None,
) -> dict:
    """
    Run all 5 queries (4 classes + open_roles) for one vendor.

    If `emit_event` is provided, emit one event per MCP call with status
    transitions: firing → done/failed. Consumed by the SSE stream in the
    agent endpoint. When None (default), runs silently.
    """
    query_name = vendor.get("query_name") or vendor["name"]
    seen_urls: set[str] = set()
    sentiment_rows: list[dict] = []
    legal_rows: list[dict] = []
    leadership_rows: list[dict] = []
    per_class_counts: dict[str, int] = {}
    fallback_paths: dict[str, str] = {}

    def emit(payload: dict) -> None:
        if emit_event is not None:
            emit_event(payload)

    # The 4 news/lawsuit/layoff/leadership classes
    for qc in QUERY_CLASSES:
        query = f"{qc['template'].format(query_name=query_name)} after:{AFTER}"
        label = f"{vendor['name']}/{qc['class']}"

        emit({
            "step": "pull",
            "vendor": vendor["name"],
            "tool": "search_engine",
            "class": qc["class"],
            "query": query,
            "status": "firing",
        })

        t0 = time.monotonic()
        organic, path = await search_with_fallback(
            session, query, anthropic_client, fallback_log, label
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        per_class_counts[qc["class"]] = len(organic)
        fallback_paths[qc["class"]] = path

        emit({
            "step": "pull",
            "vendor": vendor["name"],
            "tool": "search_engine",
            "class": qc["class"],
            "query": query,
            "status": "done" if organic or path != "all-failed" else "failed",
            "results": len(organic),
            "duration_ms": duration_ms,
            "path": path,
        })

        s, l, ld = build_news_class_rows(
            vendor, qc, organic, capture_date, seen_urls, path
        )
        sentiment_rows.extend(s)
        legal_rows.extend(l)
        leadership_rows.extend(ld)

    # The 1 open_roles careers query
    careers_query = (
        f'{query_name} jobs OR careers OR hiring OR "open position" '
        f"after:{AFTER}"
    )
    label = f"{vendor['name']}/open_roles"

    emit({
        "step": "pull",
        "vendor": vendor["name"],
        "tool": "search_engine",
        "class": "open_roles",
        "query": careers_query,
        "status": "firing",
    })

    t0 = time.monotonic()
    careers_organic, careers_path = await search_with_fallback(
        session, careers_query, anthropic_client, fallback_log, label
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    emit({
        "step": "pull",
        "vendor": vendor["name"],
        "tool": "search_engine",
        "class": "open_roles",
        "query": careers_query,
        "status": "done" if careers_organic or careers_path != "all-failed" else "failed",
        "results": len(careers_organic),
        "duration_ms": duration_ms,
        "path": careers_path,
    })

    open_roles_row = build_open_roles_row(
        vendor, len(careers_organic), capture_date, careers_path
    )
    volume_row = build_news_volume_row(
        vendor, per_class_counts, capture_date, len(seen_urls), fallback_paths
    )

    # The EDGAR class — no-op for vendors without a CIK (Stripe, Plaid).
    # Uses scrape_as_markdown on SEC's submissions JSON; emits its own
    # firing/done event so the FlowPanel renders progress consistently.
    edgar_result = await capture_edgar_for_vendor(
        session, vendor, capture_date, emit_event=emit_event,
    )
    edgar_rows = edgar_result.get("rows", [])

    rows = (
        sentiment_rows + legal_rows + leadership_rows
        + [open_roles_row, volume_row] + edgar_rows
    )
    return {
        "vendor": vendor["name"],
        "rows": rows,
        "sentiment_count": len(sentiment_rows),
        "legal_count": len(legal_rows),
        "leadership_count": len(leadership_rows),
        "open_roles_value": open_roles_row["value"],
        "news_volume_value": volume_row["value"],
        "per_class_counts": per_class_counts,
        "fallback_paths": fallback_paths,
        "open_roles_path": careers_path,
        "edgar_filings_found": edgar_result.get("filings_found", 0),
        "edgar_items_matched": edgar_result.get("items_matched", 0),
    }
