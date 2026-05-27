Foreshock dashboard — Impeccable audit (findings only)
A. Spacing inconsistencies
Double horizontal rule inside the header band
Location: App.tsx:124-147
border-b on the outer <header> plus a second border-t mt-3 pt-3 row for RiskScale + ActivityIndicator stacks two rules within one zone, giving the header a "boxed in" feel that competes with the page rhythm.
Fix: collapse to one row (drop the inner top-rule, use space-y between the two sub-rows) OR remove the outer bottom rule and let the inner divider be the single edge.

Header bleeds full-width; main is centered to max-w-7xl
Location: App.tsx:124,149
At wide viewports the title "foreshock" hugs the screen edge while the vendor grid sits centered — the title and the first card don't share a left baseline.
Fix: wrap header content in the same max-w-7xl mx-auto so the title aligns with the grid below.

FleetOverview uses p-5 (20px); VendorCard uses p-4; DetailPanel uses p-6
Location: FleetOverview.tsx:60, VendorCard.tsx:48, DetailPanel.tsx:71
DESIGN.md spacing scale is 4/8/12/16/24/32/48 — p-5 (20px) is unique to FleetOverview and breaks the rhythm.
Fix: pick p-4 (16px) or p-6 (24px) for FleetOverview to match the scale.

Out-of-scale spacings: mt-0.5, mt-1.5, gap-1.5, mb-1.5
Locations: VendorCard.tsx:62,72, RiskScale.tsx:21, SettingsGear.tsx:134,139
Tokens 2px (0.5) and 6px (1.5) aren't in the locked scale.
Fix: round to mt-1 (4px) or mt-2 (8px). gap-1.5 → gap-2.

VendorCard inner vertical rhythm is mt-4 then mt-3
Location: VendorCard.tsx:67,81
Two adjacent inner gaps at 16/12 — small enough that the eye reads them as the same value but they aren't. Either unify to one or make the difference deliberate (e.g., mt-4/mt-5).

DetailPanel internal section gaps mix space-y-6 (24px) with section-local mt-6 mb-2
Location: DetailPanel.tsx:71,199-201
Sources section breaks the parent's space-y-6 cadence with its own internal margins, so the gap before "Sources" reads larger than the gap before other sections.
Fix: rely on the parent's space-y-6 and drop the mt-6 on the inner <h3>.

B. Typographic hierarchy
Three different sizes used for the same UI semantic ("uppercase section label")
Locations: FleetOverview.tsx:62 text-[10px], VendorCard.tsx:72 text-[10px], DetailPanel.tsx:112,151,199,249 text-xs (12px), SettingsGear.tsx:69,76 text-[10px].
Fix: pick one — likely text-[11px] (DESIGN.md --text-2xs token) — for every uppercase section label.

Title→tagline jump is 24→12px in the header
Location: App.tsx:127-129
Skips two scale steps. The tagline reads disconnected from the title.
Fix: tagline at text-sm (14px) or text-base (16px) per the 1.22–1.43 adjacent ratio.

VendorCard uses text-3xl (30px) for score; DetailPanel uses text-4xl (36px) for score; DESIGN.md spec is 28/40
Location: VendorCard.tsx:69, DetailPanel.tsx:97
Tailwind's text-3xl/text-4xl defaults (30/36px) don't match the spec's --text-2xl=28px and --text-3xl=40px.
Fix: add the explicit DESIGN.md scale to tailwind.config.js fontSize (Stage-3 drift item §285) so component class names line up with spec values.

FleetOverview headline doesn't read as the highest-ranked element on the card
Location: FleetOverview.tsx:90-97
font-medium (500) at body size (16px) is barely above the narrative below (14px, muted). The headline should be the eye anchor; it currently competes with the supporting paragraph.
Fix: headline at text-lg font-semibold (or weight 700) to clearly outrank the supporting copy.

Tally chips ("N critical / warning / stable") at text-xs next to a 24px title
Location: App.tsx:132-135
The status counts sit at the same size as the tagline — they're more important than the tagline but visually rank below it.
Fix: tally chips at text-sm weight 500; tagline at text-xs ink-dim.

C. Color usage / token drift
Critical-red used outside its permitted list
Location: CitedText.tsx:51 — invalid citation rendered in text-signal-red.
DESIGN.md §61 explicitly enumerates the four permitted uses; "unresolved citation" isn't one. The honest semantic is "warning."
Fix: text-signal-amber for unresolved-citation styling.

Hover/border opacities not standardized — /15, /20, /30, /40, /50
Locations: VendorCard.tsx:48 border-ink-primary/15, SettingsGear.tsx:130,167 border-ink-primary/20, VendorCard.tsx:57 border-ink-dim/30, StateBadge.tsx:5-9 mixes /40 and /50.
Fix: lock to two opacities — /15 for resting/hover lift and /40 for state-pill borders. Make StateBadge use /40 uniformly (critical doesn't need its own value).

ink-primary/5 for soft button background isn't a token
Locations: SettingsGear.tsx:59,130,178
Used as the hover/press-state fill on the gear button, the reset button, and the Kbd chip. Five percent white-cast is brittle — when components nest it stacks.
Fix: add an explicit token (e.g., surface-hover: rgba(238, 241, 248, 0.05)) or use surface-2 from the spec.

backdrop-blur on the DetailPanel sticky header
Location: DetailPanel.tsx:47
DESIGN.md §276 calls out glassmorphism as anti-pattern unless purposeful. The blur here is decorative — a solid bg-base would read more confident.
Fix: drop backdrop-blur and use bg-base (no /95 alpha either).

Signal-blue weight on inline citations may be too prominent
Location: CitedText.tsx:50
text-signal-blue hover:underline font-medium — weight 500 on saturated blue inside a 14px paragraph makes citations more attention-grabbing than the claims they support.
Fix: drop to weight 400, rely on color alone for affordance.

D. Alignment
Header right-edge stats don't column-align with each other across rows
Location: App.tsx:132-141 vs 145-146
Top-row right cluster (critical/warning/stable counts + gear) and bottom-row right side (ActivityIndicator) both right-align, but the start of each cluster floats. The right edges line up; the left edges don't, so reading down the right column feels jagged.
Fix: pin both to the same content width OR explicitly stagger them as columns.

VendorCard footer balance is asymmetric
Location: VendorCard.tsx:81-90
Left: "convergence: 3" — 4 visible glyphs of weight. Right: "121 signals · latest 2026-05-27" — 25+ glyphs. justify-between distributes empty space but the visual masses don't balance.
Fix: move "convergence" to the right cluster ("121 signals · 3 converging · latest …") and put the latest-capture date on the left as a primary affordance.

DetailPanel score/sparkline row baseline
Location: DetailPanel.tsx:93-108
items-end aligns the bottoms of the score numeral and the sparkline, but the score has a 3-line composition (type + score+badge + meta) and the sparkline is one element. The sparkline visually floats relative to the score-block's vertical center.
Fix: align sparkline to the score-numeral baseline (the most-important glyph), not the meta line below it.

E. AI-default / generic feels
VendorCard layout is the hero-metric template (DESIGN.md §277 explicit ban)
Location: VendorCard.tsx:67-79
Big number + tiny uppercase "RISK SCORE" label below + a sparkline — this is exactly the SaaS cliché the spec calls out. The "RISK SCORE" label is the giveaway; the score's context is already in the card.
Fix: drop the "RISK SCORE" uppercase subtitle. Let the numeral + state pill carry the meaning. (DESIGN.md spec puts state pill top-right, score bottom-left, sparkline bottom-right — no caption needed.)

Identical card chrome across very different surfaces
Locations: FleetOverview.tsx:60, VendorCard.tsx:48, DetailPanel.tsx:167, DetailPanel.tsx:207,242
All five surfaces use bg-surface border border-rule rounded-lg. Same chrome → no visual ranking. Fleet Overview (fleet-level synthesis) shouldn't look identical to a Source citation (single quoted snippet).
Fix: introduce a hierarchy — e.g., Fleet Overview gets a 1px top accent in signal-blue (charged-moment-adjacent, brand-anchored), VendorCard stays as-is, Source citations drop the border and rely on indentation/divider rules. Or: vary radii (DESIGN.md scale sm/md/lg exists but everything is md).

Sparkline tooltip is the browser default
Location: Sparkline.tsx:175
<title> SVG element → OS yellow box. DESIGN.md §222 specifies a designed tooltip with auto-dismiss at 1500ms.
Fix: implement the spec'd tooltip OR mark §222 as "not in scope, defer to Stage 4" honestly in DESIGN.md.

PdfIcon and GearIcon are generic Feather-style line icons
Location: DetailPanel.tsx:302-321, SettingsGear.tsx:184-200
Both are the standard SaaS-template lineart. Spec doesn't ban them but the seismograph motif (DESIGN.md §8 in CLAUDE.md) doesn't show up anywhere in the UI's iconography.
Fix: replace PdfIcon with a "document with waveform" custom SVG (4 strokes; ties to brand), or drop the icon entirely and use just text. Same for GearIcon — many enterprise dashboards drop it for a label "Settings".

The middot · separator is doing too much work
Locations: App.tsx:133-135 inline, ActivityIndicator.tsx:21,25,29, VendorCard.tsx:87, DetailPanel.tsx:103,213
· · · · everywhere. Uniform delimiter = uniform rhythm = AI-default texture.
Fix: vary — use the middot only when joining same-rank items; use a thin vertical rule (<span class="w-px h-3 bg-rule mx-3" />) between different-rank items; use commas inside a single semantic unit.

Uniform tracking-wider on every uppercase label
Locations: throughout — every uppercase className is paired with tracking-wider.
Wide tracking everywhere = no distinction between label tiers. The wordmark gets letter-spacing: -0.02em per spec, but no in-app label uses any other tracking.
Fix: tighten high-importance section labels (tracking-wide or even tracking-normal); reserve tracking-wider for the smallest microcopy.

Card layout drifts from DESIGN.md §229 spec
Location: VendorCard.tsx:50-90
Spec: "state pill top-right, score bottom-left, sparkline bottom-right." Reality: score is in the MIDDLE row (with sparkline next to it), and convergence+signals occupies the BOTTOM row. Spec doesn't mention the footer.
Fix: either remove the footer (move convergence/signals into the meta-text under the vendor name) so score+sparkline are genuinely the bottom row, OR update DESIGN.md §229 to acknowledge the footer.

F. Hierarchy bugs at the page level
No clear single primary CTA on the dashboard surface Spec rule §145: "One primary CTA per screen." The dashboard has: every vendor card (clickable, looks identical), the gear (icon-only), the chord (hidden), and on the DetailPanel the "Export DORA evidence" button outlined in signal-blue. There's no single visual "primary action" on the dashboard view itself. The hidden chord is the actual hero action but it's invisible. Fix: either accept this (the dashboard is observational by design — no CTA needed) and document it in DESIGN.md, or expose the chord trigger as a visible button.
Recommendation for triage: items #1, #3, #7, #12, #15, #20, #21, #24 are the highest-leverage — they pattern-match Impeccable's hard rules (hero-metric template, identical chrome, glassmorphism, color-token violation, scale-token violations). Items #22, #23, #26 are spec-drift acknowledgments that may be better resolved by editing DESIGN.md than the code.

Tell me which numbered items to apply and I'll batch the fixes.