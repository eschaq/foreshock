"""
The demo's hero moment (act 2) + the --live/--seeded safety net.

Pipeline:
    fetch real-vendor MCP response   <-- THE ONLY THING THAT SWITCHES
    build real-vendor Type 2 rows
    build Veridian finale rows (always — the demo's scripted beat)
    APPEND-write to Airtable
    dashboard re-scores on next refresh

The Veridian finale (a lawsuit + the 2nd C-suite departure, after the
existing CTO exit on 2026-05-21) is deliberately NOT staged in the
historical capture so the live pull is the moment that lands it.

Modes:
    live    — real MCP search_engine call (fast tool, ~2-4s)
    seeded  — reads a cached fixture; zero network dependency

Both modes write the same Type 2 rows. Same UI flow. Same Claude
summary path. The switch only affects WHERE the real-vendor MCP
response comes from — a tight boundary by design.

Every row this module writes is tagged `live-pull-beat:` in notes so
rehearsal cycles can be cleanly undone via `reset_live_pull_rows()`.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pyairtable import Api

from .capture import score_sentiment_heuristic

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BD_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN", "")
AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AT_BASE = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
MCP_URL = f"https://mcp.brightdata.com/mcp?token={BD_TOKEN}"

TABLE_NAME = "signals"
TOP_N = 4

# Provenance tag on every row this module writes. Used by reset_live_pull_rows
# to identify which rows came from a live-pull rehearsal vs the historical
# capture. NOT a user-facing label.
NOTES_TAG = "live-pull-beat"

# Cached fixture for --seeded mode. Same shape as a real `search_engine`
# response (the JSON-in-text-block parsed payload).
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "seeded_real_pull.json"

# The one fast vendor pull for the live moment. Single search_engine call,
# 2-4s on a base tool. Real-vendor proof that this works on live companies.
LIVE_PULL_VENDOR = {"name": "Stripe", "type": "Payments"}
LIVE_PULL_QUERY = "Stripe news after:2026-01-01"


# ---------------------------------------------------------------------------
# Veridian finale — the demo's scripted beat
# ---------------------------------------------------------------------------

def _veridian_finale_rows(capture_date: str) -> list[dict]:
    """The two rows that land Veridian's deliberately-unstaged finale."""
    base = {
        "capture_date": capture_date,
        "vendor_name": "Veridian Pay",
        "vendor_type": "Payments/BaaS",
        "is_demo_vendor": True,
        "unit": "event",
        "sentiment": "negative",
        "source_url": "DEMO-SCENARIO-FINALE",
    }
    return [
        {
            **base,
            "metric": "legal_event",
            "value": "Class action filed against Veridian Pay over alleged "
                     "customer data exposure",
            "notes": (
                f"{NOTES_TAG}: lawsuit filed — class action alleges customer "
                f"data exposure (staged demo finale — the legal dimension "
                f"the demo deliberately lands)"
            ),
        },
        {
            **base,
            "metric": "leadership_change",
            "value": "Veridian Pay CEO Marisha Chen departs",
            "notes": (
                f"{NOTES_TAG}: Veridian Pay CEO Marisha Chen departs amid "
                f"mounting pressure (staged demo finale — second C-suite "
                f"exit, follows CTO departure 2026-05-21)"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# The fetch boundary — the ONLY thing that switches on mode
# ---------------------------------------------------------------------------

async def _fetch_organic_live() -> dict:
    """Real MCP search_engine call. Returns parsed JSON payload."""
    if not BD_TOKEN:
        raise RuntimeError(
            "BRIGHTDATA_API_TOKEN not set — cannot run --live"
        )
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_engine",
                arguments={"query": LIVE_PULL_QUERY, "engine": "google"},
            )
    if result.isError:
        raise RuntimeError(f"MCP error: {result.content}")
    return json.loads(result.content[0].text)


def _fetch_organic_seeded() -> dict:
    """Read the cached MCP response from disk — zero network."""
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"seeded fixture not found at {FIXTURE_PATH}. "
            f"Run --live --save-seed once to capture one."
        )
    return json.loads(FIXTURE_PATH.read_text())


async def _fetch_organic(mode: Literal["live", "seeded"]) -> dict:
    """The mode switch. Identical downstream processing for both."""
    if mode == "live":
        return await _fetch_organic_live()
    return _fetch_organic_seeded()


def _save_fixture(payload: dict) -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Row construction (same downstream for both modes)
# ---------------------------------------------------------------------------

def _real_vendor_rows_from_payload(
    payload: dict, capture_date: str
) -> list[dict]:
    organic = payload.get("organic", [])
    vendor = LIVE_PULL_VENDOR
    base = {
        "capture_date": capture_date,
        "vendor_name": vendor["name"],
        "vendor_type": vendor["type"],
        "is_demo_vendor": False,
    }
    sentiment_rows: list[dict] = []
    seen_urls: set[str] = set()
    for item in organic[:TOP_N]:
        link = (item.get("link") or "").strip()
        if not link or link in seen_urls:
            continue
        seen_urls.add(link)
        title = (item.get("title") or "").strip()
        desc = (item.get("description") or "").strip()
        value, label = score_sentiment_heuristic(f"{title} {desc}")
        sentiment_rows.append({
            **base,
            "metric": "news_sentiment",
            "value": str(value),
            "unit": "score",
            "source_url": link,
            "sentiment": label,
            "notes": f"{NOTES_TAG}: [live-real-pull] {title}"[:255],
        })
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
        "notes": (
            f"{NOTES_TAG}: [live-real-pull] unique_urls={len(seen_urls)} "
            f"for {vendor['name']}"
        ),
    }
    return sentiment_rows + [volume_row]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class LivePullResult:
    mode: Literal["live", "seeded"]
    capture_date: str
    real_vendor_rows: list[dict] = field(default_factory=list)
    veridian_rows: list[dict] = field(default_factory=list)
    rows_written_ids: list[str] = field(default_factory=list)
    dry_run: bool = False
    saved_seed: bool = False

    @property
    def total_rows(self) -> int:
        return len(self.real_vendor_rows) + len(self.veridian_rows)


async def run_live_pull(
    mode: Literal["live", "seeded"] = "seeded",
    write: bool = True,
    save_seed: bool = False,
    capture_date: str | None = None,
) -> LivePullResult:
    """
    The hero pull.

    `mode`: "live" -> real MCP call;  "seeded" -> cached fixture.
    `write`: when False, return the planned rows without touching Airtable.
    `save_seed`: when True with mode="live", overwrite the seeded fixture
                 with this response so future --seeded matches reality.
    """
    today = capture_date or date.today().isoformat()
    payload = await _fetch_organic(mode)

    if mode == "live" and save_seed:
        _save_fixture(payload)

    real_rows = _real_vendor_rows_from_payload(payload, today)
    veridian_rows = _veridian_finale_rows(today)
    all_rows = real_rows + veridian_rows

    written: list[str] = []
    if write:
        api = Api(AT_KEY)
        table = api.table(AT_BASE, TABLE_NAME)
        created = table.batch_create(all_rows, typecast=True)
        written = [r["id"] for r in created]

    return LivePullResult(
        mode=mode,
        capture_date=today,
        real_vendor_rows=real_rows,
        veridian_rows=veridian_rows,
        rows_written_ids=written,
        dry_run=(not write),
        saved_seed=(save_seed and mode == "live"),
    )


def reset_live_pull_rows() -> int:
    """
    Delete every row this module has written (tagged `live-pull-beat:`).
    Returns the number deleted. Used for rehearsal cycles — does NOT touch
    historical capture rows, the Veridian staged arc, or audit-promoted rows.
    """
    api = Api(AT_KEY)
    table = api.table(AT_BASE, TABLE_NAME)
    # Airtable's FIND returns position-or-0; >0 means substring present.
    formula = f"FIND('{NOTES_TAG}:', {{notes}}) > 0"
    matches = table.all(formula=formula)
    if not matches:
        return 0
    table.batch_delete([r["id"] for r in matches])
    return len(matches)
