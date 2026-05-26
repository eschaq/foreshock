import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from foreshock.api import (
    all_vendors_overview,
    clear_summary_cache,
    vendor_detail,
)
from foreshock.live_pull import (
    LIVE_PULL_QUERY,
    LIVE_PULL_VENDOR,
    reset_live_pull_rows,
    stream_live_pull,
)
from foreshock.report import build_vendor_report_pdf

app = FastAPI(title="Foreshock API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health():
    return {"status": "foreshock api up"}


@app.get("/vendors")
def vendors():
    """Dashboard grid: all 6 vendors with score, state, sparkline trajectory."""
    return {"vendors": all_vendors_overview()}


@app.get("/vendors/{name}")
def vendor(name: str, refresh: bool = False):
    """Detail panel: full payload incl AI summary + cited sources."""
    detail = vendor_detail(name, force_refresh=refresh)
    if "error" in detail:
        raise HTTPException(status_code=404, detail=detail["error"])
    return detail


@app.post("/cache/summaries/clear")
def clear_cache():
    return {"cleared": clear_summary_cache()}


@app.get("/vendors/{name}/report.pdf")
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


@app.get("/status")
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


@app.get("/live-pull/stream")
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


@app.post("/live-pull/reset")
def live_pull_reset():
    """Delete every row tagged `live-pull-beat:`. For rehearsal cycles."""
    return {"deleted": reset_live_pull_rows()}
