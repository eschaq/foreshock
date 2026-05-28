import asyncio
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from foreshock.api import (
    add_vendor_payload,
    all_vendors_overview,
    clear_summary_cache,
    fleet_summary_payload,
    lookup_vendor_payload,
    remove_vendor_payload,
    trust_audit_payload,
    vendor_detail,
)
from foreshock.vendor_store import VendorStoreError
from foreshock.live_pull import (
    LIVE_PULL_QUERY,
    LIVE_PULL_VENDOR,
    reset_live_pull_rows,
    stream_live_pull,
)
from foreshock.report import build_ict_register_pdf, build_vendor_report_pdf

app = FastAPI(title="Foreshock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# All backend routes live under /api so the React app can be served from the
# same origin (StaticFiles at /) without colliding with API paths.
router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "foreshock api up"}


@router.get("/vendors")
def vendors():
    """Dashboard grid: system + active user-added vendors with score, state,
    sparkline trajectory, is_removable flag."""
    return {"vendors": all_vendors_overview()}


# --- Vendor management (Wave 3) ---------------------------------------------
# /vendors/lookup MUST come before /vendors/{name} so FastAPI doesn't
# treat "lookup" as a vendor name.

@router.get("/vendors/lookup")
def vendor_lookup(name: str = "", top_n: int = 3):
    """Live CIK + ticker lookup against SEC's public-company universe.
    Returns up to 3 fuzzy matches with confidence score. Empty list for
    private companies / unmatched queries / SEC outage (graceful degrade)."""
    return lookup_vendor_payload(name, top_n=top_n)


class AddVendorRequest(BaseModel):
    name: str
    vendor_type: str
    cik: str | None = None
    ticker: str | None = None
    website: str | None = None


@router.post("/vendors")
def add_vendor(req: AddVendorRequest):
    """Add a vendor to the monitored list. Persists to `vendor_config` in
    Airtable. Vendor appears on dashboard immediately at STABLE; signals
    flow in on the next agent run (no auto-pull on add — honesty)."""
    try:
        return add_vendor_payload(
            name=req.name,
            vendor_type=req.vendor_type,
            cik=req.cik,
            ticker=req.ticker,
            website=req.website,
        )
    except VendorStoreError as e:
        # 503 when the Airtable table is missing (operator action needed);
        # 400 for ordinary validation/duplicate errors.
        msg = str(e)
        if "does not exist" in msg or "not configured" in msg:
            raise HTTPException(status_code=503, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.delete("/vendors/{name}")
def remove_vendor(name: str):
    """Soft-delete a user-added vendor (sets is_active=false). Signal
    history in the `signals` table is preserved. System vendors cannot
    be removed via this endpoint (returns 400)."""
    try:
        return remove_vendor_payload(name)
    except VendorStoreError as e:
        msg = str(e)
        if "not in the monitored list" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.get("/vendors/{name}")
def vendor(name: str, refresh: bool = False):
    """Detail panel: full payload incl AI summary + cited sources."""
    detail = vendor_detail(name, force_refresh=refresh)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return detail


@router.get("/fleet/summary")
def fleet_summary(refresh: bool = False):
    """Dashboard fleet-overview card: 3-4 sentence portfolio briefing."""
    return fleet_summary_payload(force_refresh=refresh)


@router.post("/cache/summaries/clear")
def clear_cache():
    return {"cleared": clear_summary_cache()}


@router.get("/trust/audit")
def trust_audit():
    """Fleet-wide citation audit. Powers the dashboard trust indicator.
    Returns 0 unresolved when every AI claim resolves to a numbered
    source — the trust contract holding end-to-end."""
    return trust_audit_payload()


@router.get("/vendors/{name}/report.pdf")
def vendor_report_pdf(name: str):
    """One-click DORA evidence-artifact export. Returns a real PDF."""
    try:
        pdf = build_vendor_report_pdf(name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    safe_name = name.replace(" ", "_").replace("/", "_")
    from datetime import date as _d
    filename = f"foreshock_{safe_name}_{_d.today().isoformat()}.pdf"
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/export/ict-register")
def export_ict_register():
    """One-document ICT register covering every monitored vendor.

    Cover page (title, scope, fleet summary, citation audit, vendor TOC)
    + per-vendor sections (reuses the single-vendor template, page break
    between vendors) + shared methodology appendix at the end. The
    page-footer carries the FLEET-wide audit verdict.

    DORA Article 28-aligned format. Slower than the single-vendor PDF —
    fetches detail for every vendor (cached when warm).
    """
    try:
        pdf = build_ict_register_pdf()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    from datetime import date as _d
    filename = f"foreshock_ict_register_{_d.today().isoformat()}.pdf"
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/status")
def status():
    """Subtle activity-indicator data. Always-on monitoring claim."""
    vendors = all_vendors_overview()
    latest_capture = max(
        (v["latest_capture"] for v in vendors if v["latest_capture"]),
        default=None,
    )
    return {
        "monitoring_active": True,
        "vendor_count": len(vendors),
        "signal_count_total": sum(v["signal_count"] for v in vendors),
        "last_capture": latest_capture,
        "live_pull_query": LIVE_PULL_QUERY,
        "live_pull_vendor": LIVE_PULL_VENDOR["name"],
    }


@router.get("/live-pull/stream")
async def live_pull_stream(mode: str = "live", save_seed: bool = False):
    """
    SSE stream of the live pull. The honesty boundary:
      mode=live    -> emits real mcp_call/mcp_result events with timing
      mode=seeded  -> emits fixture_read/fixture_loaded events
                      labeled cached_replay. Never fakes an mcp_call.
    """
    if mode not in ("live", "seeded"):
        raise HTTPException(400, "mode must be 'live' or 'seeded'")

    async def gen():
        try:
            async for ev in stream_live_pull(
                mode=mode, write=True, save_seed=save_seed
            ):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'
        yield 'data: {"type": "stream_end"}\n\n'

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/live-pull/reset")
def live_pull_reset():
    """Delete every row tagged `live-pull-beat:`. For rehearsal cycles."""
    return {"deleted": reset_live_pull_rows()}


# ---------------------------------------------------------------------------
# Unattended daily agent — Pull → Clean → Promote pipeline.
# Triggered by the UI chord OR by Railway cron (see railway.toml).
# Per-step progress events stream out via SSE.
# ---------------------------------------------------------------------------

_agent_jobs: dict[str, dict] = {}


@router.post("/agent/run")
async def agent_run():
    """
    Kick off a Pull → Clean → Promote run async. Returns the job_id
    immediately so the caller can open the SSE stream and watch progress.
    """
    from foreshock.agent import run_agent_pipeline

    job_id = uuid.uuid4().hex[:12]
    queue: asyncio.Queue = asyncio.Queue()
    _agent_jobs[job_id] = {"queue": queue, "status": "running"}

    def emit_event(event: dict) -> None:
        # Synchronous-safe queue insert from any context.
        queue.put_nowait(event)

    async def runner():
        try:
            await run_agent_pipeline(emit_event)
        except Exception as e:
            queue.put_nowait({"step": "error", "message": str(e)})
        finally:
            _agent_jobs[job_id]["status"] = "done"
            queue.put_nowait(None)  # sentinel: closes the SSE stream

    asyncio.create_task(runner())
    return {"job_id": job_id}


@router.get("/agent/stream/{job_id}")
async def agent_stream(job_id: str):
    """SSE stream of per-step events for a previously-started agent job."""
    job = _agent_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    queue: asyncio.Queue = job["queue"]

    async def gen():
        try:
            while True:
                # Long timeout — agent runs can be 60–120s. Timeout is a
                # safety net so the stream doesn't hang forever if the
                # runner crashes silently.
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    yield 'data: {"type": "timeout"}\n\n'
                    break
                if event is None:
                    yield 'data: {"type": "stream_end"}\n\n'
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            # Clean up the job entry once the stream closes (success, timeout,
            # or client disconnect). Prevents memory growth on long-lived servers.
            _agent_jobs.pop(job_id, None)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


app.include_router(router)


# ---------------------------------------------------------------------------
# Frontend: serve the built React app from /. The catch-all runs after all
# /api/* routes; it returns real asset files when they exist on disk and
# falls back to index.html otherwise so client-side routes survive
# hard-refreshes.
# ---------------------------------------------------------------------------

DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    candidate = DIST_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(DIST_DIR / "index.html")
