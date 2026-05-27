---
register: product
---

# Foreshock — Design System (DESIGN.md)

> Persisted visual spec. Read by every Impeccable command and by the frontend during the reskin pass. Update via `impeccable document` (or by hand) when the visual system evolves. Pairs with PRODUCT.md (strategic anchor).
>
> **Status:** this file is the *spec* for Stage 3's reskin pass. Some tokens here already exist in `frontend/tailwind.config.js`; others are additions that Stage 3 will introduce. The "Drift from current implementation" section at the end flags what's spec-but-not-yet-applied.

---

## Color

### Strategy: **Restrained**
Per Impeccable's four-step color-commitment axis (Restrained → Committed → Full palette → Drenched), Foreshock sits firmly at the **Restrained** end: tinted neutrals do 95% of the surface work, and saturated accents are used deliberately and sparingly.

- Most of the canvas is the dark base. Most surfaces are very subtle tonal lifts off the base.
- Saturated color (the state palette) appears only on state badges, sparkline strokes, threshold guides, and a few specific accent moments. **Never** as background fills for chrome, **never** as gradients in the chrome.
- The four-color state palette (`teal/amber/red/blue`) is a *functional* color system: each color encodes a specific UI semantic. Decoration uses the tinted neutrals.

### Locked palette (anchored to the banner's actual pixel values)

#### Base / ground (95% of the canvas)
| Token | Value | Notes |
|---|---|---|
| `--base` | `#080809` | Page canvas. Cool-tinted near-black (sampled from banner corners; 220° hue, ~25% S, 5% L). **Never** `#000`. |
| `--base-tint-1` | `#0A0C12` | Slightly bluer base used as the absolute page background. Already in CLAUDE.md §8 / Tailwind config as `base`. |
| `--surface` | `#161B2B` | Card / panel surface, slightly elevated from base. Already in Tailwind as `surface`. |
| `--surface-2` | `#1B2236` | Secondary surface — rare; only when a panel sits inside a panel and visual nesting is unavoidable. **Prefer not to use** (see Layout rules: "nested cards are always wrong"). |

#### Ink / text
| Token | Value | Notes |
|---|---|---|
| `--ink-primary` | `#EEF1F8` | Body, wordmark, headings. Slightly cool-cast off-white. **Never** `#fff`. |
| `--ink-muted` | `#9AA3B8` | Secondary text, captions, helper labels. |
| `--ink-dim` | `#5A6178` | Tertiary text, separators, hint copy, footer disclaimer. |

#### Signal — the state palette (the only saturated colors in the system)
Used **only** for state cells, badges, sparkline strokes, threshold guides, the FlowPanel mode header, and a few specific charged-moment accents. NEVER for chrome.

| Token | Value | Semantic |
|---|---|---|
| `--signal-blue` | `#3B82F6` | Brand / citation anchors / calm-waveform left side of the banner. |
| `--signal-teal` | `#3FB8AF` | STABLE state — the most-common state in the system. |
| `--signal-amber` | `#FFAA33` | WARNING state. Also the peak-transition color in the banner. |
| `--signal-red` | `#FF5247` | CRITICAL state. The rarest color in the interface. |

#### Functional helpers (derived from the locked palette)
| Token | Value | Notes |
|---|---|---|
| `--rule` | `#21263B` | Hairline rules, table dividers (`base` + 8% cool tint). |
| `--overlay-strong` | `rgba(8, 8, 9, 0.80)` | Modal scrim during charged moments (live pull, detail panel open). |
| `--overlay-quiet` | `rgba(8, 8, 9, 0.30)` | Reduced scrim after live-pull "updated ✓" — lets the vendor cards behind show through. |

### Color rules

1. **Never `#000` or `#fff`** anywhere. Always one of the tinted neutrals.
2. **OKLCH preferred** for any new color derivations. Reduce chroma at lightness extremes (>90 or <10) to avoid garish.
3. **State colors saturated high** (60–80%); the dark canvas reads them as confident, not loud, because they're surrounded by very-low-saturation surroundings.
4. **Critical red is the rarest** color in the interface. Permitted on: Veridian's CRITICAL pill, the `≥60` threshold guide on sparklines, the alert headline when state==critical, the FAIL marker in the trust-contract audit. Nowhere else.
5. **No gradients in chrome.** Gradients are reserved for *charged moments only* (e.g., the sparkline glow at the moment of an alert firing — TBD in Stage 3). Never on background fills, never on text.

---

## Typography

### Primary family: **General Sans** (Fontshare, free for commercial)
**Self-hosted** via `@fontsource/general-sans` or direct download into `frontend/public/fonts/`.

Why General Sans:
- **Survives both reject lists.** Not on Impeccable's reflex-reject font list (Inter / Space Grotesk / DM Sans / Plex / Outfit / Plus Jakarta / Instrument / Fraunces / Newsreader / Lora / Crimson / Playfair / Cormorant / Syne / Space Mono). Not on CLAUDE.md §8's banned defaults (Inter / Roboto / Arial / system / Space Grotesk).
- **Geometric humanist sans with character.** Distinctive lowercase `g` and `a`, single-storey `a` available as stylistic alternate. Reads "calibrated" — precise without being terminal/Plex.
- **Strong weight contrast** (300 → 700) supports hierarchy via weight, not just size.
- **Tabular OpenType numerals** via `font-feature-settings: "tnum"` — clean column alignment for the score numerals.
- **Not yet saturated** in the fintech/SaaS lane (vs. Inter / Geist which are everywhere).
- **One family handles wordmark, headings, body, data columns** — per Impeccable's principle that "a single well-chosen family with committed weight/size contrast is stronger than a timid display+body pair."

### Weights in use
| Weight | Use |
|---|---|
| **400 Regular** | Body text, table cells, paragraph copy |
| **500 Medium** | Emphasis, labels, table headers, FlowPanel event prefixes |
| **600 Semibold** | Section headers, panel titles, badge labels |
| **700 Bold** | Wordmark "foreshock", hero score numerals, critical-state badge text, AI-summary headline |

Skip 100, 200, 300, 800. Keep the scale committed.

### Scale (rem; root = 16px)
| Token | Size | Use |
|---|---|---|
| `--text-2xs` | `0.6875rem` (11px) | Micro labels, footer disclaimer text, citation tags `[N]` |
| `--text-xs` | `0.75rem` (12px) | Caption, helper, table small |
| `--text-sm` | `0.875rem` (14px) | Body small, table cells, FlowPanel event lines |
| `--text-base` | `1rem` (16px) | Body |
| `--text-lg` | `1.125rem` (18px) | Emphasized body |
| `--text-xl` | `1.375rem` (22px) | Section title, panel header |
| `--text-2xl` | `1.75rem` (28px) | Score numeral (vendor card) |
| `--text-3xl` | `2.5rem` (40px) | Score numeral (detail panel) |
| `--text-4xl` | `3.5rem` (56px) | Reserved — not currently used |

Adjacent-step ratio: 1.22–1.43. Above Impeccable's 1.25 floor.

### Wordmark treatment ("foreshock")

- General Sans Bold (700), **lowercase**.
- `letter-spacing: -0.02em` — tight, instrument-feel.
- Default rendering: solid `--ink-primary` (`#EEF1F8`). **Never** gradient-filled. **Never** on a colored background.
- Pairs with one of:
  - The horizontal seismograph trace (banner art / about page hero).
  - A tiny status dot to its left (header on the dashboard — already in place).
- Wordmark color in CRITICAL system state: still `--ink-primary`. Charge is in the state cells, not the wordmark.

### Numeric figures

Apply `font-variant-numeric: tabular-nums` (Tailwind: `tabular-nums`) on every numeric column and aligned-number context.

Already used on:
- Vendor card score numeral
- Score-component contribution column (PDF + detail panel)
- Sparkline tooltips
- FlowPanel event timing

### Optional mono — only where alignment is functional

**Sometype Mono** (Fontshare, free) is reserved for ONE place: the FlowPanel's SSE event log.

Justification: the event log reads as terminal output by genre. The `▸` prefixes, the `tool=search_engine vendor=Stripe` key=value pairs, the `duration_ms=2426` numerics — all of this is instrument-readout content. Mono there is functional, not decorative.

Anywhere else: tabular figures in General Sans cover the column-alignment need without introducing a second family.

### Reject list reminder (do not re-introduce by reflex)

Inter, Roboto, Arial, Helvetica, system-default, Space Grotesk, Space Mono, DM Sans, DM Serif Display / Text, Plus Jakarta Sans, Outfit, Instrument Sans / Serif, IBM Plex Sans / Mono / Serif, Fraunces, Newsreader, Lora, Crimson (all variants), Playfair Display, Cormorant (all variants), Syne.

---

## Layout

### Rules

1. **Cards are the lazy answer.** Use them only when truly the best affordance. **Nested cards are always wrong** (Impeccable absolute ban). Current audit: DetailPanel uses only one level of cards — keep it that way.
2. **Don't wrap everything in a container.** Most elements don't need one.
3. **Vary spacing for rhythm.** Section spacing scale: 8 / 12 / 16 / 24 / 32 / 48px. Tightest within a row, loose between sections. Avoid same-padding-everywhere monotony.
4. **One primary CTA per screen.** Subordinate everything else visually. **Exception — dashboard main view:** observational by design, no primary CTA is intentional. The hero action (live pull) is exposed via keyboard chord (Ctrl/Cmd + Shift + L) and the agent trigger button; the dashboard itself is a monitoring surface, not an action surface.
5. **No side-stripe borders.** `border-left` > 1px as a colored accent is banned (Impeccable absolute ban). For state, use the state pill, not a left stripe.
6. **Max content width** for the vendor grid: `7xl` (80rem) centered. Allows 3-col layout on lg, 2-col on md, 1-col on sm.

### Spacing scale
| Token | Value | Use |
|---|---|---|
| `--space-1` | `4px` | Hairline gap (icon-to-label) |
| `--space-2` | `8px` | Tight gap |
| `--space-3` | `12px` | Inner padding small |
| `--space-4` | `16px` | Inner padding default, card padding |
| `--space-5` | `20px` | Inner padding loose |
| `--space-6` | `24px` | Section gap |
| `--space-8` | `32px` | Major section gap |
| `--space-12` | `48px` | Hero space, between top-level zones |

### Radii
| Token | Value | Use |
|---|---|---|
| `--radius-sm` | `4px` | Badges, chips |
| `--radius-md` | `10px` | Cards, panels |
| `--radius-lg` | `14px` | Modal containers, large panels |

No `rounded-full` for non-pill elements. No mixed radii inside the same hierarchy level (Impeccable: "elevation-consistent / icon-style-consistent").

---

## Motion

### Default easing
- **Enter:** `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-quart)
- **Exit:** `cubic-bezier(0.7, 0, 0.84, 0)` (ease-in-quart)
- **No** spring, **no** bounce, **no** elastic.

### Durations
- `--dur-micro` 120ms — hover/focus, button press
- `--dur-std` 200ms — panel open, state change, sparkline update
- `--dur-complex` 320ms — modal/detail panel slide in
- Never > 500ms.

### Rules
- **Exit < Enter.** Exit animations at ~60–70% of enter duration (Impeccable + Material parity).
- **Transform + opacity only.** Never animate `width` / `height` / `top` / `left` / `padding` / `margin`.
- **`prefers-reduced-motion`** must disable: activity-indicator dot pulse, FlowPanel header streaming pulse, refresh-confirmation fade, dashboard card stagger. Keep state changes instant under reduced-motion.

### Where motion is permitted (charged moments)

The only places visual energy moves — everywhere else is static.

| Surface | Motion | Why |
|---|---|---|
| Activity-indicator dot | Continuous slow pulse | Saying "still watching" — the product's heartbeat |
| FlowPanel header dot | Pulse during streaming | "MCP call in progress" |
| Vendor card initial load | 40ms-staggered pop-in (translateY + opacity) | Stage-the-reveal of the grid |
| Live-pull complete | Backdrop fade strong → quiet (700ms) | Lets cards behind become visible without auto-closing the panel |
| "Dashboard updated ✓" suffix | Color flip teal/amber → dim (after 2.5s) | Confirmation lifecycle |
| Sparkline trace update | Path interpolation on data change (320ms) | The wave is the brand; updates should *move* like a seismograph |

Anywhere not on this list: instant transitions. Hover changes color only (no scale, no shadow). Buttons get focus rings, not press animations.

---

## Component principles

### `StateBadge.tsx`

- Border + background tint + text color all derive from the same state token (`--signal-{state}`).
- Background opacity 10–15%, border opacity 40–50%, text 100%.
- Uppercase, `letter-spacing: 0.08em`, weight 500, font-size `--text-2xs`.
- **Never** on a colored background.
- **Never** combined with an icon — the pill IS the affordance.

### `Sparkline.tsx`

- Stroke color matches the LATEST observation's state color.
- Threshold guides at score 30 and 60 — dashed, opacity 12–18%, in the corresponding state color (amber for 30, red for 60).
- Point dots at each capture date; latest dot 1.5× larger so the most-recent observation reads as the anchor.
- Tooltip on hover (web) / focus (kbd): date + score + state. Auto-dismiss after 1500ms.

### `VendorCard.tsx`

- Surface: `--surface` background, 1px `--rule` border, `--radius-md` corners.
- On hover/focus: border lightens to `rgba(255,255,255,0.15)`. **No scale transform** (avoid layout shift; Impeccable rule).
- Score numeral: `--text-3xl`, weight 700, `tabular-nums`, color follows state.
- Layout: state pill top-right, score mid-left, sparkline mid-right, footer row carries convergence count + signal count + latest-capture date. **Never** columnar/centered (Impeccable: visual hierarchy via composition, not uniformity).

### `DetailPanel.tsx`

- Slide-in from right via `transform: translateX(0)`, 320ms ease-out-quart.
- Backdrop `--overlay-strong` during initial open; reduces to `--overlay-quiet` AFTER the live-pull "updated ✓" lifecycle reaches its terminal phase (vendor cards behind become visible without closing the panel).
- Citation anchor links inline: `--signal-blue` color, underline-on-hover only.
- Source list: numbered cards, each with metric + capture_date + snippet + clickable URL. No nested cards inside; the outer `surface` is the only level.

### `FlowPanel.tsx`

- **Sometype Mono** font (the only place mono is used).
- Mode-honest coloring: `--signal-teal` accents in `--live` mode, `--signal-amber` in `--seeded` mode.
- Per-event line: `▸` prefix in state-mode color, then event content. **No icons** beyond the `▸` — the prefix is the affordance.
- Backdrop honesty: in `--seeded` mode, the header explicitly reads "Cached replay — network not used" with the amber accent.

### `SettingsGear.tsx`

- Outline-only icon (`stroke-current` from `--ink-muted`, transitions to `--ink-primary` on hover).
- Dropdown panel: `--surface` bg, `--rule` border, `--radius-md` corners.
- Mode toggle: side-by-side pill buttons. Active pill carries the mode's state color (teal/amber). Inactive pill is `--ink-muted` outline.
- Reset button: bottom of the panel, outline-only with `--rule` border, semantic-danger color on confirmation.

---

## Charged moments — the only places visual energy lands

These are the surfaces that get to be loud. Everywhere else stays restrained.

1. **A vendor crossing into CRITICAL.** Card state pill flips red, score numeral re-renders in red, sparkline stroke shifts to red. Latest dot enlarges.
2. **The live-pull MCP flow.** FlowPanel slides in over the dashboard with a colored header (teal=live / amber=seeded), streaming events line-by-line.
3. **The "dashboard updated ✓" confirmation.** Bright teal (live) or amber (seeded), fades to dim grey 2.5s after.
4. **The DORA evidence PDF export.** The amber disclaimer callout on page 1; the `PASS` verdict in green on page 3.
5. **Veridian's seismograph spike in its sparkline** at the moment the live-pull lands the lawsuit + CEO event. Sparkline animates the new path interpolation.

If a visual flourish doesn't trace to one of these moments, it's decoration. Per the brand voice: **charge is earned, never baked in.**

---

## Anti-patterns — never produce these

Cross-checked against Impeccable's absolute bans. Hard checklist.

| Banned | What it catches |
|---|---|
| **Side-stripe borders** | `border-left` > 1px as a colored accent on cards/list-items/callouts/alerts. Rewrite with full borders, background tints, or nothing. |
| **Gradient text** | `background-clip: text` + gradient. Use solid `--ink-primary`. Emphasis via weight or size, not color tricks. |
| **Glassmorphism as default** | Blurs / glass cards used decoratively. Rare and purposeful or nothing. |
| **The hero-metric template** | Big number + small label + supporting stats + gradient accent + identical card grid below. SaaS cliché. |
| **Identical card grids** | Same-sized cards × icon + heading + text, repeated endlessly. Vary by content density. |
| **Modal as first thought** | Modals are usually laziness. Exhaust inline / progressive alternatives first. |
| **Nested cards** | Always wrong. Use one level of card; if a "nested" element needs hierarchy, use spacing + headings instead. |
| **Em dashes** | Use commas, colons, semicolons, periods, or parentheses. Also not `--` (Impeccable copy rule). |

---

## Drift from current implementation (what Stage 3 will need to address)

Honest accounting of where the spec above ≠ what's in the code today.

| Token / Decision | Status |
|---|---|
| Color tokens (`base`, `surface`, `signal-*`, `ink-*`) | ✅ Already in `frontend/tailwind.config.js` and used throughout |
| `--rule`, `--overlay-strong`, `--overlay-quiet` | ❌ Not yet in Tailwind config — add in Stage 3 |
| `--surface-2` | ❌ Spec; not yet needed in any component |
| **Typography family (General Sans + Sometype Mono)** | ❌ **Currently uses system-default sans** (`ui-sans-serif`, `-apple-system`, etc. in index.css) — Stage 3 self-hosts General Sans, applies as default, swaps in Sometype Mono for FlowPanel |
| Weight scale (400/500/600/700) | 🟡 Components use Tailwind defaults; spec adds explicit hierarchy guidance |
| Spacing scale tokens | 🟡 Tailwind defaults are close; codify in tailwind.config in Stage 3 |
| Radii tokens | 🟡 Tailwind defaults are close |
| Motion / easing tokens | ❌ Currently uses Tailwind default `transition-colors` etc. — Stage 3 adds the ease-out-quart curves and reduced-motion gating |
| Charged-moment motion (sparkline path interpolation on update) | ❌ Not yet implemented — Stage 3 |
| Tabular numerals on score columns | ✅ Already in components via `tabular-nums` |
| Citation `[N]` styling | ✅ Already implemented via `CitedText.tsx` |
| State badges | ✅ Already matches spec |
| Vendor card layout | ✅ Already matches spec (state pill top-right, score bottom-left, sparkline bottom-right) |

---

## Stage-3 implementation checklist (forward-looking; not for execution in Stage 2)

When Stage 3 begins:

- [ ] Install `@fontsource/general-sans` + `@fontsource/sometype-mono` (or self-host from Fontshare downloads into `frontend/public/fonts/`)
- [ ] Update `frontend/src/index.css` to set `font-family: 'General Sans', ui-sans-serif, system-ui, sans-serif` on body
- [ ] Add Sometype Mono to FlowPanel.tsx via inline `font-family` or a dedicated `font-mono` token in Tailwind
- [ ] Extend `tailwind.config.js` with: `--rule`, `--overlay-strong`, `--overlay-quiet` (under `colors`); motion easings (under `transitionTimingFunction`); explicit text-size scale
- [ ] Add CSS for `prefers-reduced-motion` to disable: activity-indicator ping, FlowPanel header pulse, refresh-confirmation transition
- [ ] Verify state-color contrast (WCAG AA) against `--base` for: teal text, amber text, red text — adjust luminance if needed (keep hue, shift L slightly)
- [ ] Audit current code for the anti-patterns list above; report findings before remediation
- [ ] Decide on wordmark kerning adjustment for `f-o` at 24px Bold (likely needs a manual `letter-spacing` tweak for the `f→o` pair)

---

## Stage 4 — roadmap (post-MVP visual polish)

Items deferred past submission; track separately from the build.

- **Custom iconography.** Replace `PdfIcon` (DetailPanel export button) and `GearIcon` (SettingsGear) with seismograph-motif SVGs. PdfIcon → "document with waveform" (4-stroke custom). GearIcon → consider dropping the icon entirely and using a label-only `Settings` chip; if kept, swap for a brand-aligned outline form. Current icons are generic Feather lineart and don't carry the seismograph brand language used in the banner and sparklines.
