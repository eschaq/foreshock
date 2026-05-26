from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from foreshock.api import (
    all_vendors_overview,
    clear_summary_cache,
    vendor_detail,
)

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
