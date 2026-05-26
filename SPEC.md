# Foreshock — System Specification (current state)

> **Snapshot:** 2026-05-26 end-of-build-day-2. Documents what's actually built and behaving, for enhancement-planning purposes. For product vision and explicitly-roadmapped features, see [CLAUDE.md](CLAUDE.md). For the build-sequence narrative, see git log.

---

## 0. TL;DR

Foreshock is a continuous third-party-vendor risk-monitoring application for fintech GRC teams. It watches **6 named vendors** (5 real + 1 staged demo) across public web sources via **Bright Data MCP**, stores timestamped signal history in **Airtable**, runs a **CDC diff + weighted-component risk score**, fires a **convergence alert** when a vendor crosses critical, and produces a **fully-cited GRC-analyst-style narrative via Claude**. A **React/Tailwind dashboard** renders the scoreboard with sparkline trajectories, click-to-drill detail panels, a quiet always-on activity indicator, and a **settings gear that toggles between live MCP capture and a cached fixture replay** for demo network safety.

Build acts 1–7.5 are complete. The visual reskin (act 8) and demo video recording (act 9) remain.

Total source: ~5,400 lines (~3,000 Python backend + ~1,500 TypeScript frontend + ~900 supporting scripts).

---

## 1. Product positioning (what's actually built)

- **Audience.** A GRC / compliance lead at a mid-market fintech ($50M–$2B rev) managing DORA obligations on a stack of critical ICT vendors. Often a one-person team.
- **What the product surfaces.** Real-time business-health signals on named vendors — leadership departures, lawsuits, headcount trajectory, sentiment direction, news volume, glassdoor — and synthesizes them into a sourced narrative with a recommended action.
- **The gap it claims.** GRC platforms watch paperwork; security raters watch the attack surface. Foreshock watches business-health signals — the leading indicators that precede vendor failure.
- **Differentiation line in the demo.** "BitSight watches the security posture; Foreshock watches the business health. The layoff precedes the breach."
- **Trust contract.** Every claim in an AI summary cites a numbered source, each citation resolves to a real `source_url` in the evidence list. Frontend renders `[N]` markers as anchor links to the source list; an audit visibly flags any unsourced claim.

---

## 2. Architecture at a glance

```
                            ┌─────────────────────────────────────┐
                            │       Bright Data MCP (cloud)       │
                            │  search_engine / scrape_as_markdown │
                            └────────────────┬────────────────────┘
                                             │ (live mode only)
                                             ▼
   ┌─────────────────────┐     ┌──────────────────────────────────┐
   │  fixtures/.json     │────▶│  capture.py  /  live_pull.py     │
   │  (seeded mode)      │     │   - per-class queries            │
   └─────────────────────┘     │   - row construction (Type 2)    │
                               │   - optional validator callback  │
                               └──────────────┬───────────────────┘
                                              │  Type 2 append-only rows
                                              ▼
                               ┌──────────────────────────────────┐
                               │      Airtable `signals` table    │
                               │      (the only source of truth)  │
                               └──────────────┬───────────────────┘
                                              │  read on demand
                                              ▼
        ┌──────────────────────────────────────────────────────────────┐
        │   scoring.py  →  alerts.py  →  summarizer.py  →  validator.py │
        │   (CDC diff)    (convergence)   (Claude+trust)  (Claude gate) │
        └──────────────────────────┬───────────────────────────────────┘
                                   │  REST + SSE
                                   ▼
                          ┌─────────────────────┐
                          │  FastAPI (main.py)  │
                          │  /vendors           │
                          │  /vendors/{name}    │
                          │  /status            │
                          │  /live-pull/stream  │  (SSE)
                          │  /live-pull/reset   │
                          │  /cache/.../clear   │
                          └──────────┬──────────┘
                                     │  via Vite /api proxy
                                     ▼
                       ┌─────────────────────────────┐
                       │  React + TS + Tailwind UI   │
                       │  Vite dev server :5173      │
                       └─────────────────────────────┘
```

---

## 3. Data model

### 3.1 Airtable `signals` table (the only persistent data)

Every signal observation is a **new timestamped row** — Type 2 SCD; never overwritten. CDC diff is computed by comparing rows for the same `vendor_name + metric`.

| Field | Type | Notes |
|---|---|---|
| `capture_date` | Date | ISO `YYYY-MM-DD` of capture |
| `vendor_name` | Single line text | "Stripe", "Veridian Pay", etc. |
| `vendor_type` | Single line text | "Payments", "Payments/BaaS", "Cloud Infra", etc. |
| `metric` | Single select (auto-extending) | See §3.3 |
| `value` | Single line text | Numeric or text; scoring tries float-parse first |
| `unit` | Single line text | `score`, `count`, `event`, `employees`, `postings` |
| `source_url` | URL | The trust-contract anchor |
| `sentiment` | Single select | `positive` / `neutral` / `negative` (heuristic placeholder) |
| `notes` | Long text | Free-form context; carries provenance tags |
| `is_demo_vendor` | Checkbox | True only for Veridian Pay |

**Current row count: 127** (Stripe 37, Twilio 22, Plaid 20, Snowflake 20, AWS 15, Veridian 13). See §11 for the live scoreboard.

### 3.2 Vendor catalog

| Vendor | Type | Demo? | Notes |
|---|---|---|---|
| Veridian Pay | Payments/BaaS | ✓ | Fictional. Staged 30-day risk arc (4/23 → 5/21). Finale beat (lawsuit + 2nd C-suite exit) lands via live-pull, not staged. |
| Stripe | Payments | — | Real. Includes one audit-promoted leadership_change (CTO Singleton, [fintechfutures.com](https://www.fintechfutures.com/fintech/stripe-cto-david-singleton-to-step-down-after-seven-years-to-start-own-company)). |
| Twilio | Comms/2FA | — | Real. Holds 2 validated event rows (Missed Call LLC lawsuit + leadership transition) + 1 audit-promoted TCPA legal_event. |
| Plaid | Bank Data | — | Real. No events; sentiment-driven. |
| Snowflake | Data Infra | — | Real. No events; sentiment-driven. |
| AWS | Cloud Infra | — | Real. No events; sentiment-driven. |

Defined in two places (intentional — different concerns):
- `foreshock/capture.py::REAL_VENDORS` — the 5 real for daily capture
- `foreshock/api.py::DASHBOARD_VENDORS` — the 6 for the dashboard grid (adds Veridian, ordered for display)

### 3.3 Metric vocabulary

| Metric | Kind | How scored |
|---|---|---|
| `headcount_linkedin` | Numeric | % decline over window → 0-100 score |
| `open_roles` | Numeric | Captured but not currently scored |
| `glassdoor_rating` | Numeric | Absolute drop (oldest-vs-latest) folded into sentiment component |
| `news_sentiment` | Numeric or sentiment label | Window-avg of {−1, 0, +1}; deteriorating if avg ≤ −0.2 |
| `sentiment_review` | Numeric or sentiment label | Same mapping as news_sentiment |
| `news_volume` | Numeric count or label | `low`/`normal`/`high`/`layoff news` → 0-3 score; numeric counts mapped via `(n−5)×10` capped 100 |
| `leadership_change` | Event | Each event = 35 points; C-suite words (CEO/CTO/CFO/COO/CIO/chief) = 55. Capped 100. |
| `legal_event` | Event | Each event = 40 points. Capped 100. |
| `funding_event` | Event | Defined in scoring schema; not currently used |
| `outage_incident` | Event | Adds 20/event to news_volume component |

Defined in [`foreshock/scoring.py`](backend/foreshock/scoring.py): `NUMERIC_METRICS`, `SENTIMENT_METRICS`, `VOLUME_METRICS`, `EVENT_METRICS`.

### 3.4 Notes-prefix taxonomy

The `notes` field carries provenance prefixes used by validators, the audit pass, and the dashboard's optional detail view.

| Prefix | Provenance | Used by |
|---|---|---|
| `[news]`, `[lawsuit]`, `[layoff]`, `[leadership]` | Query class that produced the row in daily capture | Set by `capture.py`; audited by `audit_signal_prefixes.py` |
| `[off-topic]` | Audit verdict that vendor isn't the primary subject | Set by `audit_signal_prefixes.py` |
| `auto-detected: ...` | Heuristic event-detector match (pre-validator era) | `capture.py` |
| `validated (reason): ...` | Claude validator confirmed a candidate event | `capture.py` when `validator` callback present |
| `audit-promoted (claude-validated): ...` | Manually promoted from sentiment row → event row, Claude-confirmed | One-off promotions for Stripe CTO + Twilio TCPA |
| `live-pull-beat: ...` | Written by the demo's live-pull module | `live_pull.py`; targeted by `/live-pull/reset` |
| `STUBBED ...` | Veridian's staged 30-day arc | Manually seeded once |

---

## 4. Pipeline — stages in detail

### 4.1 Capture (daily background) — [`foreshock/capture.py`](backend/foreshock/capture.py)

For each of the 5 real vendors, fires 4 class-scoped Google `search_engine` calls via Bright Data MCP, recency-filtered with the Google `after:2026-01-01` operator (portable; doesn't depend on a tool-specific recency param).

```python
QUERY_CLASSES = [
    {"class": "news",       "template": "{vendor} news"},
    {"class": "lawsuit",    "template": "{vendor} lawsuit OR sued OR settles OR court"},
    {"class": "layoff",     "template": '{vendor} layoffs OR "job cuts" OR "workforce reduction"'},
    {"class": "leadership", "template": '{vendor} CEO OR CTO OR CFO OR chairman "steps down" OR resigns OR departs'},
]
```

Per vendor per run, writes (Type 2 append):
- `news_volume` row — total unique URLs across all 4 queries, with per-class breakdown in `notes`
- ~20 `news_sentiment` rows (top 5 per class, deduped by URL, class prefix in `notes`)
- `legal_event` / `leadership_change` event rows — **only if** a conservative pattern matcher fires (vendor name + role + departure verb / vendor + legal term in same blob) AND, if a `validator` callback is supplied, Claude confirms

CLI: `scripts/run_daily_capture.py`. Latency: ~60–80s sequential (20 MCP calls × 2–4s).

**Validator callback signature** (decoupled — `capture.py` doesn't import the Anthropic SDK):
```python
ValidatorFn = Callable[[str, str, str, str], tuple[bool, str]]
                       # vendor, event_type, title, description -> (valid, reason)
```

### 4.2 Validation (event gate) — [`foreshock/validator.py`](backend/foreshock/validator.py)

A tight Claude call with a hard YES/NO contract. Used in two places:
- Inline in `capture.py` (when `validator` callback supplied — guards new event rows)
- Post-hoc in `scripts/clean_todays_events.py` (cleaned today's noise: 17 rejected out of 19)

Returns `ValidationResult(valid: bool, reason: str, raw: str)`. Strict JSON parse with code-fence stripping fallback. Parse errors → `valid=False`.

Also exposes `classify_signal()` which returns one of `leadership | lawsuit | layoff | news | unrelated` — used by the prefix-audit pass.

Model: `claude-sonnet-4-6` (spec'd in `MODEL` constant).

### 4.3 Prefix audit — [`scripts/audit_signal_prefixes.py`](backend/scripts/audit_signal_prefixes.py)

Walks every `news_sentiment` row whose notes are prefixed `[leadership]` or `[lawsuit]` (for real vendors), runs each through `classify_signal()`, and updates the prefix to match Claude's verdict. `unrelated` becomes `[off-topic]`. Run once already — 33 of 39 candidates were either reclassified to `[news]` (12) or marked `[off-topic]` (21); 6 confirmed correct. Cleans up the detail-view display without touching scoring.

### 4.4 Scoring — [`foreshock/scoring.py`](backend/foreshock/scoring.py)

Pure functions. Input: list of signal row dicts for one vendor. Output: `VendorRisk` dataclass.

**CDC diff** (`build_diff`):
- Groups rows by metric
- For each metric: `latest`, `prior` (immediate predecessor), `oldest_in_window` (60-day window)
- Numeric metrics → `numeric_delta` (latest−prior), `numeric_trajectory` (latest−oldest), `pct_trajectory`
- Event metrics → `event_count_window`, `event_values[]`
- Sentiment metrics → window-average mapped from labels {neg, neu, pos} → {−1, 0, +1}
- Volume metrics → label scale 0–3 OR numeric count
- Each metric flagged `deteriorating: bool` per metric-specific rule

**Component scoring** (`score_vendor`):

| Component | Weight | Logic |
|---|---|---|
| `leadership` | 0.30 | 35/event base, 55 for C-suite; capped 100 |
| `legal` | 0.25 | 40/event; capped 100 |
| `headcount` | 0.20 | Linear in `pct_trajectory`; −5% = 50, −10% = 100 |
| `sentiment` | 0.15 | Average of news_sentiment + sentiment_review + glassdoor-drop scores |
| `news_vol` | 0.10 | Latest news_volume value mapped to 0-100, plus outage bonus |

**State bands** (`STABLE_MAX=30`, `WARNING_MAX=60`):
- `score < 30` → stable
- `30 ≤ score < 60` → warning
- `score ≥ 60` → critical

**Convergence count:** number of independent signal dimensions whose `deteriorating` flag is True. Drives the alert's `convergence` tag.

**Source carrying:** `MetricDiff.sources: list[SourceRef]` captures every in-window row's `(capture_date, value, source_url, notes, sentiment)` so downstream consumers (alerts, summarizer) get the citation trail for free.

### 4.5 Alerts — [`foreshock/alerts.py`](backend/foreshock/alerts.py)

`evaluate_alert(VendorRisk) → Alert | None`:
- `state == "stable"` → None
- `state == "warning"` and `convergence_count >= 2` → `Alert(alert_type="convergence")` else None (single-metric warnings don't page)
- `state == "critical"` → Alert with `alert_type="convergence"` if `>=2` dimensions deteriorating, else `single_metric`
- `CONVERGENCE_MIN = 2` is the threshold

Payload structure (`Alert` dataclass):
```python
{
  vendor_name, fired_at, alert_type, state, score, threshold,
  convergence_count,
  signals: [ConvergenceSignal(metric, summary, latest_value, latest_date,
                              source_urls[], evidence[{capture_date, value,
                              source_url, notes, sentiment}])],
  component_breakdown: [{name, score, weight, contribution, drivers[]}],
  headline: "<one-liner>",
}
```

The `evidence` carries the full sourced trail per signal — what step 4.6's Claude pass consumes.

### 4.6 AI summary (with trust contract) — [`foreshock/summarizer.py`](backend/foreshock/summarizer.py)

Consumes an `Alert` (the scored diff summary — never raw Airtable rows; CLAUDE.md §2 "summary-only pattern"). Produces a four-field GRC-analyst briefing with strict [N] citations.

**Prompt skeleton** (system + user template):
- System prompt instructs Claude: GRC analyst role, DORA awareness, **citations are not optional**, **no extrapolation**, claude is the sentiment authority (heuristic labels are noisy priors).
- User template lays out: vendor, score, state, threshold, alert type, convergence count; then a numbered SIGNALS block; then a numbered SOURCES list (1..N) that the narrative must cite.
- Claude returns strict JSON: `{headline, sentiment_read, narrative, recommended_action}`.

**Output:** `RiskSummary` dataclass with `headline`, `sentiment_read`, `narrative`, `recommended_action`, `citations: list[Citation]`, `generated_by`, `parse_error`.

**Trust-contract auditor:** `validate_citations(summary) → CitationAudit` — parses every `[N]` / `[N,M]` pattern from the four text fields, confirms each resolves to a real citation. Surfaces `invalid_ns` (hallucinations — should always be empty), `uncited_ns` (sources Claude didn't use), and per-field `citation_density`.

**Graceful degradation:** No `ANTHROPIC_API_KEY` set, any Anthropic API error, any JSON parse error → returns a deterministic summary built from structured signals with `generated_by="deterministic-fallback"`. Pipeline never breaks.

Model: `claude-sonnet-4-6`.

Veridian narrative (critical) ran with 11 sources, 100% sourced. Stripe narrative (warning) with 6/8 sources used, 100% sourced. See [`scripts/test_summary.py`](backend/scripts/test_summary.py) for the verification harness.

### 4.7 Live pull (demo act 2) — [`foreshock/live_pull.py`](backend/foreshock/live_pull.py)

The demo's hero moment. Triggered by `Ctrl/Cmd + Shift + L` (frontend) or `scripts/run_live_pull.py` (CLI). Streamable via SSE.

Two functions:
- `run_live_pull(mode)` — single-shot, returns `LivePullResult`
- `stream_live_pull(mode)` — async generator yielding per-step events (consumed by the SSE endpoint and the FlowPanel)

**The mode switch** (the honesty boundary):

```
mode=live    → _fetch_organic_live()   → MCP search_engine call
                                       → emits {mcp_call} + {mcp_result} events
                                       → data_path: "bright-data-mcp"

mode=seeded  → _fetch_organic_seeded() → reads foreshock/fixtures/seeded_real_pull.json
                                       → emits {fixture_read} + {fixture_loaded} events
                                       → label: "cached_replay"
                                       → data_path: "local-disk"
```

**Downstream is identical for both modes.** Same `_real_vendor_rows_from_payload()`, same Veridian finale construction (`_veridian_finale_rows()`), same Airtable write.

**Veridian finale (scripted, hardcoded — fires in both modes):**
- `legal_event`: "Class action filed against Veridian Pay over alleged customer data exposure" → source_url `DEMO-SCENARIO-FINALE`
- `leadership_change`: "Veridian Pay CEO Marisha Chen departs" → source_url `DEMO-SCENARIO-FINALE`

**Provenance tag:** every row written by this module is tagged `live-pull-beat:` in `notes`. `reset_live_pull_rows()` deletes exactly those rows. Rehearsal-safe.

**Save-seed:** `--live --save-seed` captures the live MCP response and overwrites the seeded fixture, so subsequent `--seeded` runs replay a real recent pull.

**Veridian impact:** 68.2 → 81.2 (+13). Convergence 5 → 6. Legal component lights up from 0 → 10.0. Same delta in both modes (Veridian finale is identical).

---

## 5. Backend API surface

FastAPI app in [`backend/main.py`](backend/main.py). CORS open (will tighten for prod). All endpoints are GET unless noted.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Health check |
| GET | `/vendors` | Dashboard grid payload — array of `VendorOverview`. Computes risk score, state, convergence, sparkline trajectory (per-historical-capture-date scoring), component breakdown. |
| GET | `/vendors/{name}` | Detail panel payload: overview + alert envelope + cached AI summary (regenerates if cache key changed) + recent_signals[40]. Optional `?refresh=true` busts the cache. |
| GET | `/status` | Activity-indicator data: `monitoring_active`, `vendor_count`, `signal_count_total`, `last_capture`, `live_pull_query`, `live_pull_vendor`. |
| GET | `/live-pull/stream?mode=live\|seeded` | SSE stream of the live-pull events (text/event-stream). Mode controls fetch source; emits honest mode-specific events. |
| POST | `/live-pull/reset` | Deletes every row tagged `live-pull-beat:`. Returns `{deleted: N}`. |
| POST | `/cache/summaries/clear` | Empties the in-memory summary cache. Mostly diagnostic — cache auto-invalidates via key. |

### 5.1 Summary cache

In-process dict in [`foreshock/api.py`](backend/foreshock/api.py), `Lock`-guarded. Keyed by `(vendor_name, latest_capture_date, signal_count)` — the `signal_count` ensures new rows (from live pull or daily capture) auto-invalidate without manual busting.

---

## 6. Frontend

Stack: React 18 + TypeScript + Vite 5 + Tailwind 3. No shadcn CLI install yet — primitives written by hand in shadcn style so an `npx shadcn add` pass can layer cleanly during act 8.

Vite dev server at `:5173`. Vite proxy: `/api/*` → `http://127.0.0.1:8000/*`. No CORS issues in dev.

### 6.1 Component tree

```
App.tsx
├── header
│   ├── title + tagline
│   ├── tally (n critical · n warning · n stable)
│   └── SettingsGear (⚙)
│       └── dropdown: LIVE/SEEDED toggle + shortcut + reset
│   └── (second row)
│       ├── RiskScale (legend: 0–30 / 30–60 / 60–100)
│       └── ActivityIndicator (● monitoring active · last pull · n signals · trigger:mode)
│
├── main grid (3-col on lg, 2-col on md, 1-col on sm)
│   └── VendorCard × 6
│       ├── name + type + (demo) tag
│       ├── StateBadge
│       ├── score (mono, 3xl, tabular-nums)
│       ├── Sparkline (inline SVG, threshold guides @30/@60)
│       └── footer: convergence · signal count · latest capture
│
├── DetailPanel (slide-in from right, max-w-3xl)
│   ├── header (vendor name, larger sparkline)
│   ├── score components table (5 rows)
│   ├── AI risk summary block (when alert fired)
│   │   ├── trust-contract audit badge
│   │   ├── headline, sentiment_read, narrative paragraphs, recommended_action
│   │   │   (all rendered via CitedText — [N] → anchor links)
│   │   └── sources list (numbered, each with metric, capture_date, note, source_url)
│   └── recent_signals table (40 rows)
│
└── FlowPanel (modal, ctrl/cmd+shift+L)
    ├── header (teal "Bright Data MCP — live capture" OR amber "Cached replay")
    ├── event log (streamed via EventSource)
    │   └── mode-specific rows: mcp_call, mcp_result, fixture_read,
    │       fixture_loaded, rows_built, airtable_write, complete
    │       (complete row has dynamic suffix per refreshPhase)
    └── footer (kbd hint, close button)
```

### 6.2 Brand palette (semantic Tailwind tokens)

From CLAUDE.md §8, wired in [`tailwind.config.js`](frontend/tailwind.config.js):

| Token | Hex | Use |
|---|---|---|
| `base` | `#0A0C12` | page background |
| `surface` | `#161B2B` | card background |
| `signal-blue` | `#3B82F6` | brand / calm / citation anchors |
| `signal-teal` | `#3FB8AF` | stable / live mode |
| `signal-amber` | `#FFAA33` | warning / seeded mode |
| `signal-red` | `#FF5247` | critical |
| `ink-primary` | `#EEF1F8` | primary text |
| `ink-muted` | `#9AA3B8` | secondary text |
| `ink-dim` | `#5A6178` | tertiary / hint text |

All state pills, the risk-scale legend, the activity indicator, the FlowPanel header, and the settings-gear mode toggle reference these same tokens — color coherence is enforced by Tailwind class reuse, not by manual copy-paste.

### 6.3 Trigger mode + URL sync

- **Initial mode** read from `?mode=live|seeded` (default `live`)
- **Settings gear** toggles via `handleModeChange(mode)` → `setTriggerMode(mode)` + `history.replaceState` updates URL
- **Activity indicator** colors the trigger-mode label teal (live) or amber (seeded) — glanceable confirmation
- **FlowPanel** consumes the current mode when the chord fires; SSE URL built as `/api/live-pull/stream?mode={mode}`

### 6.4 Trust-contract rendering ([`components/CitedText.tsx`](frontend/src/components/CitedText.tsx))

Regex-parses `\[(\d+(?:\s*,\s*\d+)*)\]` in any text. For each citation:
- Resolves to `citations.find(c => c.n === N)` (memoized Map)
- Renders as anchor link to `#source-{n}` (jumps to the numbered source card below)
- Hover title shows `metric · source_url`
- Unresolved citation indices render in `signal-red` with dotted underline (would expose hallucinations — currently always zero)

### 6.5 Refresh lifecycle ([`components/FlowPanel.tsx`](frontend/src/components/FlowPanel.tsx))

```
SSE "complete" event arrives
   ↓ 350ms beat (lets operator see the "complete" line)
setRefreshPhase("refreshing")    suffix: "— refreshing dashboard…" (pulsing italic)
   ↓
await onComplete()               App.tsx refetches /vendors + /status,
                                 vendor cards re-render in state
   ↓
setRefreshPhase("updated")       suffix: "— dashboard updated ✓" (bright mode-color)
                                 overlay: bg-black/80 → bg-black/30
                                          (700ms CSS transition — cards visible behind)
   ↓ 2500ms
setConfirmFaded(true)            suffix opacity fades to dim grey (700ms)
                                 panel stays open until operator closes
```

This was a fix in step 7.6 — the original implementation had the suffix hardcoded so the indicator never resolved.

---

## 7. Honesty & trust contracts (what's enforced where)

### 7.1 The trust contract (every AI claim is sourced)

- **Backend enforces structure:** `summarizer.py` builds a numbered SOURCES list before the prompt is sent; the prompt's strict JSON schema demands [N] markers; `validate_citations()` post-parse audits.
- **Frontend enforces visibility:** `CitedText` renders [N] as anchor links; `DetailPanel` shows the audit badge (✓ all claims sourced / ✗ N unsourced); unresolved citations render in red.
- **Verified:** Veridian narrative — 11 sources cited, 0 hallucinated. Stripe narrative — 6/8 sources used, 0 hallucinated.

### 7.2 The honesty contract (live vs seeded must not be lied about)

- **The boundary lives in `live_pull.py::stream_live_pull`** — distinct event types per mode (`mcp_call`/`mcp_result` vs `fixture_read`/`fixture_loaded`).
- **The events carry the truth:** `data_path: "bright-data-mcp"` vs `data_path: "local-disk"`, and a `label: "cached_replay"` marker for seeded events.
- **Frontend renders whatever arrives** — it cannot fake events because the SSE event source is the truth.
- **The mode label is glanceable:** activity indicator + FlowPanel header both color-code to mode (teal vs amber).
- **The seeded-mode FlowPanel header explicitly says** "Cached replay — network not used", with subtitle pointing at `?mode=live` for the real path.

### 7.3 Event validation (no false-positive events in the schema)

- **Capture-time:** `capture.py`'s conservative pattern matcher casts a wide net; optional `validator` callback (Claude) gates which candidates become event rows. False-positive rate empirically high without the validator (e.g., "Stripe Communications" PR agency, Twilio CFO share sales, Snowflake CEO pay disclosures — all caught and rejected).
- **Post-hoc:** `clean_todays_events.py` validates already-banked event rows and deletes rejects. Verified: 17 of 19 candidates rejected with reasons.
- **Audit pass:** `audit_signal_prefixes.py` reclassifies misleading `[leadership]`/`[lawsuit]` notes prefixes on sentiment rows — they don't drive scoring but would mislead a detail-view consumer.

---

## 8. Demo wiring (acts 1–5 from CLAUDE.md §5)

### 8.1 Operator playbook

1. **Pre-show:** `python scripts/run_live_pull.py --reset` to clean up any rehearsal rows.
2. **Browser:** open `http://localhost:5173`. Confirm activity indicator shows `trigger: live` (teal).
3. **Act 1 (15s):** narrate the 6-vendor grid. Veridian critical, gradation through Twilio/Stripe warning to Plaid/Snowflake/AWS stable.
4. **Act 2 (30–45s):** press `Ctrl/Cmd + Shift + L`. FlowPanel opens; SSE stream shows real Bright Data MCP call to `search_engine` for Stripe, results count + duration, then row construction + Airtable write + Veridian finale. On `complete`, overlay fades, Veridian visibly ticks up to 81.2.
5. **Act 3 (20s):** close flow panel; Veridian's sparkline shows the spike, legal dimension lights up, convergence chip reads 6.
6. **Act 4 (30s):** click Veridian → Claude generates summary live (~5–15s, sourced); narrative now references the lawsuit + CEO Marisha Chen departure with anchor-linked citations.
7. **Act 5 (15s):** close detail panel; close the gear-driven seeded fallback narrative (gear → SEEDED toggle; press chord again → cached replay path runs the same flow).

### 8.2 Network failure fallback

- Click gear → toggle `SEEDED`. Activity indicator flips to amber `trigger: seeded`.
- Chord fires the cached path. FlowPanel header reads "Cached replay — network not used" in amber; events labeled `cached_replay`.
- Veridian still escalates to 81.2 (finale rows are scripted), but the audience sees the truth about the data source.

### 8.3 Rehearsal cycle

- `python scripts/run_live_pull.py --reset` OR gear → "reset live-pull rows" button. Both POST `/live-pull/reset`. Deletes rows tagged `live-pull-beat:` only; doesn't touch the staged Veridian arc, audit-promoted rows, or historical capture data.

---

## 9. File inventory

### Backend (Python, FastAPI)

| File | LOC | Purpose |
|---|---|---|
| [`main.py`](backend/main.py) | ~70 | FastAPI app, endpoints, SSE wiring |
| [`foreshock/api.py`](backend/foreshock/api.py) | 237 | Vendor overview + detail + trajectory + cache |
| [`foreshock/alerts.py`](backend/foreshock/alerts.py) | 188 | `Alert` dataclass + `evaluate_alert()` |
| [`foreshock/capture.py`](backend/foreshock/capture.py) | 293 | Per-class queries, MCP calls, row construction, optional validator callback |
| [`foreshock/live_pull.py`](backend/foreshock/live_pull.py) | 437 | Hero pull + the live/seeded switch + streaming generator |
| [`foreshock/scoring.py`](backend/foreshock/scoring.py) | 440 | CDC diff + weighted-component scoring (pure functions) |
| [`foreshock/summarizer.py`](backend/foreshock/summarizer.py) | 406 | Claude summary call + trust-contract auditor + deterministic fallback |
| [`foreshock/validator.py`](backend/foreshock/validator.py) | 197 | `validate_event()` + `classify_signal()` — tight Claude calls |

### Backend scripts (CLIs / one-offs)

| Script | Purpose |
|---|---|
| `run_daily_capture.py` | Pulls all 5 real vendors via 4 query classes; APPEND-writes Type 2 rows |
| `run_live_pull.py` | CLI of the live/seeded/reset/dry-run paths; mirrors the chord trigger |
| `clean_todays_events.py` | Post-hoc Claude validation of today's banked event rows (deletes rejects) |
| `audit_signal_prefixes.py` | Reclassifies misleading `[leadership]`/`[lawsuit]` notes prefixes |
| `whatif_promote_events.py` | In-memory simulation of "what if we promoted these untagged events?" |
| `test_scoring.py` | Pipeline smoke test: scoring on Veridian (critical) + Stripe (stable then warning) |
| `test_alerts.py` | Smoke test: alert payload structure on Veridian + Stripe |
| `test_summary.py` | Smoke test: full Claude summary + trust-contract audit on Veridian + Stripe |
| `test_brightdata_mcp.py` | First-contact verification of the MCP connection |
| `test_airtable_write.py` | First-contact verification of Type 2 append-write |
| `test_recency_filter.py` | Verifies the `after:` recency filter returns 2026-era results |

### Frontend (React, TypeScript)

| File | LOC | Purpose |
|---|---|---|
| `App.tsx` | 146 | Top-level: state, keyboard chord, header layout, modal coordination |
| `main.tsx` | 10 | ReactDOM bootstrap |
| `types.ts` | 101 | TypeScript types incl FlowEvent union (the honesty schema in type form) |
| `lib/api.ts` | 30 | Typed fetch helpers (vendors, detail, status, SSE URL builder) |
| `components/VendorCard.tsx` | 59 | Card on the grid |
| `components/StateBadge.tsx` | 20 | Color-coded state pill |
| `components/Sparkline.tsx` | 104 | Inline SVG trajectory; threshold guides at 30/60 |
| `components/CitedText.tsx` | 68 | Renders `[N]` markers as anchor links + validates resolution |
| `components/DetailPanel.tsx` | 299 | Slide-in vendor detail with AI summary, sources, recent signals |
| `components/RiskScale.tsx` | 52 | Header legend: 0–30 stable / 30–60 warning / 60–100 critical |
| `components/ActivityIndicator.tsx` | 46 | Always-on "monitoring active" + last pull + trigger mode |
| `components/FlowPanel.tsx` | 440 | SSE consumer, mode-honest event log, refresh lifecycle |
| `components/SettingsGear.tsx` | 201 | Mode toggle + shortcut reminder + reset button |

### Other

- `CLAUDE.md` — build context / product knowledge (was created on build day 1; still source of truth for product vision and roadmap-not-yet-built)
- `SPEC.md` — *this file*
- `README.md` — minimal scaffolding
- `LICENSE` — MIT
- `backend/.env` — `BRIGHTDATA_API_TOKEN`, `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `ANTHROPIC_API_KEY` (gitignored)
- `backend/foreshock/fixtures/seeded_real_pull.json` — cached MCP response for `--seeded` mode (currently holds 9 real Stripe news hits from a `--save-seed` run)

---

## 10. External integration points

| System | How we talk to it | What it returns |
|---|---|---|
| **Bright Data MCP** (hosted) | `streamablehttp_client(https://mcp.brightdata.com/mcp?token=...)` + `mcp.ClientSession` | `search_engine` results (organic) as JSON-in-text-block; ~2–4s |
| **Airtable** | `pyairtable.Api(...).table(base, "signals")` with formula filters | Type 2 rows |
| **Anthropic** | `anthropic.Anthropic(api_key=...)` → `client.messages.create(...)` | Sonnet-4.6 responses, strict JSON in practice |

`.env` keys live in `backend/.env`. Both Bright Data and Anthropic have been verified live; Airtable is the system of record.

---

## 11. Current data state (the live scoreboard)

```
vendor          score    state      conv   signals   notable
─────────────────────────────────────────────────────────────────────────────────────────
Veridian Pay    68.2     CRITICAL    5      13        staged 30-day arc; finale lands via live-pull
Twilio          49.5     WARNING     4      22        2 validated events + 1 audit-promoted TCPA
Stripe          35.9     WARNING     3      37        1 audit-promoted CTO Singleton departure
Plaid           20.8     STABLE      2      20        sentiment + news_vol only
Snowflake       18.9     STABLE      1      20        sentiment + news_vol only
AWS             16.6     STABLE      2      15        sentiment + news_vol only
─────────────────────────────────────────────────────────────────────────────────────────
                                            127 rows total
```

**After a live pull lands:**
- Veridian → 81.2 (CRITICAL, conv=6, legal_event count 0→1, +13.0 to score)
- Real-vendor data appends to whichever vendor was the live-pull target (Stripe by default)

---

## 12. Known limitations + quirks

### 12.1 Capture
- **`[news]` query template returns 0 hits for some vendors** (Plaid, Twilio, AWS in the last run). The bare `{vendor} news after:2026-01-01` gets squeezed out by Google's news vertical. The other 3 classes carry the volume. Logged as roadmap in CLAUDE.md §11a.
- **Bare-name vendor queries pull noise.** Stripe queries pulled "Stripe Communications" (PR agency); AWS pulled "Tim Cook"; Plaid pulled "Zimmer Biomet". Mitigated by the Claude validator + the prefix audit. Logged as roadmap in CLAUDE.md §11a (use `"Stripe Inc."` / `"Amazon Web Services"` disambiguators).
- **`LEADERSHIP_VERBS` only matches conjugated forms** (`steps down`, not `step down`). The Stripe CTO Singleton announcement said "to step down" and was missed by the heuristic — caught only by the audit pass. Logged as roadmap.

### 12.2 Scoring
- **`open_roles` metric is captured but never scored.** Schema-aware but no component reads it yet.
- **`funding_event` metric defined but never observed in current data.** Schema-aware.
- **News volume scoring asymmetry:** label "layoff news" maps to score 99; numeric count 8 maps to score 30. If a vendor's latest news_volume changes from label to count (or vice versa), the diff would show a drop where there isn't one. Currently happens only for Veridian (label) vs everyone else (count).
- **Sentiment heuristic is keyword-based** — placeholder per CLAUDE.md §1. Claude owns sentiment in the AI summary layer; the keyword scores are noisy priors only.

### 12.3 Summary cache
- **In-process dict** — restart loses cache. Fine for single-instance demo; production would want Redis.
- **Cache invalidation is by key** (`(name, latest_capture, signal_count)`). New rows auto-invalidate. But the cache grows over a long session — no eviction. Demo lifespan only.

### 12.4 Live pull
- **Idempotency via tag-then-reset**, not via unique IDs. Re-running live-pull duplicates Veridian finale rows. Reset works by tag prefix.
- **`run_live_pull` and `stream_live_pull` duplicate some orchestration code.** Refactor candidate — share an `_execute_pull(on_event_callback)` core.
- **Live MCP results can return 0** under rate-limiting (seen during back-to-back testing). The flow reports 0 honestly; downstream still works (no sentiment rows, just the news_volume row + Veridian finale).

### 12.5 Frontend
- **No real-time push** — dashboard polls on user-driven refresh (vendor click, page reload, live-pull completion). No websocket.
- **Detail panel doesn't auto-refresh when underlying data changes** — closes/reopens require a click.
- **Settings gear closes on outside-click and Esc**, but doesn't sync mode back from URL after the user manually edits the address bar (one-way: gear → URL).
- **Sparkline anchors max to 60** (so the critical band is always visible on the y-axis) — vendors that breach 60 (Veridian) will show their topmost point right at the chart top edge. Visually fine.

### 12.6 Trust contracts
- **The "audit-promoted" rows use real source URLs** (FinTech Futures for Singleton; JD Supra for TCPA) — verified manually. The Labaton Reddit thread was intentionally NOT promoted (soft source).
- **DEMO-SCENARIO and DEMO-SCENARIO-FINALE source_urls** in the Veridian rows are flagged in the UI as "(no public source — staged demo signal)". Trust contract still works — citations resolve to these entries; they just don't have clickable external links.

### 12.7 Operational
- **Both dev servers must be running for the demo:** `uvicorn` on `:8000`, Vite on `:5173`. No production deploy yet (CLAUDE.md mentions Railway hobby tier as the target — not provisioned).
- **No CI / no tests** — the `scripts/test_*.py` files are smoke runners, not unit tests. No CI pipeline.
- **No DB migrations / no schema management** — Airtable is the schema, and `typecast=True` on writes auto-extends single-select fields.

---

## 13. What's deliberately NOT built (out of scope by design)

Per CLAUDE.md §9 (Scope Guardrails):

**Not in MVP (in roadmap):**
- Other monitoring modules (competitor / supplier / M&A target)
- DORA register auto-generation
- Questionnaire / GRC workflow (OneTrust's lane)
- Security scoring (BitSight's lane)
- Multi-target comparison
- Team accounts / RBAC
- Automated historical backfill

**Build sequence remaining:**
- **Step 8** — Reskin pass (typography that isn't an AI-default tell, motion, seismograph motif as logo, proper density tuning, hover/focus states). Stack: UI/UX Pro Max skill, Anthropic frontend-design skill, Vercel web-design-guidelines skill.
- **Step 9** — Record the demo video (acts 1–5, clean genuine-live take, <5min, <300MB).

---

## 14. Enhancement-planning hooks

Some places where extension is natural:

- **New metric** → add to one of the four metric-class sets in `scoring.py` + a component (or fold into existing component). The diff logic auto-picks it up.
- **New query class** → add to `QUERY_CLASSES` in `capture.py`; row construction generalizes.
- **New vendor** → add to `REAL_VENDORS` (capture) and `DASHBOARD_VENDORS` (api). The validator + scoring + summary pipeline doesn't need to know vendor names.
- **New event detector** → add `_detect_xxx()` predicate + the loop in `capture_vendor` (already factored into a tuple-driven loop in step 4.6).
- **Tighten/widen the Claude validator** → edit `_PROMPT` constant in `validator.py`. Both `validate_event` and `classify_signal` share the same model and JSON-strict pattern.
- **Add an alert delivery channel** (email, slack) → `evaluate_alert` returns an `Alert` dataclass; wire a new consumer that subscribes to alerts. Currently only the dashboard consumes them.
- **Pre-cache summaries** for the dashboard's stable-vendors on startup → call `vendor_detail(name, force_refresh=True)` for each in a startup task. Currently lazy on click.
- **Persist summary cache to disk** → swap the in-process dict in `api.py` for a file-backed key-value store. Cache key already includes signal count.
- **Multi-tenant signals table** → add a `tenant_id` field everywhere; Airtable formula filters extend trivially.

---

## 15. Run book

### Dev mode

```bash
# Backend
cd backend
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend
npm install
npm run dev   # serves at :5173 with /api proxy to :8000
```

### Common operations

```bash
# Daily capture (all 5 real vendors)
cd backend && .venv/bin/python scripts/run_daily_capture.py

# Validate today's banked events
.venv/bin/python scripts/clean_todays_events.py --dry-run
.venv/bin/python scripts/clean_todays_events.py

# Audit signal prefixes
.venv/bin/python scripts/audit_signal_prefixes.py --dry-run
.venv/bin/python scripts/audit_signal_prefixes.py

# Live pull (CLI mirror of the chord)
.venv/bin/python scripts/run_live_pull.py --seeded            # demo safety
.venv/bin/python scripts/run_live_pull.py --live              # genuine pull
.venv/bin/python scripts/run_live_pull.py --live --save-seed  # capture fixture
.venv/bin/python scripts/run_live_pull.py --reset             # rehearsal cleanup

# Verify scoring on a vendor
.venv/bin/python scripts/test_scoring.py

# Run AI summary verification + citation audit
.venv/bin/python scripts/test_summary.py
```

### Reset paths (in order of bluntness)

| Action | Effect | Where |
|---|---|---|
| Settings gear → "reset live-pull rows" | Deletes `live-pull-beat:` tagged rows | UI |
| `python scripts/run_live_pull.py --reset` | Same | CLI |
| `POST /live-pull/reset` | Same | API |
| `POST /cache/summaries/clear` | Empties in-memory AI summary cache | API (rarely needed — auto-invalidates by key) |
| Manual Airtable row deletes | Last resort — be careful with the staged Veridian arc | Airtable UI |
