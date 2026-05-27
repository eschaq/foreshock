"""
SEC company-tickers lookup — for the add-vendor flow's "type a name,
get CIK + ticker" experience.

Why direct, not Bright Data MCP. Same blocker as the EDGAR module:
Bright Data's `scrape_as_markdown` returns empty for JSON endpoints
and SEC HTML is robots-blocked at the current tier. SEC's
`company_tickers.json` is one ~1MB blob that maps every public-company
name to CIK and ticker, designed for programmatic access.

Caching strategy. Fetch once, hold in memory for 24h. The file is
stable (companies don't change CIK). One cold-start fetch on the first
lookup; subsequent lookups are O(N=~10K) substring scans against the
in-memory list — ~10ms even unindexed. Far better than per-query SEC
search calls (which require multiple round-trips + parsing).

Matching strategy. Three tiers ranked by confidence:
  1.00  exact title match
  0.90  title starts with query
  0.70  query appears anywhere in title
Within a tier, shorter titles rank higher (closer match by length).
"""
from __future__ import annotations

import time
from typing import Optional

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_USER_AGENT = "Foreshock/1.0 contact@foreshock.ai"
SEC_REQUEST_TIMEOUT = 15.0
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


# In-memory cache. Module-global because there's only one universe of
# SEC-listed companies and we want it shared across all requests.
_tickers_cache: list[dict] | None = None
_tickers_cache_ts: float = 0.0


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _fetch_tickers() -> list[dict]:
    """Single GET to SEC. Returns list[{cik, ticker, title}]."""
    resp = requests.get(
        TICKERS_URL,
        headers={
            "User-Agent": SEC_USER_AGENT,
            "Accept": "application/json",
        },
        timeout=SEC_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json()
    # SEC ships this as a dict keyed by string indices; flatten.
    out: list[dict] = []
    for v in raw.values():
        cik_int = v.get("cik_str")
        ticker = v.get("ticker", "")
        title = v.get("title", "")
        if cik_int is None or not title:
            continue
        out.append({
            # 10-digit zero-padded CIK matches the format used in REAL_VENDORS
            # and edgar.py (SUBMISSIONS_URL expects padded).
            "cik": str(cik_int).zfill(10),
            "ticker": ticker.strip().upper(),
            "title": title.strip(),
        })
    return out


def _get_tickers(force_refresh: bool = False) -> list[dict]:
    """Cached accessor. First call fetches (~1-2s); subsequent <1ms."""
    global _tickers_cache, _tickers_cache_ts
    now = time.monotonic()
    if (
        not force_refresh
        and _tickers_cache is not None
        and (now - _tickers_cache_ts) < CACHE_TTL_SECONDS
    ):
        return _tickers_cache
    _tickers_cache = _fetch_tickers()
    _tickers_cache_ts = now
    return _tickers_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_company(query: str, top_n: int = 3) -> list[dict]:
    """
    Fuzzy-match a company name against SEC's public-company universe.

    Returns up to `top_n` matches, each shaped:
      {name: str, cik: str (10-digit padded), ticker: str, match_confidence: float}

    Empty query or no matches -> empty list. The caller decides whether
    to surface "private company - proceed without EDGAR" vs an error.
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    try:
        companies = _get_tickers()
    except Exception:
        # Honest degradation per spec: if SEC is unreachable, return
        # empty list so the user can proceed with manual entry.
        return []

    exact: list[dict] = []
    starts: list[dict] = []
    contains: list[dict] = []

    for c in companies:
        t = c["title"].lower()
        if t == q:
            exact.append(c)
        elif t.startswith(q):
            starts.append(c)
        elif q in t:
            contains.append(c)

    # Within each tier, shorter title => closer match.
    starts.sort(key=lambda c: len(c["title"]))
    contains.sort(key=lambda c: len(c["title"]))

    confidence_map = [(exact, 1.00), (starts, 0.90), (contains, 0.70)]
    matches: list[dict] = []
    for tier, conf in confidence_map:
        for c in tier:
            matches.append({
                "name": c["title"],
                "cik": c["cik"],
                "ticker": c["ticker"],
                "match_confidence": conf,
            })
            if len(matches) >= top_n:
                return matches
    return matches


def warm_cache() -> dict:
    """Optional: pre-load tickers so the first lookup is fast.
    Returns {loaded: int, source: 'sec.gov'} or {error: str}."""
    try:
        n = len(_get_tickers(force_refresh=True))
        return {"loaded": n, "source": "sec.gov"}
    except Exception as e:
        return {"error": str(e)}
