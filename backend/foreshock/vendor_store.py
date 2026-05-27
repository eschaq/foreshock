"""
Vendor configuration store — system vendors (hardcoded) + user-added
vendors (Airtable `vendor_config` table).

Two-tier design:
  - System vendors live in code (`SYSTEM_DASHBOARD_VENDORS`, `SYSTEM_REAL_VENDORS`).
    These never go to vendor_config; they can't be removed via the UI.
  - User-added vendors live in Airtable's `vendor_config` table. They
    appear on the dashboard alongside system vendors and can be removed
    (soft delete via is_active=false). Signal history is preserved.

Why this split. Keeping the 6 existing vendors hardcoded means the
dashboard keeps working even if the vendor_config table is missing,
empty, or unreachable. Add/remove flows degrade gracefully — a missing
table only breaks the add path, not the existing dashboard.

Airtable `vendor_config` schema (user must create this table — see
`SETUP_NOTES` below):
  name           single line  (primary)
  vendor_type    single line
  is_demo        checkbox     (default false — user vendors are real)
  cik            single line  (10-digit zero-padded SEC CIK, optional)
  ticker         single line  (e.g. "SNOW", optional)
  website        URL          (optional)
  is_active      checkbox     (default true; soft-delete flips to false)
  added_at       single line  (ISO date string)
  notes          long text    (optional)
"""
from __future__ import annotations

import os
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pyairtable import Api

# Re-exported so existing callers (capture.py, agent.py) keep working
# while we migrate them. SYSTEM_REAL_VENDORS shadows REAL_VENDORS — same
# data, lifted here so this module is the single source of truth for
# "what does the dashboard show" and "what does the agent capture".
from .capture import REAL_VENDORS as SYSTEM_REAL_VENDORS

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AT_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AT_BASE = os.environ.get("AIRTABLE_BASE_ID", "").split("/")[0]
VENDOR_CONFIG_TABLE = "vendor_config"


# System vendors that appear on the dashboard. Veridian is the demo;
# the rest are the real ones we always monitor. User-added vendors are
# merged in on top of this list at read time.
SYSTEM_DASHBOARD_VENDORS: list[dict] = [
    {"name": "Veridian Pay", "type": "Payments/BaaS", "is_demo": True,  "cik": None},
    {"name": "Twilio",       "type": "Comms/2FA",    "is_demo": False, "cik": "0001403708"},
    {"name": "Stripe",       "type": "Payments",     "is_demo": False, "cik": None},
    {"name": "Plaid",        "type": "Bank Data",    "is_demo": False, "cik": None},
    {"name": "Snowflake",    "type": "Data Infra",   "is_demo": False, "cik": "0001640147"},
    {"name": "AWS",          "type": "Cloud Infra",  "is_demo": False, "cik": "0001018724"},
]


SETUP_NOTES = """\
The user-add flow requires an Airtable table named `vendor_config` in
the same base as `signals`. Create it with these fields:

  name (single line)        vendor_type (single line)
  is_demo (checkbox)        cik (single line)
  ticker (single line)      website (URL)
  is_active (checkbox)      added_at (single line)
  notes (long text)

Until the table exists, GET /vendors works (system vendors only),
POST /vendors returns a 503 with this hint, and DELETE /vendors/{name}
returns 404 (since no user vendor can exist without the table).
"""


# ---------------------------------------------------------------------------
# Airtable handle (lazy, cached, fault-tolerant)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _table_or_none():
    """Returns the vendor_config table handle or None if the base/key
    is unset. Does NOT verify the table actually exists — that's checked
    on first use (404 surfaces from pyairtable)."""
    if not AT_KEY or not AT_BASE:
        return None
    return Api(AT_KEY).table(AT_BASE, VENDOR_CONFIG_TABLE)


def _is_missing_table_error(exc: Exception) -> bool:
    """Heuristic: pyairtable raises HTTPError with 'TABLE_NOT_FOUND' or
    similar in the message when the table doesn't exist."""
    s = str(exc).upper()
    return "NOT_FOUND" in s or "404" in s


# ---------------------------------------------------------------------------
# Read: user-added vendors (cached briefly to avoid hammering Airtable)
# ---------------------------------------------------------------------------

_user_vendors_cache: list[dict] | None = None
_user_vendors_cache_ts: float = 0.0
_USER_CACHE_TTL = 30.0  # seconds — dashboard reloads should feel snappy


def list_user_vendors(force_refresh: bool = False) -> list[dict]:
    """Active user-added vendors. Returns [] if table missing/empty/unreachable.
    Cached for 30s; invalidated by add/remove."""
    global _user_vendors_cache, _user_vendors_cache_ts
    now = time.monotonic()
    if (
        not force_refresh
        and _user_vendors_cache is not None
        and (now - _user_vendors_cache_ts) < _USER_CACHE_TTL
    ):
        return _user_vendors_cache

    table = _table_or_none()
    if table is None:
        _user_vendors_cache = []
        _user_vendors_cache_ts = now
        return []

    try:
        records = table.all(formula="{is_active}=TRUE()")
    except Exception as e:
        if _is_missing_table_error(e):
            # Table not created yet — degrade silently
            _user_vendors_cache = []
            _user_vendors_cache_ts = now
            return []
        raise

    vendors: list[dict] = []
    for r in records:
        f = r.get("fields", {})
        name = (f.get("name") or "").strip()
        if not name:
            continue
        vendors.append({
            "name": name,
            "type": (f.get("vendor_type") or "Other").strip(),
            "is_demo": bool(f.get("is_demo", False)),
            "cik": (f.get("cik") or "").strip() or None,
            "ticker": (f.get("ticker") or "").strip() or None,
            "website": (f.get("website") or "").strip() or None,
            "_record_id": r["id"],
        })
    _user_vendors_cache = vendors
    _user_vendors_cache_ts = now
    return vendors


def _invalidate_cache() -> None:
    global _user_vendors_cache_ts
    _user_vendors_cache_ts = 0.0


# ---------------------------------------------------------------------------
# Merged views — what the dashboard and capture pipeline actually iterate
# ---------------------------------------------------------------------------

def _system_names() -> set[str]:
    return {v["name"] for v in SYSTEM_DASHBOARD_VENDORS}


def get_dashboard_vendors() -> list[dict]:
    """System + user-added active vendors, in dashboard order. Each
    dict carries `is_removable` so the UI knows which cards get the X."""
    system = [
        {**v, "is_removable": False, "_source": "system"}
        for v in SYSTEM_DASHBOARD_VENDORS
    ]
    user = [
        {**v, "is_removable": True, "_source": "user"}
        for v in list_user_vendors()
        if v["name"] not in _system_names()  # never let user-added shadow system
    ]
    return system + user


def get_capture_vendors() -> list[dict]:
    """Vendors the daily agent should pull signals for. System reals +
    active non-demo user-added vendors. Demo vendors (Veridian) are
    excluded — their data is staged separately."""
    out: list[dict] = list(SYSTEM_REAL_VENDORS)
    sys_names = {v["name"] for v in out}
    for v in list_user_vendors():
        if v["is_demo"]:
            continue
        if v["name"] in sys_names:
            continue
        out.append({
            "name": v["name"],
            "type": v["type"],
            # User-added vendors have no disambiguated Google query — fall
            # back to the bare name. Operators can refine via vendor_type
            # later if noise becomes a problem.
            "query_name": v["name"],
            "cik": v["cik"],
        })
    return out


# ---------------------------------------------------------------------------
# Write: add / remove
# ---------------------------------------------------------------------------

class VendorStoreError(Exception):
    """Raised for user-actionable failures (table missing, dup name, etc)."""


def add_user_vendor(
    name: str,
    vendor_type: str,
    cik: Optional[str] = None,
    ticker: Optional[str] = None,
    website: Optional[str] = None,
) -> dict:
    """Insert one row in vendor_config. Returns the created record fields.
    Raises VendorStoreError on validation / setup problems."""
    name = (name or "").strip()
    if not name:
        raise VendorStoreError("name is required")
    if not vendor_type:
        raise VendorStoreError("vendor_type is required")

    # Block adding a system vendor by name (clearer than letting it silently
    # be shadowed at read time).
    if name in _system_names():
        raise VendorStoreError(
            f"'{name}' is a system vendor (already monitored, not user-removable)"
        )

    # Prevent duplicates among user-added vendors.
    for existing in list_user_vendors(force_refresh=True):
        if existing["name"].lower() == name.lower():
            raise VendorStoreError(
                f"'{name}' is already in the monitored list"
            )

    table = _table_or_none()
    if table is None:
        raise VendorStoreError(
            "Airtable not configured (AIRTABLE_API_KEY / AIRTABLE_BASE_ID unset)"
        )

    row: dict[str, Any] = {
        "name": name,
        "vendor_type": vendor_type,
        "is_demo": False,
        "is_active": True,
        "added_at": date.today().isoformat(),
    }
    if cik:
        row["cik"] = cik
    if ticker:
        row["ticker"] = ticker
    if website:
        row["website"] = website

    try:
        created = table.create(row, typecast=True)
    except Exception as e:
        if _is_missing_table_error(e):
            raise VendorStoreError(
                "Airtable table 'vendor_config' does not exist. " + SETUP_NOTES
            )
        raise

    _invalidate_cache()
    return {**row, "_record_id": created["id"]}


def deactivate_user_vendor(name: str) -> dict:
    """Soft-delete: set is_active=false. Signal history preserved.
    Returns {name, was_active, rows_preserved} or raises VendorStoreError."""
    name = (name or "").strip()
    if not name:
        raise VendorStoreError("name is required")

    if name in _system_names():
        raise VendorStoreError(
            f"'{name}' is a system vendor and cannot be removed"
        )

    matches = [
        v for v in list_user_vendors(force_refresh=True)
        if v["name"].lower() == name.lower()
    ]
    if not matches:
        raise VendorStoreError(f"'{name}' is not in the monitored list")

    target = matches[0]
    table = _table_or_none()
    if table is None:
        raise VendorStoreError("Airtable not configured")

    table.update(target["_record_id"], {"is_active": False}, typecast=True)
    _invalidate_cache()

    return {
        "name": target["name"],
        "was_active": True,
        "deactivated": True,
        "rows_preserved": True,
        "note": (
            "Vendor deactivated. Existing signal rows in `signals` table "
            "are preserved for audit history."
        ),
    }
