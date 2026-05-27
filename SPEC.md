# Foreshock — System Specification (current state)

> Snapshot as of 2026-05-27. Documents what's actually shipped and behaving — not roadmap. For build-sequence narrative see git log; for vision and explicit roadmap see [CLAUDE.md](CLAUDE.md).

---

## 0. TL;DR

Foreshock is a continuous third-party vendor risk-monitoring app for fintech GRC teams. It watches **6 named vendors** (5 real + 1 staged demo) via **Bright Data MCP**, appends Type-2 SCD history to **Airtable**, runs a **CDC diff + 5-component weighted risk score**, fires **convergence alerts** at critical, and produces a **fully-cited GRC-analyst narrative via Claude Sonnet 4.6**. A React/Tailwind dashboard renders the scoreboard with sparkline trajectories, click-to-drill detail panels, an always-on activity indicator, a settings-gear **live/seeded mode toggle** for demo network safety, and **one-click DORA evidence PDF export**. An async **agent pipeline** (Pull → Clean → Promote) runs unattended via API trigger or cron.

Build acts 1–7.5 complete. Visual reskin (act 8) and demo video (act 9) remain.

Source: ~5,400 lines (~3,000 Python backend / ~1,500 TS frontend / ~900 supporting scripts).

---

## 1. Positioning (the gap being filled)

Three adjacent categories — each watches the wrong thing for this use case:

| Category | Examples | Watches | Misses |
|---|---|---|---|
| GRC platforms | OneTrust, Prevalent, ProcessUnity, Archer | Paperwork, registers, questionnaires | Real-time external reality |
| Security raters | BitSight, SecurityScorecard, UpGuard, Black Kite | Attack surface, certs, breach proxies | Business-health deterioration |
| Comp/CI tools | Owler, Crayon, Klue, Similarweb | Generic competitor news | GRC-shaped scoring + DORA artifacts |

**Foreshock's lane.** Business-health signal monitoring + GRC-shaped output. Thesis: *the layoff precedes the breach.* Leadership turnover, lawsuits, hiring freeze precede vendor failure by weeks-to-months. No adjacent player watches them in a GRC context.

**Demo line.** "BitSight watches the security posture; Foreshock watches the business health. The layoff precedes the breach."

## 2. Audience

Solo (or one-of-two) GRC/compliance lead at a mid-market fintech ($50M–$2B rev), managing 15–40 critical ICT vendors under DORA (or analogous regime). Currently spending ~5 hrs/week on manual vendor monitoring. Personal failure mode: post-incident "should have seen earlier."

---

## 3. Architecture at a glance

```
┌──────────────┐    daily      ┌─────────────────────────────────┐
│ Bright Data  │ ◀──── pull ──│  capture.py / observation.py    │
│   MCP        │               │  (4 query classes/vendor)       │
└──────────────┘               └────────────┬────────────────────┘
                                            │ Type-2 rows
                                            ▼
                               ┌─────────────────────────────────┐
                               │  validator.py (Claude YES/NO)   │
                               │  drops false-positive events    │
                               └────────────┬────────────────────┘
                                            ▼
                               ┌─────────────────────────────────┐
                               │  Airtable signals table         │
                               │  (append-only SCD)              │
                               └────────────┬────────────────────┘
                                            ▼
                  ┌───────────────────────────────────────────────┐
                  │  scoring.py — CDC diff + 5-component score    │
                  │  alerts.py — convergence/threshold alerting   │
                  │  summarizer.py — Claude + trust-audit         │
                  └────────────────────────┬──────────────────────┘
                                           ▼
       ┌──────────────────────────────────────────────────────────┐
       │  FastAPI (api.py, agent.py, live_pull.py, report.py)     │
       │  REST + SSE endpoints                                    │
       └────────────────────────┬─────────────────────────────────┘
                                ▼
               ┌──────────────────────────────────────┐
               │  React dashboard                     │
               │  grid · detail · flow · agent · PDF  │
               └──────────────────────────────────────┘
```

---

## 4. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + TS + Tailwind + shadcn primitives | Semantic tokens (`base`, `surface`, `signal-*`, `ink-*`, `rule`, `overlay-*`) |
| Backend | FastAPI (Python 3.11) | uvicorn + WatchFiles; in-process summary cache |
| AI | Anthropic SDK, `claude-sonnet-4-6` | Strict-JSON output, citation auditor, deterministic fallback |
| Web data | Bright Data MCP (hosted, no local install) | `search_engine` + `scrape_as_markdown` (free tier, fast) + `web_data_*` (Pro tier) fallback |
| Data | Airtable (`typecast=True` auto-extending selects) | Schema = Airtable; no migrations |
| PDF | ReportLab + bundled TTFs | General Sans + Sometype Mono, no system font drift |
| Hosting | Railway Hobby ($5/mo) | Always-on, no cold start |
| Repo | GitHub public, MIT | github.com/eschaq |

---

## 5. Core capabilities (shipped)

### 5.1 Continuous signal capture
- 5 real vendors: **Stripe, Plaid, Snowflake, Twilio, AWS**; 1 demo: **Veridian Pay**
- 4 query classes per vendor via Bright Data MCP `search_engine`: `news`, `lawsuit`, `layoff`, `leadership`
- Recency-filtered (`after:2026-01-01`); disambiguated names (`"Stripe Inc."`, `"Amazon Web Services"`)
- Fallback chain: structured `web_data_*` → `scrape_as_markdown` + Claude parse
- Claude validator gates event candidates before Airtable write (17 of 19 false-positives rejected in recent run)

### 5.2 Type-2 SCD history
- Every reading appended as new timestamped row; never overwritten
- Full historical reconstruction at any point in time
- 127 rows live across 6 vendors

### 5.3 CDC diff + weighted scoring
- Latest-vs-prior per metric over 60-day window
- 5-component score (0–100):
  - **Leadership 30%** — 35 pts/event, 55 for C-suite (CEO/CTO/CFO/COO/CIO/chief), cap 100
  - **Legal 25%** — 40 pts/event, cap 100
  - **Headcount 20%** — linear in % decline (-5% = 50, -10% = 100)
  - **Sentiment 15%** — window-avg of {-1, 0, +1} across news + reviews + glassdoor drop
  - **News volume 10%** — label (low/normal/high/layoff) or numeric `(n-5)*10` cap 100
- **State bands:** <30 stable / 30–60 warning / ≥60 critical
- **Convergence count** = number of metrics with `deteriorating=true` simultaneously (drives alert type)

### 5.4 Alerts
- Stable → no alert
- Warning + convergence ≥2 → convergence alert
- Critical → convergence or single-metric alert
- Alert carries full sourced evidence trail for downstream summary

### 5.5 AI risk narratives — the trust contract
- Claude Sonnet 4.6, GRC-analyst voice, **strict-JSON** output
- Fields: `headline / sentiment_read / narrative / recommended_action`
- **Every factual claim must carry `[N]` citation** to a numbered source URL
- Post-parse **trust auditor** (`validate_citations`) parses every `[N]`/`[N,M]` marker, flags unresolved
- Frontend renders valid citations as anchor links to source cards; unresolved render in **amber-dotted-underline** (visual hallucination flag)
- Verified examples: Veridian (11 sources, 0 hallucinated, 100% coverage); Stripe (6/8 sources used, 0 hallucinated)
- **Graceful degradation:** no API key or any error → deterministic summary, labeled `generated_by="deterministic-fallback"`

### 5.6 DORA evidence PDF
- One-click from any vendor detail panel: `GET /vendors/{name}/report.pdf`
- ReportLab-rendered; bundled TTFs (no system-font drift)
- Structure: amber disclaimer callout → header → risk narrative (with `[N]` citations) → component table → numbered sources list
- Demo-source URLs flagged "(no public source — staged demo signal)" — honesty preserved on paper
- The compliance artifact for "what did you know and when" auditor questions

### 5.7 Live-pull demo flow (the hero moment)
- Triggered by `Ctrl/Cmd+Shift+L` (or settings gear button)
- SSE stream → FlowPanel renders per-event log (MCP call → result → row build → Airtable write → complete)
- Two modes, settings-gear toggleable, URL-synced:
  - **live** — real Bright Data MCP call (~2–4s, `data_path: "bright-data-mcp"`)
  - **seeded** — cached fixture (~100ms, `data_path: "local-disk"`, labeled `"cached_replay"`)
- Both paths land identical downstream effects (Type 2 rows → re-score → fresh Claude summary)
- Veridian finale (lawsuit + CEO Marisha Chen departure) fires in either mode — score 68.2 → 81.2, convergence 5 → 6
- Rehearsal cleanup: `POST /live-pull/reset` deletes only `live-pull-beat:`-tagged rows

### 5.8 Unattended daily agent pipeline
- `POST /agent/run` → async pipeline **Pull → Clean → Promote**
- `GET /agent/stream/{job_id}` SSE stream renders per-stage progress in AgentPanel
- PULL: all MCP calls for 5 real vendors + open_roles + Veridian staged beats
- CLEAN: Claude validator drops false-positive events
- PROMOTE: surviving rows Type-2-appended to Airtable
- Railway cron-trigger ready (07:00 UTC)

### 5.9 Fleet-level briefing
- Header card above grid: 3–4 sentence Claude synthesis of all-vendor portfolio state
- Labels AI origin explicitly (`"AI · synthesized from scored fleet state"` vs `"deterministic fallback"`)
- Top border color reflects worst-vendor state (red > amber > teal)

---

## 6. Product surface

### 6.1 Backend API (FastAPI on :8000)

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | Health check |
| `/vendors` | GET | Dashboard grid (all vendors, score + state + sparkline trajectory + components) |
| `/vendors/{name}` | GET | Detail panel (overview + alert + AI summary + recent 40 signals) |
| `/vendors/{name}/report.pdf` | GET | DORA evidence PDF |
| `/fleet/summary` | GET | Fleet briefing (Claude-synthesized portfolio narrative) |
| `/status` | GET | Activity indicator data (monitoring active, signal count, last capture) |
| `/live-pull/stream?mode=live\|seeded` | GET | SSE stream of live-pull events |
| `/live-pull/reset` | POST | Rehearsal cleanup |
| `/cache/summaries/clear` | POST | Diagnostic cache flush |
| `/agent/run` | POST | Kick off unattended daily pipeline (returns `job_id`) |
| `/agent/stream/{job_id}` | GET | SSE stream of pipeline progress |

### 6.2 Frontend (React + Tailwind on :5173)

- **Dashboard grid** — 6 vendor cards (state pill, score, inline sparkline, convergence + signal count + capture date)
- **Sparklines** — inline SVG; threshold guides at 30/60; draw-on animation (one-shot, `prefers-reduced-motion` honored); stroke color matches current state
- **Fleet overview card** — Claude briefing above grid, AI-origin label visible
- **Settings gear** — live/seeded mode toggle + reset button + shortcut hint; bound to `?mode=` URL param
- **Activity indicator** — always-on pulsing dot + monitoring claim + last pull + signal count + trigger-mode color
- **Risk scale legend** — header strip showing band thresholds
- **Detail panel** — right-slide modal (320ms ease-out-quart): large score, components table, alert with cited narrative, trust-audit badge, numbered sources list, recent-signals table, DORA PDF download
- **FlowPanel / AgentPanel** — SSE consumers; per-event log in monospace (only place Sometype Mono is used — reads as terminal output)
- **Keyboard chord** `Ctrl/Cmd+Shift+L` — triggers agent pipeline

---

## 7. Data model

**Airtable `signals` table** (Type 2 SCD, append-only):

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
| `notes` | Long text | Provenance prefixes: `[news]`, `[lawsuit]`, `[leadership]`, `[off-topic]`, `auto-detected:`, `validated:`, `audit-promoted:`, `live-pull-beat:`, `STUBBED` |
| `is_demo_vendor` | Checkbox | True only for Veridian Pay |

**Metric vocabulary:** `headcount_linkedin`, `open_roles`, `glassdoor_rating`, `news_sentiment`, `sentiment_review`, `news_volume`, `leadership_change`, `legal_event`, `funding_event`, `outage_incident`.

**VendorOverview payload (dashboard):** `{name, type, is_demo, score, state, convergence_count, signal_count, latest_capture, trajectory[{date,score,state}], components[{name,score,weight,contribution,drivers}]}`.

**VendorDetail payload (drill-down):** VendorOverview + `alert` + `summary{headline,sentiment_read,narrative,recommended_action,citations[],generated_by}` + `recent_signals[40]`.

---

## 8. The trust contract (the key differentiator vs. generic AI tools)

The core objection to AI-in-compliance is "plausible but wrong." Foreshock's structural answer:

1. **AI never sees raw rows** — only the scored diff summary (summary-only pattern)
2. **Every claim must cite** — system prompt enforces, validator audits, frontend visually flags unresolved
3. **Numbered sources panel** — every `[N]` in narrative links to a numbered card with metric + capture_date + snippet + URL
4. **Demo data flagged** — staged Veridian signals show "(no public source — staged demo signal)" in UI + PDF
5. **Deterministic fallback** — when AI unavailable, summary still ships, labeled `generated_by="deterministic-fallback"`
6. **Honesty boundary in live-pull** — SSE `data_path` field distinguishes `bright-data-mcp` from `local-disk` replay; frontend cannot fake events

---

## 9. Honesty boundaries (built-in, not bolted on)

| Surface | Honesty mechanism |
|---|---|
| AI summary | Trust-contract auditor + visual unresolved-citation marker |
| Demo vendor | `is_demo_vendor` flag; UI badge; PDF disclaimer; staged sources flagged |
| Live vs seeded mode | SSE event `data_path` field; settings-gear toggle; URL param; color-coded mode label |
| AI vs deterministic | `generated_by` field on summary; fleet briefing label "AI · synthesized" vs "deterministic fallback" |
| PDF | Amber disclaimer callout on page 1 ("Example output — illustrative only") |
| Off-topic capture | `[off-topic]` prefix on notes (e.g. "Stripe Communications" PR agency, "Tim Cook" for AWS) |

---

## 10. Current live scoreboard (2026-05-27)

```
vendor          score    state      conv   signals   notable
─────────────────────────────────────────────────────────────────────────────────
Veridian Pay    68.2     CRITICAL    5      13        staged arc; finale via live-pull
Twilio          49.5     WARNING     4      22        2 validated + 1 audit-promoted event
Stripe          35.9     WARNING     3      37        1 audit-promoted CTO Singleton
Plaid           20.8     STABLE      2      20        sentiment + volume only
Snowflake       18.9     STABLE      1      20        sentiment + volume only
AWS             16.6     STABLE      2      15        sentiment + volume only
─────────────────────────────────────────────────────────────────────────────────
                                            127 rows total
```

After live-pull: Veridian → 81.2 (CRITICAL, conv=6, legal_event 0→1, +13.0 to score).

---

## 11. Current limitations (honest gaps)

### Capture
- News volume queries return 0 for some vendors (Plaid, Twilio, AWS) — Google News vertical thin on bare-name searches
- `LEADERSHIP_VERBS` only matches conjugated forms (`steps down`) — misses infinitive (`to step down`); audit pass catches what live capture misses
- Bare-name queries pull noise; mitigated by Claude validator + post-hoc prefix audit, not by query design

### Scoring
- `open_roles` captured but not yet scored (component slot reserved)
- `funding_event` defined but never observed
- News-volume asymmetric: label `"layoff news"` = 99; numeric count of 8 = 30; mode-switching label↔count shows phantom drops
- Sentiment heuristic keyword-based (placeholder); Claude replaces in summary narrative

### Operational
- No real-time push to frontend — refresh required after capture
- In-process summary cache (no Redis); cache grows unbounded over long sessions
- Detail panel doesn't auto-refresh after live-pull
- Live-pull idempotency via tag-then-reset, not unique IDs — re-running duplicates Veridian finale rows
- No CI / no unit tests (only `scripts/test_*.py` smoke runners)
- No DB migrations (Airtable IS the schema; auto-extending selects via `typecast=True`)

---

## 12. Explicitly out of scope (roadmap-only, not built)

Per CLAUDE.md scope guardrails — useful for moat analysis to know what we deliberately don't compete on:

- Other monitoring modules (competitor / supplier / M&A target) — same engine, different entity class
- DORA register auto-generation (one-off PDF export only ships)
- Questionnaire / vendor onboarding workflow — OneTrust's lane
- Security scoring (CVE, cert hygiene, attack-surface metrics) — BitSight's lane
- Multi-target side-by-side comparison
- Team accounts / RBAC / SSO
- Automated historical backfill
- Webhooks / Slack notifications / email digests
- API for external consumers (read-only, internal-only currently)

---

## 13. Candidate moats (hypotheses for the competitor sweep to validate)

Pre-analysis bets. Test each against actual incumbent depth in §1.

1. **The business-health signal category itself.** Adjacent players don't watch leadership / legal / hiring as a coherent risk feed. Is there a pure-play vendor-business-health monitor in market? Suspect: not in GRC shape.
2. **The trust contract pattern.** AI summary + numbered citations + post-parse validator + visual unresolved-marker. Most AI compliance tools currently ship plausible-but-unsourced narratives. Mechanically copyable but requires opinionated design discipline.
3. **DORA evidence PDF as one-click artifact.** Most GRC tools require composing reports manually. "Article 28 paper trail in one click" is concrete and on-trend (DORA enforceable Jan 2025). Do OneTrust / Prevalent ship anything analogous?
4. **Convergence-based alerting (not single-signal trips).** Multiple deteriorating dimensions crossing simultaneously is the actually-rare event; single signals are noisy. Suspect this is novel in GRC vendor monitoring specifically.
5. **Type-2 SCD on business signals.** Full historical reconstruction supports "what did you know and when" auditor questions. GRC platforms do this for paperwork; nobody does it for business signals.
6. **Honesty boundaries as a productized aesthetic.** Demo vs. real flag, live vs. cached mode flag, AI vs. deterministic label, source vs. demo-source flag — built into UI / PDF / SSE. Hard to retrofit; easy to differentiate on.
7. **Bright Data MCP integration depth.** All 4 actions (Discover, Access, Navigate, Extract) wired with graceful tier fallback. Compounds as Bright Data tooling expands.

---

## 14. Questions to drive the competitor sweep

- Which incumbents ship cited AI narratives (vs. plausible-but-unsourced)? Who has a trust contract pattern in production?
- Which adjacent tools watch leadership / legal / hiring signals — and how do they score / present them?
- Who ships DORA Article 28-shaped one-click evidence exports?
- Does "vendor business intelligence" exist as a named category — distinct from "vendor security risk" and "competitive intelligence"?
- Where does Owler/Crayon overlap with TPRM, and why has nobody bridged them?
- What's the going price point for vendor monitoring at this scope? (informs WTP for solo GRC lead)
- Which categories do mid-market fintechs already buy from — and where would Foreshock land in their procurement diagram?
- Who else uses Type-2 SCD for vendor signals? (suspect: nobody — it's standard for paperwork registers but not signals)

---

## 15. File inventory (for the curious)

**Backend Python** (`backend/foreshock/`):

| File | LOC | Purpose |
|---|---|---|
| `api.py` | 237 | Dashboard payload builders; vendor overview/detail; summary cache |
| `alerts.py` | 188 | Alert evaluation; convergence detection |
| `capture.py` | 293 | Daily MCP capture; 4 query classes; Type-2 row construction |
| `live_pull.py` | 437 | Hero live/seeded pull; Veridian finale; SSE streaming |
| `observation.py` | ~150 | Pull-pipeline helpers shared by CLI + agent |
| `scoring.py` | 440 | CDC diff; 5-component weighted risk score; state bands |
| `summarizer.py` | 406 | Claude Sonnet summary; trust-contract audit; fallback |
| `validator.py` | 197 | Event gate; Claude YES/NO; signal classification |
| `agent.py` | ~300 | Unattended daily pipeline with SSE (Pull → Clean → Promote) |
| `report.py` | ~200 | DORA PDF export via ReportLab |

**Frontend TypeScript** (`frontend/src/`):

| File | LOC | Purpose |
|---|---|---|
| `App.tsx` | 146 | Top-level: state, keyboard chord, header, grid, modals |
| `types.ts` | 101 | TypeScript interfaces (FlowEvent union, VendorOverview, etc.) |
| `lib/api.ts` | 30 | Typed fetch helpers |
| `components/VendorCard.tsx` | 59 | Grid card; state/score/sparkline/footer |
| `components/StateBadge.tsx` | 20 | State pill (color-coded) |
| `components/Sparkline.tsx` | 104 | Inline SVG trace with threshold guides + draw-on animation |
| `components/CitedText.tsx` | 68 | Renders `[N]` markers as anchor links to source cards |
| `components/DetailPanel.tsx` | 299 | Right-slide detail panel |
| `components/RiskScale.tsx` | 52 | Header band-threshold legend |
| `components/ActivityIndicator.tsx` | 46 | Always-on pulsing dot + monitoring claim + trigger mode |
| `components/FleetOverview.tsx` | 135 | Fleet-level Claude briefing card |
| `components/FlowPanel.tsx` | 440 | SSE consumer for live-pull |
| `components/SettingsGear.tsx` | 201 | Dropdown: mode toggle + shortcut + reset |
| `components/AgentPanel.tsx` | (large) | SSE consumer for daily agent pipeline |
