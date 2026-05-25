# Foreshock — Build Context (CLAUDE.md / Project Knowledge)

> **Purpose of this file:** the single source of truth for building Foreshock. Drop it in the repo root as CLAUDE.md (or /docs) so Claude Code has full context without re-explanation. Also serves as Claude Project knowledge in claude.ai. Last updated: May 25, 2026 (build day — kickoff done, credits live).

> **CURRENT STATUS (May 25, build open):** Credits distributed in the kickoff stream. Track is chosen AT SUBMISSION, not upfront — build it, then pick the strongest track (working lean: Track 2 Intelligence). Mentors available via @-tag in Discord. Vendor monitoring was named as an example use case in the kickoff: VALIDATION that Foreshock is centered in the theme, but the category is likely crowded, so the differentiation (business-health signals, NOT security scores — the BitSight gap: "the layoff precedes the breach") must be LOUD in the demo narration and the submission's additional-info field. Building in the VS Code Claude Code extension.

---

## 0. TL;DR for the coding agent

Foreshock is a continuous vendor-risk monitoring web app for fintech compliance teams. It watches a fintech's critical ICT vendors across public sources via Bright Data MCP, stores timestamped history (Type 2) in Airtable, runs a CDC diff to detect material change, scores risk, fires an alert when a vendor crosses threshold, and uses Claude to write a sourced AI risk summary. Built for the Bright Data "Web Data UNLOCKED" hackathon (May 25-31). Stack: React/Tailwind/shadcn + FastAPI + Claude (Sonnet 4.5) + Bright Data MCP + Airtable + Railway. Theme: "build what wasn't possible with stale/locked data" — Foreshock's whole value is real-time business-signal monitoring, so freshness IS the product.

**MVP = the five-act demo (Section 5). Build that, nothing more. Resist scope creep.**

---

## 1. Product

- **Name:** foreshock (lowercase wordmark). Tagline: "Foreshock felt it." Positioning: every vendor failure has foreshocks; we catch them.
- **What it does:** continuous monitoring of vendor BUSINESS-HEALTH signals (layoffs, leadership exits, lawsuits, sentiment, funding distress) — the leading indicators that precede vendor failure, from locked public sources, scored and alerted in near-real-time.
- **Audience:** the GRC lead at a mid-market fintech ($50M-$2B rev) managing DORA compliance for a stack of critical ICT vendors, often a one-person compliance team.
- **The gap it fills:** GRC platforms (OneTrust, Prevalent, ProcessUnity) watch paperwork/registers; security raters (BitSight, SecurityScorecard) watch the attack surface. NEITHER watches real-time business-health signals. That's Foreshock's lane — and it's the one corner of TPRM where stale data defeats the purpose, which is exactly the hackathon theme.
- **Differentiation line:** "BitSight watches the security posture; Foreshock watches the business health. The layoff precedes the breach. We catch the foreshock."
- **Trust contract:** every claim in a risk summary links to its source signal. Answers the "AI data is plausible but wrong" objection. Synthesis WITH receipts.

---

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + Tailwind + shadcn/ui | Enterprise-credible dark dashboard |
| Backend | FastAPI (Python) | — |
| AI | Claude (Sonnet 4.5) | Summary-only pattern: never pass raw rows; pass scored diff summary |
| Web data | Bright Data MCP (MANDATORY) | See Section 3 |
| Data store | Airtable | Type 2 timestamped history (Section 4) |
| Processing | Pandas | Scoring + diff |
| Hosting | Railway Hobby ($5/mo) | Always-on, NO cold-start (Prism lesson) |
| Repo | GitHub public, MIT | github.com/eschaq, clean README from Day 1 |
| Dev env | Claude Code + VS Code (Chromebook/Crostini) | — |

**Hackathon requirement:** must demonstrably use ≥1 Bright Data product; strongest submissions use MCP for all four actions (Discover, Access, Navigate, Extract). Track 2 (Intelligence) primary, Track 1 (Agent) secondary. Prize: $5,000 + AI Startup Program fast-track (the program is high-value for this data-hungry product).

---

## 3. Bright Data MCP — setup, tiers, fallback

**Hosted server (zero install):** add as custom connector:
```
https://mcp.brightdata.com/mcp?token=YOUR_API_TOKEN
```
No local npx process. $250 credits/participant on Day 1.

**Tier reality (CRITICAL):**
- **Free tier (Rapid Mode) — 3 tools:** `search_engine`, `scrape_as_markdown`, `discover`. Includes Web Unlocker (bypasses bot detection) even free.
- **Pro Mode (pay-as-you-go, covered by $250 credits):** structured `web_data_*` extractors — `web_data_crunchbase_company`, `web_data_linkedin_posts`, `web_data_yahoo_finance_business`, etc.

**Four actions → tools:**
| Action | Free | Pro |
|---|---|---|
| Discover | `discover`, `search_engine` | same |
| Access/Navigate | `scrape_as_markdown` + Web Unlocker | `scraping_browser.*` |
| Extract | `scrape_as_markdown` → Claude parses | `web_data_crunchbase_company`, `web_data_linkedin_posts` |

**THE FALLBACK PATH (de-risks the build):** if a structured `web_data_*` tool disappoints, fall back to `scrape_as_markdown` + Claude parsing. Build the capture layer to degrade gracefully to this. Free-tier base tools alone can carry the demo.

**Latency config:** structured `web_data_*` tools POLL (default timeout 600s — slow). Base tools (`search_engine`, `scrape_as_markdown`) are fast (2-4s). Set `BASE_MAX_RETRIES` 1-3 for reliability. **For the live demo pull, use FAST base tools only** — never a polling extractor on stage.

---

## 4. Data Architecture — Type 2 + CDC

- **Type 2 (SCD):** every signal reading is a NEW timestamped row, never an overwrite. Preserves full trend history (the product depends on trends). Maps from the capture sheet schema.
- **CDC diff:** compare latest pull vs prior state for same vendor+metric. The delta = "change detected." Fires alerts.
- **Airtable schema (per row):** capture_date, vendor_name, vendor_type, metric, value, unit, source_url, sentiment, notes, is_demo_vendor
- **Metrics:** headcount_linkedin, open_roles, news_volume, news_sentiment, leadership_change, legal_event, glassdoor_rating, sentiment_review, funding_event, outage_incident
- **Scoring dimensions (tune weights during build):** leadership stability + legal events weighted highest (sharpest failure signals); headcount trajectory + sentiment as trend amplifiers. Target: real vendors score "stable," Veridian scores "critical."
- **Alert logic:** threshold on scored diff. Hero alert = CONVERGENCE (multiple signals crossing at once), not a single-metric trip.

---

## 5. The Five-Act Demo (THIS IS THE MVP)

Real captured/current data on 5 real vendors + staged history on 1 fictional vendor (Veridian Pay) + ONE fast live pull that lands the dramatic beat.

1. **Dashboard (15s):** 6 vendors, risk scores + seismograph-style trend sparklines. Real vendors calm (teal), Veridian already deteriorating. Sparklines prove "watching for weeks."
2. **Live pull (30-45s, money shot):** fast Bright Data MCP call. First pulls fresh real signals on real vendors (appended — proves it works on real companies). Then lands Veridian's fresh beat (lawsuit + 2nd exec exit). Type 2 rows write with fresh timestamps. Narration draws the real-vs-demo line.
3. **Diff + alert (20s):** CDC diff; Veridian's converging signals (now 5) cross threshold; alert fires; UI refreshes red.
4. **AI summary (30s):** Claude runs LIVE on the real diff, narrates the convergence with sourced citations. Not hardcoded. ~3-5s.
5. **Close (15s):** platform vision (same engine → competitors, suppliers, M&A targets) + "Foreshock felt it."

**Real vs fictional split (state it explicitly in narration — it's a strength):** "These five are real vendors we're monitoring live. Veridian is a demo company so we can show the full alert cascade honestly, without inventing a crisis for a real business."

**Honesty guardrail:** real vendors = real data only. All manufactured drama on fictional Veridian Pay.

---

## 6. Demo Safety (build this, ~1hr, highest-leverage reliability investment)

- **`--live` / `--seeded` switch** on the fetch function. Live = real MCP call. Seeded = reads single fetch from local cached response (zero network dependency), everything else (UI, diff, live Claude summary) runs identically.
- **Pre-recorded fallback clip** of the exact pull, cued up, for live presentation.
- **Primary deliverable = recorded video** (like Prism; lablab requires it, it's what most judges score, it travels). Record a clean genuine-live take. Live presentation (if any) is a bonus with seeded-mode + clip as safety nets.
- Principle: never let an external call block the demo flow (AI-to-Code "mock dependencies" rule).

---

## 7. Build Sequence (riskiest-first — DO NOT leave the scary part for last)

The Prism-failure-mode to avoid: leaving the hard integration until tired. Build the load-bearing risk first.

1. **Bright Data MCP connection + one fast pull** (the scary novel piece). Prove `search_engine`/`scrape_as_markdown` returns vendor signals. Verify in smoke test BEFORE build day if possible.
2. **Airtable Type 2 write** — pull writes a timestamped row. Prove the data layer.
3. **CDC diff + scoring** — compare pulls, score the delta. The detection core.
4. **Alert trigger** — threshold crossing fires an alert. The convergence logic.
5. **Claude AI summary** — scored diff → sourced narrative. The summary-only pattern.
6. **Dashboard UI** (working/ugly first) — vendors, scores, sparklines, alert state.
7. **The `--live`/`--seeded` switch + demo data wiring** — Veridian staged history loaded, live pull lands the beat.
8. **Reskin pass** (LATE) — design skill stack applies the brand (Section 8). Working app first.
9. **Record the demo video** — clean take, the five acts.

Get acts 1-5 (a working end-to-end pull→diff→alert→summary) proven by mid-build. Everything after is polish + the demo wiring.

---

## 8. Brand (for the reskin pass)

- **Wordmark:** lowercase "foreshock". **Tagline:** "Foreshock felt it."
- **Palette (functional — encodes risk state):** Base `#0A0C12` / Surface `#161B2B` / Signal Blue `#3B82F6` (calm/healthy/brand) / Teal `#3FB8AF` (stable) / Signal Amber `#FFAA33` (warning/alert) / Critical Red `#FF5247` (threshold crossed). Text `#EEF1F8` / `#9AA3B8` / `#5A6178`.
- **Risk-state logic:** blue/teal = stable → amber = foreshock detected → red = critical. The dashboard color shifts ARE the risk signaling.
- **Motif:** seismograph. Logo = needle with a spike. Sparklines read as seismograph traces.
- **Typography:** AVOID Inter, Roboto, Arial, system fonts, AND Space Grotesk (all AI-default tells). Pick something with character via the design skill stack.
- **References:** G&CO, Betterment — dark cinematic fintech, confident, NOT cozy.
- **Reskin tools (Claude Code, install before build, read each SKILL.md first — supply-chain risk):** UI/UX Pro Max (primary, design-system database), Anthropic frontend-design (anti-slop direction), Vercel web-design-guidelines (accessibility pass). Optional: Impeccable.
- **Reference mockups:** foreshock_brand.html (hero + motion), foreshock_dashboard.html (dashboard layout).

---

## 9. Scope Guardrails (read when tempted to add a feature)

**IN scope (the MVP = the five acts):** named-vendor monitoring, MCP pull (4 actions), Type 2 capture, CDC diff, risk scoring, threshold alert, AI sourced summary, source verification, dashboard, the live-pull + Veridian beat, the --live/--seeded switch.

**OUT of scope (roadmap — note in pitch, do NOT build):** other monitoring modules (competitor/supplier/M&A target), DORA register auto-generation, questionnaire/GRC workflow (OneTrust's lane), security scoring (BitSight's lane), multi-target comparison, team accounts/RBAC, automated historical backfill.

**The build is meaty for solo (CDC + alerts + AI summary + live pull + dashboard). The five acts are the MVP. When tempted to add: is it in one of the five acts? No → roadmap it.**

---

## 10. Demo data assets

- **vendor_capture.csv / Google Sheet:** 5 real vendors (Stripe/Payments, Plaid/Bank Data, Snowflake/Data Infra, Twilio/Comms-2FA, AWS/Cloud Infra) + fictional Veridian Pay with full staged 30-day risk-crescendo arc (headcount 480→410, leadership departures, glassdoor decline). Veridian's FINAL beat (lawsuit + 2nd exec exit) is NOT staged — the live demo pull lands it.
- Real-vendor current data comes from the live MCP pull at demo time (daily manual capture was dropped). Headcount is MCP-era (locked source).

---

## 11. Open items to resolve during build (non-blocking)

- Tune risk-scoring weights against real captured data
- Pick a few named real fintechs as illustrative "users" for the deck (e.g., a neobank, a payments co, a BaaS provider)
- Confirm $250 credits cover the `web_data_*` extractors; confirm scrape_as_markdown fallback works per source
- Domain/trademark check for Foreshock (non-blocking)
- Discord confirms: multi-track submission, track-2 scoping, X-tagging-mandatory, mentors

---

## 12. Submission checklist (May 30-31)

- Video <5min, <300MB, demo-first (50%+ screen recording), own voice
- GitHub public, MIT, README with setup + screenshots + live link
- Live app on Railway, tested in incognito
- Cover image 16:9 (seismic motif)
- Title <50 chars, short desc <255 chars, long desc 100+ words
- Additional Info: restate the business-signal-monitoring gap + name the 4-action Bright Data usage + "scale beyond hackathon" paragraph
- Live-phase X engagement: submission post within 1hr, tag @lablabai (confirm if prize-mandatory)
- Roadmap slide = primary judging artifact (same engine → other entity classes)
