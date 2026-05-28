# foreshock

[![License: MIT](https://img.shields.io/badge/License-MIT-3FB8AF.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-3B82F6.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18-3B82F6.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/fastapi-uvicorn-3B82F6.svg)](https://fastapi.tiangolo.com/)

> **Foreshock feels it.**

Continuous business-health monitoring for the critical ICT vendors a fintech GRC team is on the hook for. Foreshock watches the leading indicators that precede vendor failure — leadership exits, lawsuits, layoffs, hiring freezes, sentiment turns, SEC 8-K filings — appends a Type-2 history to Airtable, runs a CDC diff against a weighted six-component risk score, and renders fully-cited GRC narratives that pass a verifiable zero-hallucination citation audit. Output is DORA Article 28-shaped: one click exports a multi-vendor ICT register PDF.

**Every vendor failure has foreshocks. We catch them.**

[Live App](https://YOUR-RAILWAY-URL)

---

## The gap

GRC platforms watch paperwork. Security raters watch the attack surface. Competitive-intelligence tools watch generic news. None of them watch business-health deterioration with a GRC-shaped scoring model and a verifiable audit trail.

> Your vendors are changing right now. Nobody's watching.

---

## Screenshots

<!-- Replace these with real captures before submission. -->

**Dashboard — fleet overview, risk scores, seismograph sparklines**
![Dashboard](docs/screenshots/dashboard.png)

**Vendor detail — cited AI narrative, signal timeline, sourced events**
![Vendor detail](docs/screenshots/vendor-detail.png)

**ICT Register PDF — DORA Article 28-aligned, one-click export**
![ICT register PDF](docs/screenshots/ict-register.png)

---

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 18 · TypeScript · Vite · Tailwind · shadcn primitives |
| Backend | FastAPI (Python 3.11) · uvicorn |
| AI | Anthropic SDK · `claude-sonnet-4-6` · strict-JSON output · citation auditor |
| Web data | Bright Data MCP (hosted) — four-action coverage |
| Regulatory data | SEC EDGAR submissions API (direct, via `data.sec.gov`) |
| Data store | Airtable · two tables (`signals` Type-2 SCD, `vendor_config`) |
| PDF | ReportLab + bundled General Sans / Sometype Mono |
| Hosting | Railway Hobby — always-on, no cold start |
| Repo | GitHub public · MIT |

---

## Bright Data MCP — four actions

Foreshock exercises the full four-action surface of the Bright Data MCP server. The hosted endpoint is reached at `https://mcp.brightdata.com/mcp`.

| Action | Tool(s) used | Where it lives |
|---|---|---|
| **Discover** | `search_engine` across five query classes per vendor (news, lawsuit, layoff, leadership, open_roles) | `backend/foreshock/capture.py` |
| **Access** | Bright Data Web Unlocker (bundled with `search_engine` / `scrape_as_markdown`) — bypasses bot detection on commercial sources | implicit in every MCP call |
| **Navigate** | `scrape_as_markdown` follows search results onto the source page when the heuristic needs more context | `backend/foreshock/capture.py` (fallback chain) |
| **Extract** | `scrape_as_markdown` → Claude `claude-sonnet-4-6` parses to structured event rows; `web_data_*` extractors wired for future use | `backend/foreshock/capture.py`, `backend/foreshock/validator.py` |

Latency-critical surfaces (the demo live pull) use only the fast base tools (`search_engine`, `scrape_as_markdown`) — never a polling `web_data_*` extractor on stage.

---

## DORA Article 28 positioning

The EU's **Digital Operational Resilience Act, Article 28**, requires financial entities to maintain a register of contractual arrangements with ICT third-party service providers and to assess concentration risk and substitutability on an ongoing basis. Today GRC teams reconcile that register by hand against questionnaires that age the moment they are filed.

Foreshock treats the register as living evidence. Every monitored vendor carries a continuously-updated signal history, a per-component score with weights documented in the methodology appendix, and a citation-audited AI narrative. The one-click **ICT Register PDF** covers every vendor in a single document — cover page with fleet summary and citation-audit verdict, per-vendor sections with sourced narratives, shared methodology appendix, fleet-wide footer attestation. It is the artifact a regulator or auditor can read end-to-end.

---

## Setup

### Prerequisites

- Python 3.11
- Node 20+
- Airtable base with a `signals` table and a `vendor_config` table
- API credentials for Bright Data, Airtable, and Anthropic

### Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Purpose |
|---|---|
| `BRIGHTDATA_API_TOKEN` | Bright Data MCP authentication |
| `AIRTABLE_API_KEY` | Airtable personal access token |
| `AIRTABLE_BASE_ID` | Airtable base ID (full URL tolerated; the leading segment is parsed out) |
| `ANTHROPIC_API_KEY` | Anthropic API key for `claude-sonnet-4-6` |

### Install

```bash
# Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm ci
```

### Run locally

```bash
# Terminal 1 — backend on :8000
cd backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend on :5173 (proxies /api → :8000)
cd frontend
npm run dev
```

Open `http://localhost:5173`.

### Build for production

```bash
cd frontend && npm ci && npm run build
cd ../backend && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port "$PORT"
```

The FastAPI app serves the built React bundle from `frontend/dist/` and exposes the API under `/api/*`. Healthcheck: `GET /api/health`.

---

## Verified endpoints (local)

- Dashboard: `http://localhost:5173`
- API health: `http://localhost:8000/api/health`
- Single-vendor PDF: `http://localhost:8000/api/vendors/Snowflake/report.pdf`
- ICT Register PDF: `http://localhost:8000/api/export/ict-register`
- Trust audit JSON: `http://localhost:8000/api/trust/audit`
- Live SEC lookup: `http://localhost:8000/api/vendors/lookup?name=Salesforce`

Full endpoint inventory and SSE event shapes: see [SPEC.md §19](SPEC.md).

---

## License

MIT. See [LICENSE](LICENSE).
