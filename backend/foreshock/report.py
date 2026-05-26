"""
DORA evidence-artifact export.

One-click PDF report of a vendor's risk profile, structured to resemble
documentation a GRC team might file against DORA Article 28
(continuous-monitoring obligations for critical ICT third-party providers).

This is the strategic centerpiece: it converts the trust contract from a
demo feature into a compliance deliverable. Every claim in the report
traces to a numbered source URL — same trust contract as the dashboard
AI summary, now in a printable artifact form.

LEGAL/CREDIBILITY DISCLAIMER appears in BOTH the page-1 header callout
and as a per-page footer on every page. Required, not optional —
calling this output "DORA-compliant" without that disclaimer would
itself be a regulatory misrepresentation.

PDF engine: ReportLab (pure-Python, no system deps).
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .api import vendor_detail


# ---------------------------------------------------------------------------
# Verbatim disclaimer text — appears in header callout AND per-page footer.
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Example output — illustrative only. Not validated regulatory compliance. "
    "In production, Foreshock would work with qualified DORA compliance "
    "advisors to validate that output format and content meet current "
    "regulatory requirements."
)


# ---------------------------------------------------------------------------
# Colors (print-safe versions of the dashboard's signal-* tokens)
# ---------------------------------------------------------------------------

C_INK_PRIMARY = HexColor("#161B2B")
C_INK_BODY = HexColor("#33384a")
C_INK_MUTED = HexColor("#5A6178")
C_INK_DIM = HexColor("#9AA3B8")
C_RULE = HexColor("#D5D8E2")
C_SURFACE = HexColor("#F4F5F8")
C_DISCLAIMER_BG = HexColor("#FFF5E0")
C_DISCLAIMER_BORDER = HexColor("#FFAA33")
C_BRAND = HexColor("#3B82F6")
C_CRITICAL = HexColor("#D63F2C")
C_WARNING = HexColor("#C77A1A")
C_STABLE = HexColor("#2E8A82")

_STATE_COLOR = {
    "critical": C_CRITICAL,
    "warning": C_WARNING,
    "stable": C_STABLE,
}


# ---------------------------------------------------------------------------
# Paragraph styles (lazy-built so reportlab can register fonts first)
# ---------------------------------------------------------------------------

def _make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    s: dict[str, ParagraphStyle] = {}

    s["title"] = ParagraphStyle(
        "title", parent=base, fontName="Helvetica-Bold",
        fontSize=16, leading=20, textColor=C_INK_PRIMARY,
        spaceAfter=2,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base, fontName="Helvetica",
        fontSize=9, leading=12, textColor=C_INK_MUTED, spaceAfter=10,
    )
    s["section_h"] = ParagraphStyle(
        "section_h", parent=base, fontName="Helvetica-Bold",
        fontSize=10, leading=12, textColor=C_INK_MUTED,
        textTransform="uppercase", letterSpacing=1.2,
        spaceBefore=14, spaceAfter=6,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base, fontName="Helvetica-Bold",
        fontSize=12, leading=15, textColor=C_INK_PRIMARY,
        spaceAfter=4,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base, fontName="Helvetica",
        fontSize=10, leading=14, textColor=C_INK_BODY, spaceAfter=6,
    )
    s["body_tight"] = ParagraphStyle(
        "body_tight", parent=s["body"], spaceAfter=2,
    )
    s["mono"] = ParagraphStyle(
        "mono", parent=base, fontName="Courier",
        fontSize=8, leading=11, textColor=C_INK_BODY,
    )
    s["mono_link"] = ParagraphStyle(
        "mono_link", parent=base, fontName="Courier",
        fontSize=8, leading=11, textColor=C_BRAND,
    )
    s["small"] = ParagraphStyle(
        "small", parent=base, fontName="Helvetica",
        fontSize=8, leading=11, textColor=C_INK_MUTED,
    )
    s["small_italic"] = ParagraphStyle(
        "small_italic", parent=base, fontName="Helvetica-Oblique",
        fontSize=8, leading=11, textColor=C_INK_MUTED,
    )
    s["disclaimer_box"] = ParagraphStyle(
        "disclaimer_box", parent=base, fontName="Helvetica-Bold",
        fontSize=9, leading=13, textColor=C_INK_PRIMARY,
        leftIndent=8, rightIndent=8, spaceBefore=8, spaceAfter=8,
    )
    s["footer"] = ParagraphStyle(
        "footer", parent=base, fontName="Helvetica-Oblique",
        fontSize=6.5, leading=8.5, textColor=C_INK_MUTED,
    )
    return s


# ---------------------------------------------------------------------------
# Per-page chrome (header rule + footer disclaimer + pagination)
# ---------------------------------------------------------------------------

def _draw_chrome(canvas, doc):
    canvas.saveState()
    width, height = doc.pagesize
    margin_x = doc.leftMargin

    # Top rule under the running brand wordmark (very subtle)
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(margin_x, height - 0.5 * inch, width - margin_x, height - 0.5 * inch)

    # Running brand wordmark in the top margin (so even pages without the
    # title block still show "Foreshock · DORA evidence report")
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(C_INK_MUTED)
    canvas.drawString(
        margin_x, height - 0.4 * inch,
        "FORESHOCK"
    )
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(C_INK_DIM)
    canvas.drawString(
        margin_x + 0.65 * inch, height - 0.4 * inch,
        "third-party ICT vendor risk report"
    )

    # Footer rule
    footer_top = 0.75 * inch
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(margin_x, footer_top, width - margin_x, footer_top)

    # Per-page disclaimer (full text, wrapped via Paragraph flow)
    styles = _make_styles()
    p = Paragraph(f"<b>Disclaimer.</b> {DISCLAIMER}", styles["footer"])
    avail_w = width - 2 * margin_x
    w, h = p.wrap(avail_w, 0.5 * inch)
    p.drawOn(canvas, margin_x, footer_top - 0.05 * inch - h)

    # Page number + confidentiality marker (right side, above rule)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(C_INK_MUTED)
    canvas.drawRightString(
        width - margin_x,
        footer_top + 0.07 * inch,
        f"Page {doc.page}  ·  CONFIDENTIAL  ·  example output",
    )

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Section builders — each returns a list of flowables
# ---------------------------------------------------------------------------

def _build_title_block(detail: dict, styles: dict, gen_ts: str) -> list:
    overview = detail["overview"]
    name = overview["name"]
    vtype = overview["type"]
    is_demo = overview.get("is_demo", False)

    title = f"{name} <font size=10 color='#9AA3B8'>· {vtype}</font>"
    if is_demo:
        title += (
            "  <font size=8 color='#9AA3B8'>"
            "[DEMO VENDOR — fictional, for illustration]</font>"
        )

    return [
        Paragraph(title, styles["title"]),
        Paragraph(
            f"Third-party ICT vendor risk profile  ·  generated {gen_ts}",
            styles["subtitle"],
        ),
    ]


def _build_disclaimer_callout(styles: dict) -> list:
    body = (
        f"<font color='#C77A1A'><b>EXAMPLE OUTPUT — ILLUSTRATIVE ONLY.</b></font> "
        f"{DISCLAIMER[len('Example output — illustrative only. '):]}"
    )
    cell = [[Paragraph(body, styles["disclaimer_box"])]]
    t = Table(cell, colWidths=[7.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_DISCLAIMER_BG),
        ("BOX", (0, 0), (-1, -1), 1.2, C_DISCLAIMER_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [t, Spacer(1, 12)]


def _build_section_identification(detail: dict, styles: dict, gen_ts: str) -> list:
    overview = detail["overview"]
    traj = overview.get("trajectory") or []
    window_start = traj[0]["date"] if traj else "—"
    window_end = traj[-1]["date"] if traj else "—"

    rows = [
        ["Vendor",                overview["name"]],
        ["Vendor type",           overview["type"]],
        ["Report generated",      gen_ts],
        ["Monitoring window",     f"{window_start} → {window_end}"],
        ["Signal observations",   f"{overview['signal_count']} captured rows"],
        ["Latest capture",        overview.get("latest_capture") or "—"],
        ["Capture cadence",       "continuous (daily background + on-demand pull)"],
    ]
    return [
        Paragraph("1 · Vendor identification", styles["section_h"]),
        _kv_table(rows),
        Spacer(1, 4),
    ]


def _build_section_posture(detail: dict, styles: dict) -> list:
    overview = detail["overview"]
    alert = detail["alert"]
    state = overview["state"]
    state_color = _STATE_COLOR.get(state, C_INK_PRIMARY)

    score_text = (
        f'<font size=22 name="Helvetica-Bold" color="{state_color.hexval()}">'
        f"{overview['score']:.1f}</font>"
        f'<font size=12 color="#9AA3B8"> / 100</font>'
    )
    state_label = (
        f'<font size=11 name="Helvetica-Bold" color="{state_color.hexval()}">'
        f"{state.upper()}</font>"
    )
    band_info = (
        '<font size=8 color="#5A6178">'
        "Bands: stable &lt;30  ·  warning 30–60  ·  critical ≥60"
        "</font>"
    )

    posture_inner = [[
        Paragraph(f"{state_label}<br/>{score_text}<br/>{band_info}",
                  styles["body_tight"]),
    ]]
    posture_tbl = Table(posture_inner, colWidths=[7.0 * inch])
    posture_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.5, C_RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    facts = [
        ["Convergence count",  f"{overview['convergence_count']} dimension(s) deteriorating"],
        ["Alert status",       (
            f"{alert['alert_type'] or '—'} alert fired"
            if alert["fired"] else "no alert (vendor in stable band)"
        )],
    ]
    if alert["fired"] and alert.get("fired_at"):
        facts.append(["Alert fired at", alert["fired_at"]])
    if alert["fired"] and alert.get("headline"):
        facts.append(["Alert headline", alert["headline"]])

    return [
        Paragraph("2 · Current risk posture", styles["section_h"]),
        posture_tbl,
        Spacer(1, 8),
        _kv_table(facts),
        Spacer(1, 4),
    ]


def _build_section_components(detail: dict, styles: dict) -> list:
    overview = detail["overview"]
    components = overview["components"]

    rows = [["Component", "Score", "Weight", "Contribution", "Drivers"]]
    for c in components:
        drivers = c.get("drivers") or []
        drivers_text = "; ".join(drivers) if drivers else "—"
        # Paragraph wrap on drivers cell so long driver text wraps cleanly.
        drivers_p = Paragraph(drivers_text, styles["small"])
        rows.append([
            c["name"],
            f"{c['score']:.1f}",
            f"{c['weight']:.2f}",
            f"{c['contribution']:.2f}",
            drivers_p,
        ])

    total = sum(c["contribution"] for c in components)
    rows.append([
        Paragraph("<b>Total</b>", styles["small"]),
        "",
        "",
        Paragraph(f"<b>{total:.2f}</b>", styles["small"]),
        "",
    ])

    tbl = Table(
        rows,
        colWidths=[1.0 * inch, 0.6 * inch, 0.6 * inch, 0.9 * inch, 3.9 * inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -2), 9),
        ("TEXTCOLOR", (0, 1), (-1, -2), C_INK_BODY),
        ("ALIGN", (1, 1), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_RULE),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, C_RULE),
        ("BACKGROUND", (0, -1), (-1, -1), C_SURFACE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return [
        Paragraph("3 · Score component breakdown", styles["section_h"]),
        Paragraph(
            "Each dimension scores 0–100 against its measurement rubric; "
            "weighted contributions sum to the composite. Leadership "
            "stability and legal events are weighted highest as sharpest "
            "failure signals.",
            styles["small"],
        ),
        Spacer(1, 6),
        tbl,
        Spacer(1, 4),
    ]


def _build_section_convergence(detail: dict, styles: dict) -> list:
    alert = detail["alert"]
    signals = alert.get("signals") or []

    if not signals:
        return [
            Paragraph("4 · Converging signals", styles["section_h"]),
            Paragraph(
                "<i>No converging deteriorating signals at this monitoring "
                "interval. Vendor is currently in the stable band.</i>",
                styles["body"],
            ),
        ]

    rows = [["#", "Metric", "Summary", "Latest", "Date", "Sources"]]
    for i, s in enumerate(signals, 1):
        rows.append([
            str(i),
            s.get("metric") or "—",
            Paragraph(s.get("summary") or "—", styles["small"]),
            str(s.get("latest_value") if s.get("latest_value") is not None else "—"),
            s.get("latest_date") or "—",
            str(s.get("source_count", 0)),
        ])

    tbl = Table(
        rows,
        colWidths=[0.3*inch, 1.2*inch, 3.3*inch, 0.9*inch, 0.8*inch, 0.5*inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_INK_BODY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    return [
        Paragraph("4 · Converging signals", styles["section_h"]),
        Paragraph(
            f"<b>{len(signals)} dimension(s) deteriorating concurrently.</b> "
            "The convergence pattern is the hero risk signal — independent "
            "dimensions moving together is far rarer than any single-metric "
            "trip, and far more diagnostic of material vendor stress.",
            styles["small"],
        ),
        Spacer(1, 6),
        tbl,
        Spacer(1, 4),
    ]


def _build_section_narrative(detail: dict, styles: dict) -> list:
    summary = detail.get("summary")
    if not summary:
        return [
            Paragraph("5 · AI risk narrative", styles["section_h"]),
            Paragraph(
                "<i>No active alert; AI risk narrative not generated. "
                "Vendor is in the stable band — routine monitoring "
                "continues; no narrative is produced unless / until a "
                "convergence or single-metric alert fires.</i>",
                styles["body"],
            ),
        ]

    flow: list = [
        Paragraph("5 · AI risk narrative", styles["section_h"]),
        Paragraph(
            f"Narrative generated by AI from the scored diff payload "
            f"({summary.get('generated_by') or 'AI'}). Every factual claim "
            "carries a numbered [N] citation that resolves to the source "
            "table in §6. An automated trust-contract audit verifies that "
            "no citation is fabricated.",
            styles["small"],
        ),
        Spacer(1, 8),
        Paragraph("Headline", styles["h2"]),
        Paragraph(_para_safe(summary.get("headline") or ""), styles["body"]),
        Paragraph("Sentiment read", styles["h2"]),
        Paragraph(_para_safe(summary.get("sentiment_read") or ""), styles["body"]),
        Paragraph("Narrative", styles["h2"]),
    ]
    narrative_text = summary.get("narrative") or ""
    for para in narrative_text.split("\n\n"):
        if para.strip():
            flow.append(Paragraph(_para_safe(para), styles["body"]))
    flow.append(Paragraph("Recommended action", styles["h2"]))
    flow.append(Paragraph(
        _para_safe(summary.get("recommended_action") or ""),
        styles["body"],
    ))

    audit = summary.get("audit") or {}
    flow.append(Spacer(1, 6))
    pass_marker = '<font color="#2E8A82"><b>PASS</b></font>'
    fail_marker = '<font color="#D63F2C"><b>FAIL</b></font>'
    audit_verdict = pass_marker if audit.get("all_claims_sourced") else fail_marker
    audit_text = (
        f"<b>Trust-contract audit.</b> "
        f"{len(audit.get('cited', []))} citation index(es) used in narrative; "
        f"{len(audit.get('available', []))} sources available; "
        f"{len(audit.get('invalid', []))} unresolved citation(s); "
        f"all_claims_sourced = {audit_verdict}"
    )
    flow.append(Paragraph(audit_text, styles["small"]))

    return flow


def _build_section_sources(detail: dict, styles: dict) -> list:
    summary = detail.get("summary")
    citations = (summary or {}).get("citations") or []

    flow: list = [
        Paragraph("6 · Source citations", styles["section_h"]),
        Paragraph(
            f"The {len(citations)} numbered source(s) below underpin every "
            "factual claim in §5. Each entry shows the metric of origin, the "
            "capture date, a short evidence snippet, and the URL. Sources "
            "tagged DEMO-SCENARIO are stubbed for the fictional Veridian "
            "Pay vendor and have no public URL.",
            styles["small"],
        ),
        Spacer(1, 6),
    ]
    if not citations:
        flow.append(Paragraph(
            "<i>No citations — no AI narrative was produced for this vendor.</i>",
            styles["body"],
        ))
        return flow

    rows = [["[#]", "Metric", "Date", "Snippet", "Source URL"]]
    for c in citations:
        url = c.get("source_url") or ""
        if url.startswith("http"):
            url_p = Paragraph(
                f'<link href="{_escape_attr(url)}" color="#3B82F6">{_para_safe(url)}</link>',
                styles["mono_link"],
            )
        else:
            url_p = Paragraph(_para_safe(url) or "—", styles["mono"])
        rows.append([
            f"[{c.get('n')}]",
            c.get("metric") or "—",
            c.get("capture_date") or "—",
            Paragraph(_para_safe(c.get("snippet") or "—"), styles["small"]),
            url_p,
        ])

    tbl = Table(
        rows,
        colWidths=[0.45*inch, 1.05*inch, 0.7*inch, 2.4*inch, 2.4*inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_INK_BODY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, C_RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(tbl)
    return flow


def _build_methodology(styles: dict) -> list:
    return [
        PageBreak(),
        Paragraph("Appendix · Methodology", styles["section_h"]),
        Paragraph(
            "<b>Scoring model.</b> Each signal dimension is scored 0–100 "
            "against a metric-specific rubric (event counts, percentage "
            "trajectories, sentiment averages) and weighted into a composite "
            "0–100 score. Weights as of this report: leadership 0.30, "
            "legal 0.25, headcount 0.17, sentiment 0.15, news volume 0.07, "
            "open roles 0.06. State bands: stable &lt;30, warning 30–60, "
            "critical ≥60. The convergence count tallies independent "
            "dimensions whose latest observation deteriorates against the "
            "monitoring window.",
            styles["body"],
        ),
        Paragraph(
            "<b>Continuous capture.</b> Signal rows are appended (Type 2 SCD) "
            "to an immutable log; historical observations are never overwritten. "
            "Captures come from a daily background sweep of public web sources "
            "via Bright Data MCP (search_engine, recency-filtered, "
            "per-vendor disambiguated queries) plus an on-demand pull "
            "available to the operator.",
            styles["body"],
        ),
        Paragraph(
            "<b>Event validation chain.</b> Heuristic keyword detectors "
            "produce candidate leadership_change and legal_event rows. Each "
            "candidate is then validated by an AI pass which checks "
            "whether the title and description genuinely describe an event "
            "at the named vendor (not a similarly-named entity, a share "
            "sale, a pay disclosure, or an opinion piece). Rejected "
            "candidates are not written to the schema.",
            styles["body"],
        ),
        Paragraph(
            "<b>Trust contract.</b> The §5 narrative is generated by AI "
            "from a structured scored-diff payload — never from raw signal "
            "rows. Every factual claim carries a numbered [N] citation that "
            "resolves to an entry in §6. An automated audit verifies that "
            "no citation is fabricated. Sources tagged DEMO-SCENARIO are "
            "stubbed signals on the fictional Veridian Pay vendor used to "
            "illustrate the full alert cascade without inventing a crisis "
            "for a real company.",
            styles["body"],
        ),
        Paragraph(
            "<b>Limitations.</b> Foreshock observes public-web signals only; "
            "it does not access vendor-internal data, contracts, or "
            "regulatory filings. Output is intended to AUGMENT a GRC team's "
            "third-party register, not replace human judgment, vendor "
            "outreach, or qualified legal review. See the disclaimer above.",
            styles["body"],
        ),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kv_table(rows: list[list[str]]) -> Table:
    styles = _make_styles()
    typed: list[list[Any]] = []
    for label, value in rows:
        typed.append([
            Paragraph(_para_safe(label), styles["small"]),
            Paragraph(_para_safe(value), styles["body_tight"]),
        ])
    tbl = Table(typed, colWidths=[1.6 * inch, 5.4 * inch])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, C_RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _para_safe(text: str) -> str:
    """Escape XML-special characters for ReportLab Paragraph mini-HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_attr(text: str) -> str:
    return _para_safe(text).replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_vendor_report_pdf(vendor_name: str) -> bytes:
    """Generate the DORA-evidence-style PDF for one vendor. Returns bytes."""
    detail = vendor_detail(vendor_name)
    if "error" in detail:
        raise ValueError(detail["error"])

    styles = _make_styles()
    gen_ts = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    story: list = []
    story.extend(_build_disclaimer_callout(styles))
    story.extend(_build_title_block(detail, styles, gen_ts))
    story.extend(_build_section_identification(detail, styles, gen_ts))
    story.extend(_build_section_posture(detail, styles))
    story.extend(_build_section_components(detail, styles))
    story.extend(_build_section_convergence(detail, styles))
    story.extend(_build_section_narrative(detail, styles))
    story.extend(_build_section_sources(detail, styles))
    story.extend(_build_methodology(styles))

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=1.05 * inch,
        title=f"Foreshock vendor risk report — {vendor_name}",
        author="Foreshock",
        subject="Third-party ICT vendor risk profile",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        showBoundary=0,
    )
    doc.addPageTemplates([PageTemplate(
        id="all",
        frames=[frame],
        onPage=_draw_chrome,
    )])
    doc.build(story)
    return buf.getvalue()
