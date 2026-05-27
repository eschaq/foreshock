"""
Unattended daily agent — Pull → Clean → Promote pipeline.

Runs the full daily observation as a single async job with per-step
event emission for live UI display. Triggered by:
  - POST /agent/run (UI button / keyboard chord)
  - Railway cron at 07:00 UTC (see railway.toml)

Both surfaces hit the same `run_agent_pipeline()` entry point.

Pipeline stages
---------------
1. PULL — fire all Bright Data MCP calls (4 query classes + open_roles
   per real vendor + Veridian's staged continuation). Uses the
   retry → scrape_as_markdown fallback chain from `foreshock.observation`.

2. CLEAN — run the AI validator (`foreshock.validator.validate_event`)
   on every event candidate from this pull. Reject false positives
   before they reach Airtable; the per-vendor sentiment + volume rows
   pass through unchanged.

3. PROMOTE — Type 2 append every surviving row to Airtable, grouped
   by vendor so per-vendor write confirmations can stream back.

Final event: {step: "complete", summary: {...}}.

Per the "do not duplicate" rule, all pull-step logic lives in
`foreshock.observation`; validation in `foreshock.validator`. This
module is pure orchestration + event emission.
"""
from __future__ import annotations

import os
import time
from datetime import date
from typing import Callable, Optional

from anthropic import Anthropic
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pyairtable import Api

from .capture import REAL_VENDORS
from .observation import (
    build_veridian_open_roles_row,
    capture_real_vendor,
)
from .validator import validate_event

BD_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN", "")
AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AT_BASE = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
ANTH_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"
TABLE = "signals"

EmitFn = Callable[[dict], None]


async def run_agent_pipeline(emit_event: EmitFn) -> dict:
    """
    Pull → Clean → Promote, emitting per-step progress events.

    `emit_event` is a synchronous callback (typically queue.put_nowait on
    an asyncio.Queue bridged to an SSE stream).

    Returns the final summary dict. Also emits a `{step: "complete",
    summary: ...}` event as the last event before the stream closes.
    """
    start = time.monotonic()
    today = date.today().isoformat()

    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE)
    anthropic_client = Anthropic(api_key=ANTH_KEY) if ANTH_KEY else None

    # ===== STEP 1: PULL =================================================
    emit_event({"step": "pull", "phase": "start",
                "vendors": [v["name"] for v in REAL_VENDORS] + ["Veridian Pay"]})

    pulled_rows: list[dict] = []
    pull_failures: list[dict] = []
    fallback_log: list = []
    fallback_count = 0

    try:
        async with streamablehttp_client(MCP_URL) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                for vendor in REAL_VENDORS:
                    try:
                        result = await capture_real_vendor(
                            session, vendor, today,
                            anthropic_client, fallback_log,
                            emit_event=emit_event,
                        )
                        pulled_rows.extend(result["rows"])
                    except Exception as e:
                        pull_failures.append({
                            "vendor": vendor["name"], "error": str(e),
                        })
                        emit_event({
                            "step": "pull",
                            "vendor": vendor["name"],
                            "tool": "search_engine",
                            "status": "failed",
                            "error": str(e),
                        })
    except Exception as e:
        # MCP session itself failed to open — fatal for the pull step.
        emit_event({
            "step": "pull", "phase": "session_failed", "error": str(e),
        })
        pull_failures.append({"vendor": "<mcp-session>", "error": str(e)})

    # Veridian's staged continuation row (no MCP needed; demo fixture).
    veridian_row = build_veridian_open_roles_row(today)
    pulled_rows.append(veridian_row)
    emit_event({
        "step": "pull",
        "vendor": "Veridian Pay",
        "tool": "staged-fixture",
        "class": "open_roles",
        "status": "done",
        "results": 1,
        "duration_ms": 0,
        "path": "staged",
        "note": "demo vendor — value continues the hiring-freeze arc",
    })

    fallback_count = sum(
        1 for ev in fallback_log
        if "scrape_as_markdown" in ev.get("path", "")
    )

    emit_event({
        "step": "pull", "phase": "done",
        "rows_pulled": len(pulled_rows),
        "failures": len(pull_failures),
        "fallback_calls": fallback_count,
    })

    # ===== STEP 2: CLEAN ================================================
    emit_event({"step": "clean", "phase": "start"})

    # Event candidates are the only rows that go through the validator gate.
    # Sentiment + news_volume + open_roles rows pass through untouched.
    event_metrics = ("legal_event", "leadership_change")
    candidates = [r for r in pulled_rows if r["metric"] in event_metrics]
    pass_through = [r for r in pulled_rows if r["metric"] not in event_metrics]

    kept_events: list[dict] = []
    rejected_events: list[dict] = []

    if not candidates:
        emit_event({"step": "clean", "phase": "noop",
                    "reason": "no event candidates to validate"})
    elif anthropic_client is None:
        # No AI gate — keep all candidates with a transparent note.
        kept_events = candidates
        for cand in candidates:
            emit_event({
                "step": "clean",
                "vendor": cand["vendor_name"],
                "metric": cand["metric"],
                "verdict": "kept",
                "reason": "no validator (ANTHROPIC_API_KEY unset)",
                "title": cand["value"][:120],
            })
    else:
        for cand in candidates:
            title = cand.get("value") or ""
            try:
                result = validate_event(
                    anthropic_client,
                    cand["vendor_name"],
                    cand["metric"],
                    title,
                )
                if result.valid:
                    kept_events.append(cand)
                    verdict = "kept"
                else:
                    rejected_events.append({"row": cand, "reason": result.reason})
                    verdict = "rejected"
                emit_event({
                    "step": "clean",
                    "vendor": cand["vendor_name"],
                    "metric": cand["metric"],
                    "verdict": verdict,
                    "reason": result.reason,
                    "title": title[:120],
                })
            except Exception as e:
                # Defensive: validator error → reject (safer for trust contract).
                rejected_events.append({
                    "row": cand, "reason": f"validator error: {e!s}",
                })
                emit_event({
                    "step": "clean",
                    "vendor": cand["vendor_name"],
                    "metric": cand["metric"],
                    "verdict": "rejected",
                    "reason": f"validator error: {e!s}",
                    "title": title[:120],
                })

    rows_to_write = pass_through + kept_events
    emit_event({
        "step": "clean", "phase": "done",
        "kept": len(kept_events),
        "rejected": len(rejected_events),
        "candidates": len(candidates),
    })

    # ===== DEDUP GUARD (event rows only) ================================
    # Score-inflation guard: legal_event / leadership_change rows that
    # already exist in Airtable for the same (vendor, metric, source_url)
    # triple are skipped to stop the daily agent from re-promoting an
    # article we already counted. Time-series readings (sentiment, volume,
    # open_roles, headcount) intentionally bypass — those are point-in-time
    # observations, not events, so duplicate-key semantics differ.
    #
    # One bulk fetch + in-memory set is cheaper than filterByFormula per
    # candidate. Within-batch duplicates also collapse (the key is added
    # to the set as we go).
    event_metrics_set = set(event_metrics)
    events_in_writeset = [r for r in rows_to_write if r["metric"] in event_metrics_set]
    non_events_in_writeset = [r for r in rows_to_write if r["metric"] not in event_metrics_set]
    dedup_skipped: list[dict] = []

    if events_in_writeset:
        existing_keys: set[tuple[str, str, str]] = set()
        try:
            existing = table.all(
                fields=["vendor_name", "metric", "source_url"],
                formula="OR({metric}='legal_event', {metric}='leadership_change')",
            )
            for rec in existing:
                f = rec.get("fields", {})
                existing_keys.add((
                    f.get("vendor_name", ""),
                    f.get("metric", ""),
                    f.get("source_url", ""),
                ))
        except Exception as e:
            emit_event({
                "step": "promote",
                "phase": "dedup_lookup_failed",
                "error": str(e),
                "note": "proceeding without dedup — all event rows will be written",
            })
            existing_keys = set()

        deduped_events: list[dict] = []
        for r in events_in_writeset:
            key = (r["vendor_name"], r["metric"], r.get("source_url", ""))
            if key in existing_keys:
                dedup_skipped.append(r)
                emit_event({
                    "step": "promote",
                    "vendor": r["vendor_name"],
                    "metric": r["metric"],
                    "status": "deduplicated",
                    "reason": "existing row matches vendor+metric+source_url",
                    "title": (r.get("value") or "")[:120],
                })
            else:
                deduped_events.append(r)
                existing_keys.add(key)  # collapse within-batch duplicates too
        rows_to_write = non_events_in_writeset + deduped_events

    # ===== STEP 3: PROMOTE ==============================================
    emit_event({
        "step": "promote", "phase": "start",
        "rows_to_write": len(rows_to_write),
        "events_deduplicated": len(dedup_skipped),
    })

    rows_written_total = 0
    promote_failures: list[dict] = []

    # Group by vendor so per-vendor write confirmations can stream out.
    by_vendor: dict[str, list[dict]] = {}
    for row in rows_to_write:
        by_vendor.setdefault(row["vendor_name"], []).append(row)

    for vendor_name, rows in by_vendor.items():
        try:
            created = table.batch_create(rows, typecast=True)
            rows_written_total += len(created)
            emit_event({
                "step": "promote",
                "vendor": vendor_name,
                "status": "done",
                "rows_written": len(created),
            })
        except Exception as e:
            promote_failures.append({
                "vendor": vendor_name, "error": str(e),
            })
            emit_event({
                "step": "promote",
                "vendor": vendor_name,
                "status": "failed",
                "rows_attempted": len(rows),
                "error": str(e),
            })

    elapsed = round(time.monotonic() - start, 1)

    summary = {
        "rows_written": rows_written_total,
        "events_kept": len(kept_events),
        "events_rejected": len(rejected_events),
        "events_deduplicated": len(dedup_skipped),
        "fallback_calls": fallback_count,
        "elapsed_seconds": elapsed,
        "capture_date": today,
        "failures": pull_failures + promote_failures,
    }

    emit_event({"step": "promote", "phase": "done",
                "rows_written": rows_written_total,
                "failures": len(promote_failures)})
    emit_event({"step": "complete", "summary": summary})
    return summary
