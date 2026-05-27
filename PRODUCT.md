---
register: product
---

# Foreshock — Product Anchor

> The strategic source-of-truth for every design decision. Persisted at repo root so every Impeccable command (and any other tooling) reads from one place.
>
> If a design choice doesn't trace to something below, it's a reflex, not a decision.

---

## Users

A solo or 1-of-2-person **GRC / compliance team at a mid-market fintech** ($50M–$2B revenue) responsible for **DORA Article 28 obligations** on a stack of **15–40 critical ICT vendors**.

### Day-to-day

- Owns the third-party risk register, vendor exit-plan readiness, and concentration-risk board reporting.
- Spends most of the week on paperwork-based monitoring that goes stale between annual reviews.
- Carries the blame when a vendor failure is later judged "should have been seen earlier."

### Working context

- Works outside business hours frequently: quarter-close, post-incident, board prep, end-of-day catch-up.
- Reviews the vendor scoreboard from a laptop, in a home office, in dim ambient light.
- Makes a weekly judgment call: which row to escalate to the CISO before logging off.

---

## Product Purpose

Watch the **business-health signals** that precede ICT vendor failure — leadership departures, lawsuits, hiring contractions, glassdoor decline, news volume, sentiment direction — across public web sources. Score the convergence. Fire an alert when a vendor crosses critical. Generate a **sourced GRC narrative** that maps every claim back to a citation. Produce a DORA-Article-28-shaped evidence artifact on demand.

The gap: GRC platforms watch paperwork; security raters watch the attack surface; **nobody watches business health in real time**. Foreshock fills that lane.

The narrated line: *"the layoff precedes the breach."*

---

## Brand Voice — three words

### calibrated
**Instrument precision.** The product IS a readout, not a chart with chrome. The trust contract is measurement honesty: every claim cites a source, every score traces to a component, every component traces to its data. The banner's faint registration marks and unbroken trace state this visually — a calibrated instrument.

### charged
**Energy held in reserve, released only at earned moments.** Veridian's escalation past the critical threshold. The live-pull beat landing. A vendor row crossing from stable to warning. The AI summary regenerating with a new lawsuit citation. These are moments where the product gets to be loud.

**Everywhere else, it does NOT bake energy into the chrome.** This is the discipline that separates Foreshock from cyberpunk-neon-everywhere SaaS: charge is *deserved*, not decorative.

### restrained
**95% calm dark canvas, one element draws the eye, no decoration competing.** The default everywhere except the charged moments. The banner is literally 95% dark with a single trace; the product should look the same.

Restraint is what makes "charged" land — if everything is charged, nothing is.

---

### The tension between the three

`calibrated · charged · restrained` are in deliberate tension.

- *Calibrated* pulls toward instrument honesty.
- *Charged* pulls toward emotional resonance when state changes.
- *Restrained* keeps both from becoming theatrical.

The tension IS the brand.

---

## Physical-Scene Sentence (theme justification)

> *"A one-person compliance team in a dimmed home office at 9:30 PM on a Thursday, scanning the vendor scoreboard for what changed since the morning, deciding whether one row warrants waking the CISO before signing off."*

This forces the answer: dim ambient light + tired eyes + state-color cells that need to be **unambiguously distinguishable** → **dark canvas with high-saturation accent cells** (teal stable / amber warning / red critical) is the right environmental fit.

Not dark "because tools look cool dark." Dark because the user's eyes are there at that hour.

---

## Anti-References — what Foreshock pointedly does NOT look like

Cross-checked against Impeccable's reflex-reject aesthetic lanes plus this project's CLAUDE.md §8 direction. When in doubt during the reskin, run any visual choice past this list first.

| Anti-reference | Why it's the wrong reflex |
|---|---|
| **Navy-and-gold fintech cliché** (Bloomberg-orange-on-black; JPMorgan-navy + gold accents; Stripe-purple-on-cream) | First-order training reflex for "fintech." Foreshock uses cooler signal-blue + warm signal-amber, not regal navy + gold. |
| **Terminal-cyberpunk SaaS** (neon green/cyan on black, monospace everywhere, "hacker" aesthetic) | Saturated by every B2B security product. Foreshock's restraint is the differentiator. The blue→amber crossing is dramatic but quiet; not "hacker." |
| **Editorial-typographic** (Klim/Fraunces display serif + small mono labels + ruled separators + monochromatic) | Per Impeccable: by 2026 "every Stripe-adjacent and Notion-adjacent brand has landed here." Foreshock isn't a magazine. Wordmark stays sans, not serif. |
| **SaaS-cream / Linear-glass** (pastel gradients, light backgrounds with glass-blur cards, big-friendly-rounded everything) | Wrong mood for "the layoff precedes the breach." The product is about catching stress in vendors, not about looking like a serene productivity tool. |
| **The hero-metric template** (big number + small label + supporting stats + gradient accent + identical card grid below) | One of Impeccable's absolute bans. The dashboard already doesn't do this; the brand surfaces should reinforce, not contradict. |
| **AI-gradient-text headlines** (`background-clip: text` on a purple→pink gradient on the hero word) | Absolute ban. The "foreshock" wordmark in the banner is solid off-white. Keep it solid. |

---

## Strategic Principles (the operating rules)

These are the rules every design decision answers to. If a choice contradicts one of these without an explicit reason, it's wrong.

### 1. Every claim cites a source
The trust contract is the product. UI surfaces citations as anchor-linked text. PDFs list source URLs. Sentiment narratives include `[N]` markers that resolve. Trust-contract audit always shows PASS or names the unresolved citation.

### 2. Charge is earned, never baked in
Don't decorate the calm states. Save visual energy for: state changes, threshold crossings, the live-pull beat, the dashboard-updated confirmation, the DORA-export amber callout. Anywhere else: quiet dark canvas, restrained type, one thing drawing the eye.

### 3. Honesty over polish
Demo Veridian is tagged DEMO. Live MCP calls show `data_path: bright-data-mcp`. Cached replays show `data_path: local-disk` and the label `cached_replay`. We never pretend a fixture is a live call. We never inflate convergence_count to look more critical.

### 4. The wave is the brand
The seismograph trace from the banner is the product's signature visual. Sparklines = traces. The dashboard reads as an instrument panel, not a marketing site. Avoid generic chart libraries' default styling.

### 5. One family does most things
Don't pair display + body unless the voice needs it. Tabular figures via OpenType `tnum`, not a second mono family — except where mono alignment is structurally functional (the SSE event flow in the FlowPanel reads as terminal output by genre and uses mono there).

### 6. Reskin pass discipline (Stage 3+)
- Run a design choice past the **anti-references list** above before committing.
- Run any color past the **OKLCH + tinted-neutrals + ≤15%-saturated-accents** rules in DESIGN.md.
- Run any font choice past **Impeccable's reflex-reject list** AND **CLAUDE.md §8's banned defaults**.
- Run any visual flourish past the **"charge is earned"** test — does it serve a charged moment or decorate a calm one?

---

## Glossary (terms used consistently across the codebase + this file)

- **Charged moment** — one of the specific surfaces that gets to be visually loud (see DESIGN.md § Charged moments). Anywhere else stays restrained.
- **Trust contract** — every factual claim in the UI traces to a numbered source URL.
- **Convergence** — multiple deteriorating signal dimensions simultaneously. The hero risk pattern.
- **Seismograph trace** — the visual metaphor; horizontal time-series line where amplitude = risk score. The banner shows one frozen frame; the sparklines on the dashboard show live ones.
- **DORA register** — the third-party risk register required under DORA Article 28. The compliance artifact Foreshock outputs (`/vendors/{name}/report.pdf`) is shaped to fit this.
