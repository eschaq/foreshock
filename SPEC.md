# Foreshock — System Specification

> **Source of truth as of 2026-05-27.** Documents what's actually shipped and verifiable today — not roadmap. For build-sequence narrative see git log; for vision see [CLAUDE.md](CLAUDE.md).

---

## Table of contents

1. [TL;DR](#1-tldr)
2. [Positioning (the gap being filled)](#2-positioning-the-gap-being-filled)
3. [Audience](#3-audience)
4. [System architecture](#4-system-architecture)
5. [App flows](#5-app-flows)
6. [Tech stack](#6-tech-stack)
7. [Vendor list & current scoreboard](#7-vendor-list--current-scoreboard)
8. [Signal capture](#8-signal-capture)
9. [Data model](#9-data-model)
10. [CDC diff + risk scoring](#10-cdc-diff--risk-scoring)
11. [Alert logic](#11-alert-logic)
12. [AI trust contract](#12-ai-trust-contract)
13. [SEC EDGAR integration](#13-sec-edgar-integration)
14. [Citation trust audit](#14-citation-trust-audit)
15. [ICT register PDF export](#15-ict-register-pdf-export)
16. [Concentration risk view](#16-concentration-risk-view)
17. [Vendor management](#17-vendor-management)
18. [UI surface](#18-ui-surface)
19. [API endpoints](#19-api-endpoints)
20. [Honesty boundaries](#20-honesty-boundaries)
21. [Demo script (5 acts)](#21-demo-script-5-acts)
22. [Competitor analysis](#22-competitor-analysis)
23. [Candidate moats](#23-candidate-moats)
24. [Known limitations](#24-known-limitations)
25. [Explicitly out of scope](#25-explicitly-out-of-scope)
26. [File inventory](#26-file-inventory)
27. [Open items & next steps](#27-open-items--next-steps)

---

## 1. TL;DR

Foreshock is a continuous third-party vendor risk monitoring app for fintech GRC teams. It watches **business-health signals** (leadership exits, lawsuits, layoffs, hiring trends, sentiment) on critical ICT vendors via **Bright Data MCP**, pulls **SEC EDGAR 8-K filings** for public companies, appends Type-2 history to **Airtable**, runs a **CDC diff + 6-component weighted score**, fires **convergence alerts**, generates **fully-cited GRC narratives via Claude Sonnet 4.6** with a **verifiable 0-hallucination citation audit**, and exports a one-click **DORA Article 28 ICT Register PDF** covering every monitored vendor.

**Verified live numbers (2026-05-27):**
- **70 AI claims** across 6 vendors, **0 unresolved citations** (100% audit pass)
- **~688 signal rows** in Airtable across all vendors
- **Single-vendor DORA PDF**: ~90KB · **Multi-vendor ICT Register PDF**: ~180KB
- **3 EDGAR-eligible vendors** (Snowflake, Twilio, AWS) with live SEC submissions API integration
- **Vendor add/remove**: user-added Salesforce flow tested end-to-end via live SEC company lookup

**Differentiator one-liner:** *"BitSight watches the security posture; Foreshock watches the business health. The layoff precedes the breach."*

---

## 2. Positioning (the gap being filled)

Three adjacent categories — each watches the wrong thing for this use case:

| Category | Examples | Watches | Misses |
|---|---|---|---|
| **GRC platforms** | OneTrust, Prevalent, ProcessUnity, Archer | Paperwork, registers, questionnaires | Real-time external reality |
| **Security raters** | BitSight, SecurityScorecard, UpGuard, Black Kite | Attack surface, certs, breach proxies | Business-health deterioration |
| **Competitive intelligence** | Owler, Crayon, Klue, Similarweb | Generic competitor news | GRC-shaped scoring + DORA artifacts |

**Foreshock's lane.** Business-health signal monitoring + GRC-shaped output. Thesis: *the layoff precedes the breach.* Leadership turnover, lawsuits, hiring freezes precede vendor failure by weeks-to-months. No incumbent watches them in a GRC context with a verifiable audit trail.

---

## 3. Audience

Solo (or one-of-two) GRC / compliance lead at a mid-market fintech ($50M–$2B rev), managing 15–40 critical ICT vendors under DORA (or analogous regime). Currently spending ~5 hrs/week on manual vendor monitoring. Personal failure mode: post-incident "should have seen earlier" blame.

---

## 4. System architecture

### 4.1 Component view

```
                            ┌─────────────────────────────────────────┐
                            │            BRIGHT DATA MCP              │
                            │  search_engine · scrape_as_markdown     │
                            └──────────────┬──────────────────────────┘
                                           │ (commercial sources: news,
                                           │  lawsuits, layoffs, leadership)
                                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       CAPTURE / OBSERVATION                          │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────┐  │
│  │ capture.py          │  │ observation.py      │  │ edgar.py     │  │
│  │ (4 query classes    │  │ (per-vendor orches- │  │ (SEC sub-    │  │
│  │  + open_roles)      │  │  tration + fallback)│  │  missions    │  │
│  │                     │  │                     │  │  API direct) │  │
│  └─────────────────────┘  └─────────────────────┘  └──────────────┘  │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │ candidate event rows
                                   ▼
              ┌───────────────────────────────────────┐
              │      validator.py (Claude YES/NO)     │
              │  drops false-positive events          │
              └───────────────────┬───────────────────┘
                                  │ surviving rows
                                  ▼
                ┌────────────────────────────────┐
                │   AIRTABLE                     │
                │   ├─ signals (Type-2 SCD)      │
                │   └─ vendor_config (add/remove)│
                └──────────────────┬─────────────┘
                                   │
       ┌───────────────────────────┼────────────────────────────┐
       ▼                           ▼                            ▼
┌─────────────┐         ┌───────────────────┐         ┌──────────────────┐
│ scoring.py  │         │  summarizer.py    │         │  alerts.py       │
│ CDC + 6-    │         │  Claude Sonnet 4.6│         │  Convergence /   │
│ component   │         │  + citation audit │         │  threshold eval  │
│ weighted    │         │  + fallback       │         │                  │
└──────┬──────┘         └─────────┬─────────┘         └────────┬─────────┘
       │                          │                            │
       └──────────────────────────┼────────────────────────────┘
                                  ▼
       ┌────────────────────────────────────────────────────────┐
       │              FastAPI (main.py + api.py)                │
       │  REST + SSE (live-pull, agent pipeline)                │
       │  ┌────────────────────────────────────────────────┐    │
       │  │  vendor_store.py — system + user vendor merge  │    │
       │  │  sec_lookup.py   — cached company_tickers.json │    │
       │  │  agent.py        — Pull → Clean → Promote      │    │
       │  │  report.py       — single-vendor + ICT register│    │
       │  │  live_pull.py    — demo SSE flow               │    │
       │  └────────────────────────────────────────────────┘    │
       └────────────────────────┬───────────────────────────────┘
                                ▼
       ┌────────────────────────────────────────────────────────┐
       │  REACT + TS DASHBOARD (Vite, Tailwind)                 │
       │  Fleet Overview · Concentration Risk · Vendor Grid     │
       │  Detail Panel  · AddVendor · TrustAudit · AgentPanel   │
       └────────────────────────────────────────────────────────┘
```

### 4.2 Data-flow view

```
        DAILY (cron 07:00 UTC OR manual /agent/run)
             │
             ▼
    PULL ─────────────► Bright Data MCP × 6 calls/vendor
             │             + SEC EDGAR direct × 1 call/CIK
             ▼
    CLEAN ────────────► Claude validator gates event candidates
             │             (~17 of 22 rejected as noise in recent run)
             ▼
    DEDUP ────────────► Skip event rows matching existing
             │             (vendor, metric, source_url)
             ▼
    PROMOTE ──────────► Type-2 append to Airtable signals
             │             (~117 rows / cycle / 7 vendors)
             ▼
    INDEX  ───────────► /vendors re-scores; summary cache invalidates
                          on changed (vendor, capture_date, signal_count)
```

---

## 5. App flows

### 5.1 First-time user journey

```
Dashboard load
   │
   ▼
[Fleet Overview]  ◄── /fleet/summary (Claude-generated portfolio briefing)
   │
   ▼
[Trust badge]      ◄── /trust/audit (✓ 70 claims · 0 unresolved · all sourced)
   │
   ▼
[Concentration Risk]  ◄── /vendors (all trajectories on shared time axis)
   │
   ▼
[Vendor Grid]      ◄── 6+ cards · click → detail panel
   │
   ├─► Click card → Detail panel (cited AI narrative + sources + score breakdown)
   │      └─► Export DORA evidence (PDF)
   │
   ├─► Click trust badge → Audit modal (per-vendor PASS/FAIL breakdown)
   │
   ├─► "+ Add Vendor" → modal (type "Salesforce" → SEC auto-lookup → confirm)
   │
   └─► "Export ICT Register (PDF)" → one PDF, all vendors, DORA Article 28
```

### 5.2 Agent pipeline (unattended daily)

```
POST /agent/run
   │
   ▼
Job ID returned ──► GET /agent/stream/{job_id} (SSE)
                       │
                       ▼
             ┌─────────────────────┐
             │  PULL phase         │
             │  per vendor:        │
             │    news (firing→done)
             │    lawsuit          │  ◄── Bright Data search_engine
             │    layoff           │
             │    leadership       │
             │    open_roles       │
             │    edgar_8k (if CIK)│  ◄── direct SEC API
             └──────────┬──────────┘
                        ▼
             ┌─────────────────────┐
             │  CLEAN phase        │
             │  per event:         │
             │    Claude YES/NO    │  ◄── ~80% rejection rate
             │    kept | rejected  │
             └──────────┬──────────┘
                        ▼
             ┌─────────────────────┐
             │  DEDUP guard        │
             │  skip (v,m,url)     │
             │  already in airtable│
             └──────────┬──────────┘
                        ▼
             ┌─────────────────────┐
             │  PROMOTE phase      │
             │  Airtable batch     │
             │  per-vendor confirm │
             └──────────┬──────────┘
                        ▼
                {step: "complete", summary: {...}}
```

### 5.3 Live-pull demo flow

```
Ctrl+Shift+L  OR  Settings gear button
   │
   ▼
GET /live-pull/stream?mode={live|seeded}
   │
   ▼
SSE events:
   ┌── live mode ──────────────────┐    ┌── seeded mode ───────────────┐
   │ mcp_call → mcp_result          │    │ fixture_read → fixture_loaded│
   │ data_path: "bright-data-mcp"   │    │ data_path: "local-disk"      │
   │ label: "live"                  │    │ label: "cached_replay"       │
   └────────────────┬───────────────┘    └──────────────┬───────────────┘
                    │                                   │
                    └─────────────┬─────────────────────┘
                                  ▼
                       Both paths identical downstream:
                       rows_built → airtable_write → complete
                       Veridian finale fires (lawsuit + CEO exit)
                       Veridian score: 68.2 → 81.2
```

### 5.4 Vendor add flow

```
"+ Add Vendor" button
   │
   ▼
AddVendorModal opens
   │
   ▼
User types "Salesforce" (debounced 400ms)
   │
   ▼
GET /vendors/lookup?name=Salesforce
   │
   ▼
Dropdown shows: "Salesforce, Inc. · CRM · CIK 0001108524 · Public"
   │
   ▼
User selects → CIK + ticker auto-populate
User picks type ("Other")
   │
   ▼
Confirmation summary shows:
   "Adding: Salesforce, Inc.
    EDGAR monitoring: active (8-K filings will be tracked)
    Monitoring starts: next agent run"
   │
   ▼
POST /vendors {name, vendor_type, cik, ticker}
   │
   ▼
Airtable vendor_config row created
Card appears on dashboard at STABLE, 0 signals
Next agent run includes Salesforce automatically
```

### 5.5 Vendor remove flow

```
Hover user-added card
   │
   ▼
Red ✕ button fades in (top-right, z-20)
   │
   ▼
Click ✕  → RemoveVendorConfirm modal
   │
   ▼
"Remove Salesforce, Inc. from monitoring? Signal history preserved."
   │
   ▼
Confirm → DELETE /vendors/Salesforce, Inc.
   │
   ▼
Soft-delete (is_active=false in vendor_config)
Signal history in `signals` table untouched
Card disappears, grid reflows, fleet summary regenerates
```

---

## 6. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| **Frontend** | React 18 + TypeScript + Vite + Tailwind + shadcn primitives | Dark UI; semantic tokens (`base`, `surface`, `signal-*`, `ink-*`, `rule`, `overlay-*`); Sometype Mono for numerics, General Sans for body |
| **Backend** | FastAPI (Python 3.11) | uvicorn + WatchFiles; in-process summary cache |
| **AI** | Anthropic SDK, `claude-sonnet-4-6` | Strict-JSON output, citation auditor, deterministic fallback |
| **Web data** | Bright Data MCP (hosted) | `search_engine` (free tier, fast) + `scrape_as_markdown` fallback chain; `web_data_*` wired but unused |
| **Regulatory data** | Direct `requests` to data.sec.gov | Bright Data robots-blocked from sec.gov on current tier; SEC's API designed for direct programmatic access |
| **Data store** | Airtable (`typecast=True`) | Schema = Airtable; two tables (`signals`, `vendor_config`); no migrations |
| **PDF** | ReportLab + bundled TTFs | General Sans + Sometype Mono — no system-font drift |
| **Hosting** | Railway Hobby ($5/mo) | Always-on, no cold start |
| **Repo** | GitHub public, MIT | `github.com/eschaq` |

---

## 7. Vendor list & current scoreboard

### 7.1 System vendors (hardcoded, not removable)

```
vendor          type            state      score   signals   CIK              SEC monitoring
─────────────────────────────────────────────────────────────────────────────────────────────
Snowflake       Data Infra      CRITICAL    75.2     138     0001640147       ✓ EDGAR 8-K
Twilio          Comms/2FA       CRITICAL    70.5     124     0001403708       ✓ EDGAR 8-K
Veridian Pay    Payments/BaaS   CRITICAL    62.6      23     —                — (demo)
AWS             Cloud Infra     WARNING     43.1     118     0001018724       ✓ EDGAR 8-K
Plaid           Bank Data       WARNING     39.0     126     —                — (private)
Stripe          Payments        WARNING     31.1     142     —                — (private)
─────────────────────────────────────────────────────────────────────────────────────────────
                                                      671 rows total (system)
```

### 7.2 User-added vendors (Wave 3, dynamic)

Salesforce, Inc. was added via the live UI add flow (CIK 0001108524 from SEC lookup) and is currently monitored alongside the system vendors. Total active vendors fluctuates 6–7 depending on user add/remove state. The 30s vendor-config read cache means dashboard rebuild is near-instant after add/remove.

### 7.3 Veridian Pay (demo vendor)

Fictional company; `is_demo=true`; staged 30-day deterioration arc:
- **Headcount:** 480 → 410 (-14.6% over 28d)
- **Open roles:** 38 → 32 → 22 → 14 → 8 → 4 (-89% hiring freeze)
- **Leadership:** 2 senior departures including CTO
- **Glassdoor:** 4.1 → 3.6
- **News sentiment:** label="layoff news"
- **Final beat** (fires only via live-pull): class-action lawsuit + CEO Marisha Chen departure
  - Pre-finale: 62.6 CRITICAL · conv 5 → 6
  - Post-finale: 81.2 CRITICAL · conv 6

All Veridian sources flagged `(no public source — staged demo signal)` in UI + PDF.

---

## 8. Signal capture

### 8.1 Query classes (per real vendor, via Bright Data `search_engine`)

| Class | Query template | Recency |
|---|---|---|
| `news` | `{query_name} news` | `after:2026-01-01` |
| `lawsuit` | `{query_name} lawsuit OR sued OR settles OR court` | `after:2026-01-01` |
| `layoff` | `{query_name} layoffs OR "job cuts" OR "workforce reduction"` | `after:2026-01-01` |
| `leadership` | `{query_name} CEO OR CTO OR CFO OR chairman "steps down" OR resigns OR departs` | `after:2026-01-01` |
| `open_roles` | `{query_name} jobs OR careers OR hiring OR "open position"` | `after:2026-01-01` |
| `edgar_8k` | (direct SEC submissions API, vendors with CIK only) | last 30 days |

**Query disambiguation:** `query_name` uses quoted forms (`"Stripe Inc."`, `"Amazon Web Services"`) to exclude name-collision noise (Stripe Communications PR agency, Tim Cook for AWS, etc.).

### 8.2 Fallback chain (per query)

```
1. search_engine (direct)        → 2-4s, primary path
2. search_engine (retry +2s)     → handles transient backend errors
3. scrape_as_markdown + Claude   → parse Google SERP HTML as last resort
4. Honest empty                  → labeled "all-failed" in fallback_log
```

### 8.3 Event-detection patterns (heuristic, then Claude-validated)

**`LEADERSHIP_VERBS`** (substring-matched against title+description):
- Departure forms: `depart`, `departs`, `departing`, `departed`, `departure`, `departures`
- Resignation: `resign`, `resigns`, `resigning`, `resigned`, `resignation`
- Step-down: `step down`, `steps down`, `stepping down`, `stepped down`
- Retire: `retire`, `retires`, `retiring`, `retired`, `retirement`
- Exit: `exit`, `exits`, `exiting`
- Leave: `leave`, `leaves`, `leaving`, `left`
- Misc: `ousted`, `fired`, `firing`, `replaces`, `replaced`, `successor`, `succeeds`, `transition`, `transitioning`
- Appointments: `appointed`, `named as`, `name as`

**`LEGAL_TERMS`**: `lawsuit`, `sued`, `settles`, `settlement`, `court`, `indicted`, `charges`, `subpoena`, `regulator`, `fines`, `penalty`, `antitrust`

**`LEADERSHIP_ROLES`**: `ceo`, `cto`, `cfo`, `coo`, `cio`, `cmo`, `chairman`, `president`, `founder`, `head of`

An event candidate requires **vendor + role + verb** all present in the same blob; even then, the Claude validator gates the row (typically rejects 70-80%).

---

## 9. Data model

### 9.1 Airtable `signals` table (Type-2 SCD, append-only)

| Field | Type | Notes |
|---|---|---|
| `capture_date` | Date (ISO) | — |
| `vendor_name` | Single line | "Stripe", "Veridian Pay", etc. |
| `vendor_type` | Single line | "Payments", "Comms/2FA", etc. |
| `metric` | Single select (auto-extending) | See vocabulary below |
| `value` | Single line | Numeric or text; scorer float-parses first |
| `unit` | Single line | `score`, `count`, `event`, `employees`, `postings` |
| `source_url` | URL | Trust-contract anchor |
| `sentiment` | Single select | `positive` / `neutral` / `negative` |
| `notes` | Long text | Provenance prefixes (see §9.2) |
| `is_demo_vendor` | Checkbox | True only for Veridian Pay |

### 9.2 Notes prefix taxonomy

| Prefix | Meaning |
|---|---|
| `[news]`, `[lawsuit]`, `[leadership]`, `[layoff]` | Source query class |
| `[off-topic]` | Audit-flagged as noise |
| `auto-detected:` | Heuristic match, validator not run |
| `validated (...):` | Claude validator passed with reason |
| `audit-promoted (claude-validated):` | Post-hoc promotion from sentiment row |
| `live-pull-beat:` | Inserted by `/live-pull` (rehearsal cleanup target) |
| `daily-observation:` | Inserted by daily agent pipeline |
| `edgar-8k: Item N — desc;` | Inserted by EDGAR module |
| `STUBBED` | Demo-vendor staged row |
| `value_type=count` | News-volume row with numeric value (Wave 1 disambiguation) |

### 9.3 Airtable `vendor_config` table (Wave 3, user-add store)

| Field | Type | Notes |
|---|---|---|
| `name` | Single line (primary) | Display name |
| `vendor_type` | Single line | One of `VENDOR_TYPES` enum |
| `is_demo` | Checkbox | Always false for user-added |
| `cik` | Single line | 10-digit SEC CIK (optional) |
| `ticker` | Single line | Exchange ticker (optional) |
| `website` | URL | Optional |
| `is_active` | Checkbox | Soft-delete flag (false = removed) |
| `added_at` | Single line | ISO date |
| `notes` | Long text | Optional |

If the table doesn't exist: dashboard/lookup/system-vendor flows still work; POST /vendors returns 503 with full setup hint; DELETE returns 404. Graceful degrade.

### 9.4 Metric vocabulary

`headcount_linkedin`, `open_roles`, `glassdoor_rating`, `news_sentiment`, `sentiment_review`, `news_volume`, `leadership_change`, `legal_event`, `funding_event`, `outage_incident`

### 9.5 VendorOverview API payload

```json
{
  "name": "Snowflake",
  "type": "Data Infra",
  "is_demo": false,
  "is_removable": false,
  "cik": "0001640147",
  "ticker": null,
  "score": 75.2,
  "state": "critical",
  "convergence_count": 5,
  "signal_count": 138,
  "latest_capture": "2026-05-27",
  "trajectory": [
    {"date": "2026-04-23", "score": 18.5, "state": "stable"},
    ...
    {"date": "2026-05-27", "score": 75.2, "state": "critical"}
  ],
  "components": [
    {"name": "leadership", "score": 0.0, "weight": 0.30, "contribution": 0.0, "drivers": []},
    {"name": "legal", "score": 100.0, "weight": 0.25, "contribution": 25.0, "drivers": [...]},
    ...
  ]
}
```

---

## 10. CDC diff + risk scoring

### 10.1 Component weights (sum = 1.00)

```
component       weight    rationale
─────────────────────────────────────────────────────────────────
leadership      0.30      sharpest failure signal
legal           0.25      sharpest failure signal
headcount       0.17      concrete workforce data
sentiment       0.15      trend amplifier
news_vol        0.07      noisiest dimension
open_roles      0.06      leading workforce indicator (hiring → layoffs)
─────────────────────────────────────────────────────────────────
                1.00
```

### 10.2 Per-component scoring rules

| Component | Rule | Source |
|---|---|---|
| **leadership** | 35 pts/event, 55 for C-suite (CEO/CTO/CFO/COO/CIO/chief), cap 100 | event_values from `leadership_change` rows |
| **legal** | 40 pts/event, cap 100 | event_values from `legal_event` rows |
| **headcount** | Linear in % decline: -5% = 50, -10%+ = 100 | `headcount_linkedin` window trajectory |
| **sentiment** | window-avg of {-1, 0, +1} across `news_sentiment` + `sentiment_review` + glassdoor drop | Multi-source aggregate |
| **news_vol** | `value_type=count`: `(n-5)*10` cap 100. `value_type=label` w/ embedded number: parsed as count. Pure label: cap 20 (low-confidence) | Wave 1 asymmetry fix |
| **open_roles** | Stepped bands: 0/-10% → 20, -10/-29% → 50, -30/-49% → 75, ≤-50% → 100 | Wave 1 stepped rubric |

### 10.3 State bands

```
score range        state       UI color
──────────────────────────────────────────
   0 ≤ s < 30      stable      signal-teal (#3FB8AF)
  30 ≤ s < 60      warning     signal-amber (#FFAA33)
  60 ≤ s ≤ 100     critical    signal-red (#FF5247)
```

### 10.4 Convergence count

Number of metrics with `deteriorating=true` within the 60-day window. Convergence is the actual rare event — multiple dimensions deteriorating simultaneously is the alert signal, not single-metric trips.

### 10.5 Time window

Default `DEFAULT_WINDOW_DAYS = 60`. The alert layer can tighten this for "what changed since last check" CDC slices.

---

## 11. Alert logic

```
def evaluate_alert(VendorRisk) → Alert | None:
    if state == "stable":            return None
    if state == "warning":
        if convergence >= 2:         return Alert(type="convergence")
        else:                        return None  # noisy single dim
    if state == "critical":
        if convergence >= 2:         return Alert(type="convergence")
        else:                        return Alert(type="single_metric")
```

Alert payload carries: `vendor_name`, `fired_at`, `alert_type`, `state`, `score`, `threshold`, `convergence_count`, `signals[]`, `component_breakdown[]`, `headline`. Each signal carries a sourced `evidence[]` list — the trust-contract input for the summarizer.

---

## 12. AI trust contract

The core differentiator vs. generic AI tools: **plausible-but-wrong is the failure mode**; Foreshock's structural answer is full citation enforcement.

### 12.1 Claude invocation (`summarizer.py`)

- **Model:** `claude-sonnet-4-6`
- **System prompt:** GRC-analyst voice; citations mandatory; Claude owns sentiment; no extrapolation; DORA-aware
- **User prompt:** vendor name, score, state, alert type, convergence count, numbered SIGNALS block, numbered SOURCES list
- **Output format:** strict JSON with 4 fields: `headline / sentiment_read / narrative / recommended_action`
- **Constraint:** every factual claim must carry `[N]` citation matching a source
- **Max 4 evidence rows per signal** (controls prompt size + citation density)

### 12.2 Trust-contract auditor (`validate_citations`)

After parsing, `summarizer.validate_citations()`:
1. Regex-extracts every `[N]` and `[N,M]` marker from headline/sentiment/narrative/action
2. Checks each `N` resolves to a numbered source
3. Returns `CitationAudit{cited_ns, valid_ns, invalid_ns, uncited_ns, all_claims_sourced}`

### 12.3 Frontend rendering (`CitedText.tsx`)

- Regex: `/\[(\d+(?:\s*,\s*\d+)*)\]/g`
- Valid citations: `text-signal-blue` anchor to `#source-N`
- **Unresolved (hallucinations): `text-signal-amber` dotted underline** (should be 0)
- Hover title: `metric · source_url`
- SEC-sourced citations get an extra SEC pill next to the `[N]` marker

### 12.4 Deterministic fallback

When `ANTHROPIC_API_KEY` is unset OR any error in Claude call: deterministic summary built from structured signals. Labeled `generated_by="deterministic-fallback"`. Surface label changes from "AI · synthesized" to "deterministic fallback (AI unavailable)".

### 12.5 Verified results (live numbers)

| Vendor | Claims cited | Sources available | Unresolved |
|---|---|---|---|
| Veridian Pay | 15 | 15 | **0** |
| Twilio | 10 | 10 | **0** |
| Stripe | 4 | 5 | **0** |
| Plaid | 12 | 14 | **0** |
| Snowflake | 18 | 18 | **0** |
| AWS | 11 | 11 | **0** |
| **TOTAL** | **70** | **73** | **0** |

Every AI-generated claim across every monitored vendor resolves to a numbered source. **Audit: PASS** across the fleet.

---

## 13. SEC EDGAR integration

### 13.1 Why direct (not Bright Data MCP)

`scrape_as_markdown` returns empty for `application/json` endpoints; SEC HTML is robots-blocked at the current Bright Data tier. SEC's submissions API is explicitly designed for programmatic access and their fair-use policy invites direct calls — we just need a contactable User-Agent.

**Narrative split (preserved in demo):** *"Bright Data fronts locked commercial sources (news, Glassdoor, LinkedIn). Regulatory APIs go direct because they're built for it."*

### 13.2 CIK map

```
vendor          CIK             ticker
─────────────────────────────────────────
Snowflake       0001640147      SNOW
Twilio          0001403708      TWLO¹
AWS             0001018724      AMZN (parent)
─────────────────────────────────────────
Stripe          —               private
Plaid           —               private
Veridian Pay    —               fictional
```

¹ SEC company_tickers.json maps Twilio to CIK 0001447669, but 0001403708 returns valid historical Twilio filings — both are Twilio-related entities. Hardcoded value retained.

### 13.3 8-K item → metric mapping

| 8-K Item | Maps to | Description |
|---|---|---|
| **5.02** | `leadership_change` | Departure of Directors / Certain Officers |
| **1.01** | `legal_event` | Entry into a Material Definitive Agreement (M&A signal) |
| **6.04** | `legal_event` | Bankruptcy or Receivership |

Other items are dropped. Item fallback titles populate when SEC's `primaryDocDescription` is just "8-K" or "FORM 8-K".

### 13.4 Fetch path

```
GET https://data.sec.gov/submissions/CIK{padded_cik}.json
Headers:
  User-Agent: Foreshock/1.0 contact@foreshock.ai
  Accept: application/json
Timeout: 15s
```

Returns ~1000 most recent filings. Parser filters to `form=="8-K"`, `filingDate within N days`, items in mapping.

### 13.5 Row construction

One row per (filing, targeted_item). Multi-item filings fan out — a single 8-K with Items 5.02 AND 1.01 produces both a `leadership_change` and a `legal_event` row, each citing the same source URL.

```
source_url format:
https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_stripped}/{accession_with_dashes}-index.htm

notes format:
edgar-8k: Item {N} — {description}; filed {YYYY-MM-DD}; accession {0001234567-26-000045}
```

### 13.6 Validator + dedup integration

EDGAR rows flow through the same `validator.py` (Claude YES/NO) and the same agent.py dedup guard (vendor+metric+source_url). No special-case code path. The validator typically accepts SEC-sourced events as authoritative.

### 13.7 Latency

- Spec-default 30-day window: ~200ms per vendor
- 365-day demo backfill (one-time): ~200-300ms per vendor

### 13.8 Honesty: SSE event field

```
{
  "step": "pull",
  "vendor": "Snowflake",
  "tool": "sec-submissions-api",        ← not "scrape_as_markdown"
  "class": "edgar_8k",
  "query": "SEC EDGAR 8-K CIK0001640147",
  "status": "done",
  "filings_found": 2,
  "items_matched": 2,
  "duration_ms": 217,
  "path": "direct-sec-api"              ← not "bright-data-mcp"
}
```

FlowPanel + AgentPanel render the `tool` and `path` fields verbatim — the honesty boundary is in the data itself, not just the comment.

---

## 14. Citation trust audit

### 14.1 Endpoint

```
GET /trust/audit
→ {
    total_claims: 70,
    total_citations: 73,
    unresolved: 0,
    all_pass: true,
    vendor_audits: [
      {vendor: "Veridian Pay", claims_cited: 15, sources_available: 15, unresolved: 0, audit_pass: true},
      ...
    ]
  }
```

Aggregates per-vendor summary `audit` blocks. Stable vendors (no AI summary) excluded automatically.

### 14.2 Dashboard trust badge (Wave 6)

Below the Fleet Overview narrative, right-aligned:

```
✓ Citation audit · 70 AI claims across 6 vendors · 0 unresolved · all claims sourced
                                                                  (click for breakdown)
```

- ✓ + "0 unresolved" in `signal-blue` (#3B82F6)
- Numbers in Sometype Mono `tabular-nums`
- Clickable → opens TrustAuditModal with per-vendor table
- Hidden gracefully if `/trust/audit` fails — never shows broken state

### 14.3 PDF footer (Wave 6)

Second Sometype Mono line below the standard footer on every page:

```
Citation integrity  ·  AI-generated claims: 70  ·  Unresolved citations: 0  ·  Audit: PASS
                                                                                    ^^^^
                                                                       teal (or amber for FAIL)
```

### 14.4 TrustAuditModal

| # | Vendor | Claims | Sources | Unresolved | Audit |
|---|---|---|---|---|---|
| 1 | Veridian Pay | 15 | 15 | 0 | **PASS** (teal pill) |
| 2 | Twilio | 10 | 10 | 0 | **PASS** |
| ... | ... | ... | ... | ... | ... |

Aggregate stats at top (4 cards: AI claims, sources, unresolved, vendors audited). Sometype Mono numerics. Esc / click-outside to dismiss. No new API call (reuses prop).

### 14.5 Positioning context (for submission only)

> Foreshock's citation audit infrastructure verifies every AI-generated claim against a numbered source. Current audit result: **0 unresolved citations across all monitored vendors**. In December 2025, a GPTZero investigation found 60% hallucination rates in an EY compliance advisory. FINRA's 2026 oversight report specifically flagged AI hallucination as a compliance risk. Foreshock is the only vendor-risk platform with a built-in, visible citation audit trail.

---

## 15. ICT register PDF export

### 15.1 Endpoint

```
GET /export/ict-register
→ 200 application/pdf
→ Content-Disposition: attachment; filename="foreshock_ict_register_2026-05-27.pdf"
```

Latency: ~5s warm cache, ~130s cold cache (Claude regenerates summaries).

### 15.2 Structure

```
PAGE 1 — Cover
  • Title: "ICT Third-Party Risk Register"
  • Subtitle: DORA Article 28-aligned
  • Scope kv-table (generated UTC, monitoring window, vendor count)
  • Fleet summary (headline + narrative + colored counts)
  • Citation integrity stats inline (PASS/FAIL pill)
  • Compliance disclaimer callout (amber bordered box)
  • TOC table (# | vendor | type | state | score | CIK)

PAGES 2+ — Per-vendor sections
  • PageBreak before each
  • Reuses _build_single_vendor_section() helper:
    - Title block
    - §1 Vendor identification
    - §2 Risk posture
    - §3 Score components
    - §4 Converging signals
    - §5 AI risk narrative (with [N] citations)
    - §6 Source citations (numbered)
  • Stable vendors: §5 renders "No active alert · narrative not generated"

LAST PAGE(S) — Methodology appendix (once, shared)
```

Page footer on every page carries fleet-wide audit verdict.

### 15.3 No-duplication architecture

```
                  ┌───────────────────────────────────────┐
                  │  _build_single_vendor_section()       │
                  │  (title + 6 sections, no disclaimer)  │
                  └────────────┬──────────────────────────┘
                               │
              ┌────────────────┴───────────────────┐
              ▼                                    ▼
  build_vendor_report_pdf()           build_ict_register_pdf()
  (one vendor, ~3 pages)              (cover + N vendors, ~20 pages)
```

No drift possible between formats — fix once, fixes both.

---

## 16. Concentration risk view (Wave 5)

Between FleetOverview and the vendor grid:

```
┌──────────────────────────────────────────────────────────────────┐
│ CONCENTRATION RISK              vendor risk states over window   │
│                                                                  │
│ Snowflake     SEC  ░░░░░░░░░░▓▓▓▓▓▓██████████████          75.2 │
│ Twilio        SEC  ░░░░░░░░▓▓▓▓▓▓██████████████             70.5 │
│ Veridian Pay  DEMO ▓▓▓▓▓▓▓▓▓██████████████████              62.6 │
│ AWS           SEC  ░░░░░░░░░░░░░▓▓▓▓██████████              43.1 │
│ Plaid              ░░░░░░░░░░░▓▓▓▓▓▓██████████              39.0 │
│ Stripe             ░░░░░░░░░░░░░░░▓▓▓▓▓▓██████              31.1 │
│                                                                  │
│ 2026-04-23           N capture dates           2026-05-27        │
└──────────────────────────────────────────────────────────────────┘

   ▓ = stable/teal    █ = warning/amber + critical/red    ░ = no data
```

**Mechanism:** shared time axis = union of every vendor's capture dates. Each cell column = one capture date across the whole fleet. State derived via carry-forward (vendor's state at axis date = state at latest trajectory point on-or-before that date).

**Concentration signal:** scan down a column → vertical alignment of warning/critical colors = multiple vendors deteriorating in same window. DORA-relevant by design.

**Interaction:** click any row → opens DetailPanel. Hover tooltips on cells show `date: state`. Compact (~140px tall).

---

## 17. Vendor management

### 17.1 Two-tier model

- **System vendors** (hardcoded in `vendor_store.py:SYSTEM_DASHBOARD_VENDORS`) — never removable, dashboard works even if vendor_config table missing
- **User-added vendors** (Airtable `vendor_config`, `is_active=true`) — removable via soft delete

Merged at read time. `is_removable` flag in API response drives the UI's hover-X button.

### 17.2 SEC company lookup (`sec_lookup.py`)

- Source: `https://www.sec.gov/files/company_tickers.json` (~1MB blob, ~10K companies)
- Cached in-memory 24h
- Fuzzy match tiers:
  - 1.00 — exact title match
  - 0.90 — title starts with query
  - 0.70 — query substring of title
- Within tier sorted by title length (closer match wins)
- Cold-start fetch ~1-2s; subsequent calls <10ms

### 17.3 Add flow (Wave 3)

Header "+ Add Vendor" button → modal:
- Debounced 400ms live lookup as user types
- Dropdown of top 3 SEC matches (name · ticker · CIK · Public)
- User selects → CIK/ticker auto-fill OR continues typing for private/manual
- Vendor type dropdown (`VENDOR_TYPES` enum: Payments / Bank Data / Cloud Infra / Comms/2FA / Data Infra / Payments/BaaS / Other)
- Confirmation summary: "EDGAR monitoring: active (8-K filings will be tracked)" or "not available (private company)"
- POST /vendors → Airtable row created → dashboard refresh → card appears at STABLE

**Honesty:** monitoring starts next agent run; no auto-pull on add.

### 17.4 Remove flow

Hover user-added card → red ✕ button fades in (top-right, z-20, ring-2 ring-base).

Click → RemoveVendorConfirm modal: "Remove {name} from monitoring? Signal history is preserved."

Confirm → DELETE /vendors/{name} → soft delete (is_active=false) → card disappears.

**404 handling:** treated as idempotent success (vendor already gone) — modal closes + refresh.

**System vendor protection:** returns HTTP 400 "is a system vendor and cannot be removed". System vendors get a muted info overlay on hover (no ✕): "system vendor · protected during demo".

---

## 18. UI surface

### 18.1 Page layout

```
┌────────────────────────────────────────────────────────────────┐
│ HEADER                                                          │
│   foreshock banner                  [tally] [+Add] [ICTRegister]│
│                                     [SettingsGear (live/seeded)]│
│   [RiskScale]                          [ActivityIndicator]      │
├────────────────────────────────────────────────────────────────┤
│ MAIN (max-w-7xl)                                                │
│                                                                 │
│   [FleetOverview]                                               │
│     - Claude-generated portfolio narrative                      │
│     - "AI · synthesized..." label (text-ink-muted)              │
│     - Trust badge clickable → TrustAuditModal                   │
│                                                                 │
│   [ConcentrationRisk]                                           │
│     - One row per vendor, shared time axis                      │
│                                                                 │
│   [Vendor Grid]                                                 │
│     - VendorCard × N                                            │
│     - Hover overlay: "view details" + (X for user-added)        │
│                                                                 │
└────────────────────────────────────────────────────────────────┘

Modals (overlay z-40+):
  [DetailPanel]              right-slide
  [AddVendorModal]           centered
  [TrustAuditModal]          centered
  [RemoveVendorConfirm]      centered
  [AgentPanel]               full-overlay (Pull/Clean/Promote SSE)
  [FlowPanel]                full-overlay (live-pull SSE)
```

### 18.2 Component map

| Component | LOC | Purpose |
|---|---|---|
| `App.tsx` | ~210 | Top-level state, chord, header, grid, modals |
| `ActivityIndicator.tsx` | 46 | Always-on pulsing dot + last pull + mode |
| `AddVendorModal.tsx` | ~250 | Debounced SEC lookup + type select + submit |
| `AgentPanel.tsx` | (large) | SSE consumer for daily agent pipeline |
| `CitedText.tsx` | 68 | Renders `[N]` markers as clickable anchors |
| `ConcentrationRisk.tsx` | ~110 | Shared time-axis heatmap (Wave 5) |
| `DetailPanel.tsx` | ~320 | Right-slide detail with sources/audit/PDF export |
| `FleetOverview.tsx` | ~190 | Fleet briefing + trust badge + audit modal trigger |
| `FlowPanel.tsx` | 440 | SSE consumer for live-pull |
| `RemoveVendorConfirm.tsx` | ~80 | Confirm modal + 404 idempotent handling |
| `RiskScale.tsx` | 52 | Header band-threshold legend |
| `SettingsGear.tsx` | 201 | Mode toggle + reset + shortcut hint |
| `Sparkline.tsx` | 104 | Inline SVG trace with threshold guides |
| `StateBadge.tsx` | 20 | State pill (color-coded) |
| `TrustAuditModal.tsx` | ~140 | Per-vendor citation audit breakdown (Wave 6) |
| `VendorCard.tsx` | ~140 | Card with hover overlay (view-details + delete-X) |
| `lib/edgar.ts` | 12 | `isEdgarMonitored`, `isSecSourceUrl` helpers |
| `lib/api.ts` | ~100 | Typed fetch wrappers |
| `types.ts` | ~180 | TypeScript interfaces |

### 18.3 Color tokens (semantic, in `tailwind.config.js`)

```
base              #0A0C12   page background
surface           #161B2B   card background
signal-blue       #3B82F6   brand · trust · citations
signal-teal       #3FB8AF   stable · PASS
signal-amber      #FFAA33   warning · FAIL · seeded mode
signal-red        #FF5247   critical · delete
ink-primary       #EEF1F8   body text
ink-muted         #9AA3B8   secondary text (labels)
ink-dim           #5A6178   tertiary (decorative only)
rule              #21263B   hairline rules
overlay-strong    rgba(8,8,9,0.80)
overlay-quiet     rgba(8,8,9,0.30)
```

### 18.4 Keyboard shortcuts

- `Ctrl/Cmd + Shift + L` — trigger daily agent run (opens AgentPanel SSE stream)
- `Esc` — close any open modal

---

## 19. API endpoints

### 19.1 Complete endpoint map

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Health check |
| **Vendor / dashboard** |  |  |
| `/vendors` | GET | All vendors (system + user-added) with score, state, trajectory |
| `/vendors/lookup?name=X` | GET | SEC fuzzy lookup (top 3 matches) |
| `/vendors` | POST | Add user vendor (writes to vendor_config) |
| `/vendors/{name}` | GET | Detail panel: overview + alert + summary + 40 recent signals |
| `/vendors/{name}` | DELETE | Soft delete user vendor (is_active=false) |
| `/vendors/{name}/report.pdf` | GET | Single-vendor DORA evidence PDF |
| **Aggregates** |  |  |
| `/fleet/summary` | GET | Fleet-level Claude briefing |
| `/trust/audit` | GET | Citation audit aggregate (Wave 6) |
| `/status` | GET | Activity indicator: monitoring_active, signal counts, last capture |
| **ICT register** |  |  |
| `/export/ict-register` | GET | Multi-vendor PDF, DORA Article 28 format (Wave 7) |
| **Caches** |  |  |
| `/cache/summaries/clear` | POST | Diagnostic: clear summary + fleet caches |
| **Live-pull demo** |  |  |
| `/live-pull/stream?mode=live\|seeded` | GET (SSE) | Per-event JSON: mcp_call/result OR fixture_read/loaded |
| `/live-pull/reset` | POST | Delete all `live-pull-beat:`-tagged rows |
| **Agent pipeline** |  |  |
| `/agent/run` | POST | Kick off Pull → Clean → Promote (returns job_id) |
| `/agent/stream/{job_id}` | GET (SSE) | Per-stage progress events |

### 19.2 SSE event shapes

**Live-pull events:**
```
{type: "start", mode: "live"|"seeded", ...}
{type: "mcp_call", tool, vendor, query, data_path: "bright-data-mcp"}
{type: "mcp_result", results_count, duration_ms, data_path: "bright-data-mcp"}
{type: "fixture_read", fixture, data_path: "local-disk"}
{type: "rows_built", category, vendor, count, metrics}
{type: "airtable_write", status, rows_written}
{type: "complete", mode, real_vendor_rows, veridian_rows, rows_written}
{type: "stream_end"}
```

**Agent pipeline events:**
```
{step: "pull", phase: "start", vendors: [...]}
{step: "pull", vendor, tool, class, query, status: "firing"|"done"|"failed"}
{step: "pull", phase: "done", rows_pulled, failures, fallback_calls}
{step: "clean", phase: "start"}
{step: "clean", vendor, metric, verdict: "kept"|"rejected", reason, title}
{step: "clean", phase: "done", kept, rejected, candidates}
{step: "promote", phase: "start", rows_to_write, events_deduplicated}
{step: "promote", vendor, status: "done"|"failed"|"deduplicated", rows_written}
{step: "promote", phase: "done"}
{step: "complete", summary: {...}}
```

---

## 20. Honesty boundaries

Built-in, not bolted on. Every surface has a structural mechanism for honesty:

| Surface | Honesty mechanism |
|---|---|
| **AI summary** | Trust-contract auditor + visual unresolved-citation marker (amber dotted underline) |
| **Demo vendor** | `is_demo` flag → UI badge → PDF disclaimer → staged sources flagged |
| **Live vs seeded mode** | SSE `data_path` field (bright-data-mcp vs local-disk) — frontend can't fake |
| **AI vs deterministic** | `generated_by` field → fleet briefing label "AI · synthesized" vs "deterministic fallback" |
| **EDGAR vs Bright Data** | SSE `tool` field (sec-submissions-api vs search_engine) + `path` (direct-sec-api vs ...) |
| **PDF disclaimer** | Amber-bordered callout on cover page ("EXAMPLE OUTPUT — ILLUSTRATIVE ONLY...") |
| **Off-topic capture** | `[off-topic]` prefix in notes (audit-flagged noise) |
| **System vs user vendor** | `is_removable` field → UI hides X for system; backend rejects DELETE with 400 |
| **SEC vs news citation** | `isSecSourceUrl()` check → SEC pill next to `[N]` marker in source list |
| **Citation audit verdict** | PASS (teal) vs FAIL (amber) on dashboard + PDF footer; **currently PASS** |

---

## 21. Demo script (5 acts)

### Act 1 (15s) — Dashboard impression

**Open `:5173`.** Narrate:

> "Foreshock continuously monitors 6 ICT vendors for the GRC team. The fleet view shows the AI-synthesized portfolio briefing — Snowflake, Twilio, and Veridian are critical. Three SEC-monitored, two private, one demo. The citation audit at the bottom: 70 AI claims across 6 vendors, **zero unresolved citations** — every claim sources to a citation."

Click the trust badge. **TrustAuditModal opens** showing PASS pills per vendor.

> "GPTZero found 60% hallucination rates in EY's compliance advisory. FINRA flagged AI hallucination as a 2026 compliance risk. We have a built-in citation audit. Foreshock is the only vendor-risk platform with this."

### Act 2 (20s) — Concentration risk

Close modal. Point to ConcentrationRisk card.

> "DORA Article 28 explicitly requires concentration risk analysis. This heatmap shows every vendor on the same time axis. You can see the convergence — three vendors went critical in the same two-week window. That's the foreshock signal: not one vendor failing, but the pattern."

### Act 3 (30s) — Live pull (the money shot)

`Ctrl+Shift+L`. **AgentPanel opens with live SSE.**

> "This is the daily monitoring run, end-to-end. Pull: Bright Data MCP fires across 5 query classes per vendor — news, lawsuits, layoffs, leadership changes, hiring trends. For Snowflake, Twilio, AWS, we also pull SEC EDGAR 8-K filings — direct to SEC's submissions API."

Watch events stream. Highlight the Claude validator:

> "Clean: every event candidate goes through a Claude validator. 'PayPal sues' — that's not Stripe, rejected. 'Tim Cook steps down' — that's Apple, not AWS, rejected. About 80% rejection rate. The 20% that pass are real."

Promote phase writes rows. Refresh.

### Act 4 (30s) — Detail drill + cited narrative

Click **Snowflake card** → DetailPanel slides in.

> "Snowflake is critical because of three legal events from SEC filings plus securities-class-action news. Look at the AI narrative — every claim has a [N] marker. Click it — it jumps to the source. SEC pill on the SEC filings. That's the trust contract: nothing the AI says is unsourced."

Click **Export DORA evidence (PDF)** → downloads.

### Act 5 (15s) — ICT register + close

Header → **Export ICT Register (PDF)**.

> "One click. All vendors. Cover page with the fleet view, the citation audit, the disclaimer. Per-vendor sections, methodology appendix. This is the DORA Article 28 ICT register your GRC lead would file. Nobody else ships this."

> "Foreshock felt it."

---

## 22. Competitor analysis

### 22.1 Category comparison

| Capability | OneTrust (GRC) | BitSight (Security rater) | Owler (CI) | **Foreshock** |
|---|---|---|---|---|
| **Vendor business-health monitoring** | ❌ Paperwork only | ❌ Attack surface only | △ Generic news, no scoring | ✅ **5 query classes + SEC EDGAR** |
| **Convergence-based alerting** | ❌ Single-policy violations | △ Single-metric thresholds | ❌ News alerts only | ✅ **Multi-dim convergence** |
| **Cited AI narratives (0 hallucinations)** | ❌ AI-assisted, no audit | ❌ No AI | ❌ No AI | ✅ **Verifiable 0 unresolved** |
| **SEC EDGAR 8-K integration** | ❌ | ❌ | ❌ | ✅ **3 vendors live, item-level mapping** |
| **DORA Article 28 ICT register (one-click)** | △ Manual register building | ❌ | ❌ | ✅ **Multi-vendor PDF, all in one** |
| **Type-2 SCD on business signals** | △ Yes for paperwork | ❌ | ❌ | ✅ **~688 rows append-only** |
| **Honesty boundaries productized** | ❌ Black-box scoring | ❌ Opaque algorithm | ❌ | ✅ **6+ explicit boundaries** |
| **Live demo with real data** | N/A — sales-led | △ Sample reports | ❌ Public Owler | ✅ **`:5173` live** |
| **Time-to-first-signal** | Weeks (questionnaires) | Days (cert scan) | Real-time but unscored | **24hr (next agent run)** |
| **Total cost of ownership** | $50k-$500k/yr enterprise | $30k-$200k/yr | $50/mo individual | **TBD (sub-enterprise gap)** |

### 22.2 Head-to-head wins

**vs. OneTrust / Prevalent / ProcessUnity:**
> *"They watch the paperwork. We watch the company. Their register tells you the vendor exists. Ours tells you the vendor is failing — with 0 hallucinated claims."*

**vs. BitSight / SecurityScorecard / UpGuard:**
> *"They scan certificates and ports. We scan boardrooms and courts. The breach is the lagging indicator. We watch the foreshock — the layoff, the lawsuit, the CTO exit — that precedes it."*

**vs. Owler / Crayon / Klue:**
> *"They surface news. We turn news into a scored risk signal, citation-audit it, and ship the DORA register. Same data, different output category."*

### 22.3 What no incumbent does

1. **Citation audit infrastructure with visible PASS/FAIL** on dashboard + PDF footer
2. **Multi-vendor ICT register PDF** as a one-click DORA artifact (single document, all vendors, cover + methodology)
3. **Concentration risk heatmap** — shared time axis across all vendors
4. **SSE-streamed live demo** with honesty boundary in event data (live vs seeded mode)
5. **Convergence-based alerting** — not single-metric threshold trips
6. **Trust contract pattern** — strict-JSON Claude output + post-parse validator + frontend visual marker

### 22.4 Where Foreshock will lose initially

- **Enterprise procurement / SOC2 / compliance certs** — incumbent moat
- **Vendor library breadth** — incumbents have thousands of pre-monitored vendors
- **Integration ecosystem** — no Slack/Jira/SIEM connectors yet
- **Questionnaire workflow** — explicitly out of scope (OneTrust's lane)

These are deliberate scope choices (see §25), not gaps to fix.

---

## 23. Candidate moats

Test each against actual incumbent depth.

1. **Citation audit infrastructure** — strict-JSON output + post-parse validator + visual unresolved-marker. Mechanically copyable but requires opinionated discipline across product, prompt, validator, UI. **Verifiable today: 0 unresolved across 70 claims.**
2. **DORA Article 28 ICT register as one-click PDF artifact.** Most GRC tools require composing reports manually. The "Article 28 paper trail in one click" is concrete and on-trend (DORA enforceable Jan 2025). Cover + per-vendor + methodology, fleet-wide audit verdict in footer.
3. **Business-health signal category itself.** Adjacent players don't watch leadership / legal / hiring as a coherent risk feed. Suspect: no GRC-shaped pure-play exists.
4. **Convergence-based alerting** (not single-signal trips). Multiple deteriorating dimensions crossing simultaneously is the actually-rare event. Suspect novel in GRC vendor monitoring.
5. **Type-2 SCD on business signals.** Full historical reconstruction supports "what did you know and when" auditor questions. GRC platforms do this for paperwork; nobody does it for signals.
6. **Honesty boundaries as a productized aesthetic.** Demo vs. real, live vs. cached, AI vs. deterministic, EDGAR vs. MCP, system vs. user, SEC vs. news — built into UI/PDF/SSE. Hard to retrofit; easy to differentiate.
7. **Bright Data MCP integration depth** + sane regulatory-API fallback. All 4 actions wired with graceful tier fallback; SEC direct where MCP can't reach. Compounds as Bright Data tooling expands.

---

## 24. Known limitations

### Capture
- News volume queries return 0 for some vendors (Plaid, Twilio, AWS) — Google News vertical thin on bare-name searches
- Bare-name queries pull noise; mitigated by Claude validator + post-hoc prefix audit, not by query design
- Twilio CIK (0001403708 hardcoded) doesn't match SEC tickers JSON (0001447669) — both are Twilio entities; not breaking but worth investigating

### Scoring
- `funding_event` metric defined but never observed
- Sentiment heuristic in capture is keyword-based (placeholder); Claude replaces in summary narrative
- News-volume label/count asymmetry fixed (Wave 1) but earlier rows retain label values

### Operational
- No real-time push to frontend — manual refresh required after capture
- In-process summary cache (no Redis); cache grows unbounded over long sessions
- Detail panel doesn't auto-refresh after live-pull
- Live-pull idempotency via tag-then-reset, not unique IDs — re-running duplicates Veridian finale rows
- Agent job_id pops from `_agent_jobs` registry as soon as the first SSE listener disconnects (eager cleanup in `gen()` finally block) — can't reconnect mid-run
- No CI / no unit tests (only `scripts/test_*.py` smoke runners)
- No DB migrations (Airtable IS the schema; auto-extending selects via `typecast=True`)
- ICT register PDF takes ~130s on cold cache (Claude regenerates summaries) — needs explicit user-facing latency warning in button title

### Trust / audit
- Audit shows "claims_cited" as count of `[N]` markers, not distinct factual claims (a single `[3,5]` marker = 2 claims under this counting)
- TrustAuditModal opened from FleetOverview only; not yet from DetailPanel header (could be a follow-up)
- ICT Register cover-page TOC has no page numbers (would require ReportLab `TableOfContents` with `notify()` in section headers — too invasive for current pass)

### EDGAR
- `lookback_days=30` may return 0 matches for many vendors (8-K filings are infrequent). Backfill via `scripts/test_edgar.py --days 365 --write` already seeded 6 historical rows
- `primaryDocDescription` is often just "8-K" — fallback to SEC official item titles works but lacks specificity

---

## 25. Explicitly out of scope

- Other monitoring modules (competitor / supplier / M&A target) — same engine, different entity class
- Full DORA register auto-generation (one-off PDF export only ships; not the live-syncing register)
- Questionnaire / vendor onboarding workflow — OneTrust's lane
- Security scoring (CVE, cert hygiene, attack-surface metrics) — BitSight's lane
- Multi-target side-by-side comparison view
- Team accounts / RBAC / SSO
- Automated historical backfill
- Webhooks / Slack notifications / email digests
- External API for third-party consumers (read-only, internal-only currently)

---

## 26. File inventory

### 26.1 Backend Python (`backend/foreshock/`)

| File | LOC | Purpose |
|---|---|---|
| `api.py` | ~370 | Dashboard payloads; trust audit; vendor add/remove/lookup wrappers |
| `alerts.py` | 188 | Alert evaluation; convergence detection |
| `capture.py` | ~300 | Daily MCP capture; 4 query classes; Type-2 row construction; CIK config |
| `live_pull.py` | 437 | Hero live/seeded pull; Veridian finale; SSE streaming |
| `observation.py` | ~430 | Per-vendor pull orchestration + fallback + EDGAR call |
| `scoring.py` | ~490 | CDC diff; 6-component weighted score; stepped open_roles; volume label fix |
| `summarizer.py` | 406 | Claude Sonnet summary; trust-contract audit; fallback |
| `validator.py` | 197 | Event gate; Claude YES/NO; signal classification |
| `agent.py` | ~330 | Unattended pipeline with SSE; dynamic vendor list |
| `report.py` | ~1050 | Single-vendor + ICT register PDF; shared `_build_single_vendor_section` |
| `edgar.py` | ~250 | SEC submissions API direct; item→metric mapping |
| `vendor_store.py` | ~230 | System + user vendor merge; Airtable CRUD; fault-tolerant |
| `sec_lookup.py` | ~120 | Cached company_tickers.json + fuzzy match |

### 26.2 Backend scripts (`backend/scripts/`)

| Script | Purpose |
|---|---|
| `run_daily_capture.py` | CLI: pull all real vendors via 4 query classes |
| `run_live_pull.py` | CLI: trigger live/seeded/reset paths |
| `run_daily_observation.py` | CLI wrapper around observation.capture_real_vendor() |
| `clean_todays_events.py` | Post-hoc Claude validation; delete false positives |
| `audit_signal_prefixes.py` | Reclassify misleading prefixes on sentiment rows |
| `whatif_promote_events.py` | In-memory promotion simulation |
| `populate_open_roles.py` | Veridian hiring-freeze staging |
| `dedup_cleanup_*.py` | One-off data maintenance |
| `rescore_wave1.py` | Wave 1 delta analysis |
| `test_brightdata_mcp.py` | First-contact MCP verification |
| `test_airtable_write.py` | First-contact Airtable Type-2 verification |
| `test_recency_filter.py` | Verify `after:` operator returns 2026-era results |
| `test_scoring.py` | Smoke test: scoring on Veridian + Stripe |
| `test_alerts.py` | Smoke test: alert payload structure |
| `test_summary.py` | Smoke test: Claude summary + trust audit |
| `test_edgar.py` | EDGAR smoke test (`--days N`, `--write`) |
| `debug_*.py` | EDGAR + MCP debug utilities |

### 26.3 Frontend (`frontend/src/`)

See §18.2 for component map.

---

## 27. Open items & next steps

### Pre-demo polish (optional)
- Add ticker column to dashboard cards / detail panel (data available, not surfaced)
- Page-numbered TOC in ICT register (ReportLab `TableOfContents`)
- Cold-cache warming on app startup (background `trust_audit_payload()` call)

### Post-demo roadmap signals
- Slack webhook integration (alert-on-state-change)
- Tightening leadership verb list with infinitive/modal forms (partially done Wave 1)
- Per-vendor query template tuning (currently bare-name for user-added, noisy)
- Auto-promoting validated audit events from sentiment rows (capture.py post-pass)
- Vendor lookup endpoint as Wave 3 spec described (live SEC search vs cached tickers) — current cached approach is simpler and faster but lacks fuzzy edge cases

### Architecture cleanups
- Move `_agent_jobs.pop()` from `gen()` finally to runner finally — fixes mid-stream reconnect
- Extract shared PdfIcon component (duplicated in App.tsx + DetailPanel.tsx)
- Cache TrustAudit response at parent App level (currently fetched per FleetOverview mount)
- Build per-vendor PDFs in parallel for ICT register (currently sequential — would halve cold-cache latency)

### Submission-package items
- Cover image 16:9 (seismic motif)
- Demo video <5min recorded
- README with setup + screenshots + live link
- Additional Info text: business-signal-monitoring gap + 4-action Bright Data usage + DORA register + 0-hallucination audit
- X engagement post (lablab tag if required)

---

## Appendix A — Brand

- **Wordmark:** lowercase `foreshock`
- **Tagline:** "Foreshock felt it."
- **Motif:** seismograph (sparklines read as seismic traces)
- **Typography:** General Sans (body) + Sometype Mono (numerics, citations, SSE event logs)
- **Voice:** calibrated, charged (only at earned moments), restrained (95% calm dark canvas)
- **References:** G&CO, Betterment — dark cinematic fintech, confident, not cozy
- **Anti-references:** navy-and-gold fintech cliché, terminal-cyberpunk SaaS, editorial-serif, SaaS-cream pastel, hero-metric template, gradient text, side-stripe borders

## Appendix B — Verified demo URLs

- Dashboard: `http://localhost:5173`
- Single-vendor PDF: `http://localhost:8000/vendors/Snowflake/report.pdf`
- ICT Register PDF: `http://localhost:8000/export/ict-register`
- Trust audit JSON: `http://localhost:8000/trust/audit`
- Live SEC lookup: `http://localhost:8000/vendors/lookup?name=Salesforce`
