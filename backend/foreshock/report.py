"""
DORA evidence-artifact export.

One-click PDF report of a vendor's risk profile, structured to resemble
documentation a GRC team might file against DORA Article 28
(continuous-monitoring obligations for critical ICT third-party providers).

This is the strategic centerpiece: it converts the trust contract from a
demo feature into a compliance deliverable. Every claim in the report
traces to a numbered source URL — same trust contract as the dashboard
AI summary, now in a printable artifact form.

LEGAL/CREDIBILITY DISCLAIMER renders as a prominent amber callout above
the title block on page 1. Required, not optional — calling this output
"DORA-compliant" without that disclaimer would itself be a regulatory
misrepresentation.

Typography is the brand pair: General Sans (body, headers) and Sometype
Mono (data values, source URLs). TTFs are bundled under fonts/ and
registered with ReportLab on first use.

PDF engine: ReportLab (pure-Python, no system deps).
"""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .api import vendor_detail


# ---------------------------------------------------------------------------
# Font registration — General Sans + Sometype Mono (TTFs bundled in fonts/).
# Idempotent; only registers on first call per process.
# ---------------------------------------------------------------------------

_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# Logical font names used throughout the styles (post-registration).
F_BODY = "GeneralSans"
F_BODY_MEDIUM = "GeneralSans-Medium"
F_BODY_SEMI = "GeneralSans-Semibold"
F_BODY_BOLD = "GeneralSans-Bold"
F_BODY_ITALIC = "GeneralSans-Italic"
F_MONO = "SometypeMono"
F_MONO_MEDIUM = "SometypeMono-Medium"


def _register_fonts() -> None:
    if F_BODY in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(F_BODY, os.path.join(_FONT_DIR, "GeneralSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(F_BODY_MEDIUM, os.path.join(_FONT_DIR, "GeneralSans-Medium.ttf")))
    pdfmetrics.registerFont(TTFont(F_BODY_SEMI, os.path.join(_FONT_DIR, "GeneralSans-Semibold.ttf")))
    pdfmetrics.registerFont(TTFont(F_BODY_BOLD, os.path.join(_FONT_DIR, "GeneralSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont(F_BODY_ITALIC, os.path.join(_FONT_DIR, "GeneralSans-Italic.ttf")))
    pdfmetrics.registerFontFamily(
        F_BODY,
        normal=F_BODY,
        bold=F_BODY_BOLD,
        italic=F_BODY_ITALIC,
        boldItalic=F_BODY_BOLD,
    )
    pdfmetrics.registerFont(TTFont(F_MONO, os.path.join(_FONT_DIR, "SometypeMono-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(F_MONO_MEDIUM, os.path.join(_FONT_DIR, "SometypeMono-Medium.ttf")))
    pdfmetrics.registerFontFamily(
        F_MONO,
        normal=F_MONO,
        bold=F_MONO_MEDIUM,
    )


# ---------------------------------------------------------------------------
# Disclaimer text — appears in the page-1 callout (single source of truth).
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Example output — illustrative only. Not validated regulatory compliance. "
    "In production, Foreshock would work with qualified DORA compliance "
    "advisors to validate that output format and content meet current "
    "regulatory requirements."
)


# ---------------------------------------------------------------------------
# Colors. PDF stays light-mode (white background, printable artifact) but
# state colors match the dashboard so a reader bouncing between the live
# UI and the printout reads the same signal.
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
# State colors are exact dashboard hexes (DESIGN.md / tailwind.config.js)
# so the printout reads identically to the UI.
C_CRITICAL = HexColor("#FF5247")
C_WARNING = HexColor("#FFAA33")
C_STABLE = HexColor("#3FB8AF")

_STATE_COLOR = {
    "critical": C_CRITICAL,
    "warning": C_WARNING,
    "stable": C_STABLE,
}


# ---------------------------------------------------------------------------
# Paragraph styles. Section headers go Signal Blue + uppercase tracking —
# matches the dashboard's brand voice (calibrated · charged · restrained).
# ---------------------------------------------------------------------------

def _make_styles() -> dict[str, ParagraphStyle]:
    _register_fonts()
    base = getSampleStyleSheet()["Normal"]
    s: dict[str, ParagraphStyle] = {}

    s["title"] = ParagraphStyle(
        "title", parent=base, fontName=F_BODY_BOLD,
        fontSize=17, leading=21, textColor=C_INK_PRIMARY,
        spaceAfter=2,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base, fontName=F_BODY,
        fontSize=9, leading=12, textColor=C_INK_MUTED, spaceAfter=8,
    )
    s["section_h"] = ParagraphStyle(
        "section_h", parent=base, fontName=F_BODY_SEMI,
        fontSize=10, leading=12, textColor=C_BRAND,
        textTransform="uppercase", letterSpacing=1.2,
        spaceBefore=10, spaceAfter=4,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=base, fontName=F_BODY_BOLD,
        fontSize=11, leading=14, textColor=C_INK_PRIMARY,
        spaceBefore=4, spaceAfter=2,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base, fontName=F_BODY,
        fontSize=10, leading=14, textColor=C_INK_BODY, spaceAfter=4,
    )
    s["body_tight"] = ParagraphStyle(
        "body_tight", parent=s["body"], spaceAfter=1,
    )
    s["mono"] = ParagraphStyle(
        "mono", parent=base, fontName=F_MONO,
        fontSize=7.5, leading=10.5, textColor=C_INK_BODY,
    )
    s["mono_link"] = ParagraphStyle(
        "mono_link", parent=base, fontName=F_MONO,
        fontSize=7.5, leading=10.5, textColor=C_BRAND,
    )
    s["mono_data"] = ParagraphStyle(
        "mono_data", parent=base, fontName=F_MONO,
        fontSize=9, leading=12, textColor=C_INK_BODY,
    )
    s["small"] = ParagraphStyle(
        "small", parent=base, fontName=F_BODY,
        fontSize=8, leading=11, textColor=C_INK_MUTED,
    )
    s["small_italic"] = ParagraphStyle(
        "small_italic", parent=base, fontName=F_BODY_ITALIC,
        fontSize=8, leading=11, textColor=C_INK_MUTED,
    )
    s["disclaimer_box"] = ParagraphStyle(
        "disclaimer_box", parent=base, fontName=F_BODY_MEDIUM,
        fontSize=9, leading=13, textColor=C_INK_PRIMARY,
        leftIndent=4, rightIndent=4,
    )
    return s


# ---------------------------------------------------------------------------
# Per-page chrome (header rule + brand wordmark + footer rule + page number)
# ---------------------------------------------------------------------------

def _draw_chrome(canvas, doc, audit: dict | None = None):
    """
    Per-page chrome. Optional `audit` parameter renders a second
    citation-integrity footer line below the existing one — the
    Wave 6 trust badge for the DORA evidence artifact.

    Call sites wrap this in a closure that captures audit data; see
    `build_vendor_report_pdf` for the binding.
    """
    _register_fonts()
    canvas.saveState()
    width, height = doc.pagesize
    margin_x = doc.leftMargin

    # Top rule under the running brand wordmark.
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(margin_x, height - 0.5 * inch, width - margin_x, height - 0.5 * inch)

    # Running brand wordmark + subtitle in the top margin.
    canvas.setFont(F_BODY_BOLD, 8)
    canvas.setFillColor(C_BRAND)
    canvas.drawString(
        margin_x, height - 0.4 * inch,
        "FORESHOCK"
    )
    canvas.setFont(F_BODY, 8)
    canvas.setFillColor(C_INK_DIM)
    canvas.drawString(
        margin_x + 0.62 * inch, height - 0.4 * inch,
        "third-party ICT vendor risk report"
    )

    # Footer rule + page number / confidentiality line. No disclaimer body
    # in the footer — the page-1 callout is the single source.
    footer_y = 0.55 * inch
    canvas.setStrokeColor(C_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(margin_x, footer_y, width - margin_x, footer_y)

    canvas.setFont(F_BODY, 7.5)
    canvas.setFillColor(C_INK_MUTED)
    canvas.drawString(
        margin_x, footer_y - 0.18 * inch,
        "Foreshock  ·  continuous ICT vendor risk monitoring"
    )
    canvas.drawRightString(
        width - margin_x,
        footer_y - 0.18 * inch,
        f"Page {doc.page}  ·  CONFIDENTIAL  ·  example output",
    )

    # Wave 6 trust footer — a second line of Sometype Mono below the
    # standard footer. PASS verdict colored teal; FAIL colored amber
    # (shouldn't happen on a healthy run but we surface honestly).
    if audit is not None:
        cited = len(audit.get("cited") or [])
        invalid = len(audit.get("invalid") or [])
        pass_audit = bool(audit.get("all_claims_sourced", True))
        verdict = "PASS" if pass_audit else "FAIL"
        verdict_color = C_STABLE if pass_audit else C_WARNING

        audit_y = footer_y - 0.32 * inch
        canvas.setFont(F_MONO, 6.5)
        canvas.setFillColor(C_INK_MUTED)
        prefix = (
            f"Citation integrity  ·  AI-generated claims: {cited}  ·  "
            f"Unresolved citations: {invalid}  ·  Audit: "
        )
        canvas.drawString(margin_x, audit_y, prefix)
        prefix_w = canvas.stringWidth(prefix, F_MONO, 6.5)
        canvas.setFont(F_MONO_MEDIUM, 6.5)
        canvas.setFillColor(verdict_color)
        canvas.drawString(margin_x + prefix_w, audit_y, verdict)

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
        ("BOX", (0, 0), (-1, -1), 1.0, C_DISCLAIMER_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return [t, Spacer(1, 10)]


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
        Spacer(1, 2),
    ]


def _build_section_posture(detail: dict, styles: dict) -> list:
    overview = detail["overview"]
    alert = detail["alert"]
    state = overview["state"]
    state_color = _STATE_COLOR.get(state, C_INK_PRIMARY)

    score_text = (
        f'<font size=24 name="{F_BODY_BOLD}" color="{state_color.hexval()}">'
        f"{overview['score']:.1f}</font>"
        f'<font size=12 color="#9AA3B8"> / 100</font>'
    )
    state_label = (
        f'<font size=11 name="{F_BODY_BOLD}" color="{state_color.hexval()}">'
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
        Spacer(1, 6),
        _kv_table(facts),
        Spacer(1, 2),
    ]


def _build_section_components(detail: dict, styles: dict) -> list:
    overview = detail["overview"]
    components = overview["components"]
    # SINGLE SOURCE OF TRUTH for the composite score. §2 posture headline
    # displays this; §3 Total row displays this; they're guaranteed identical
    # because they're the same value. The raw sum of full-precision
    # contributions is shown as a transparency footnote so any reader can
    # verify the rounding math.
    headline_score = overview["score"]
    raw_sum = sum(c["contribution"] for c in components)

    rows = [["Component", "Score", "Weight", "Contribution", "Drivers"]]
    for c in components:
        drivers = c.get("drivers") or []
        drivers_text = "; ".join(drivers) if drivers else "—"
        drivers_p = Paragraph(drivers_text, styles["small"])
        rows.append([
            c["name"],
            Paragraph(f"{c['score']:.1f}", styles["mono_data"]),
            Paragraph(f"{c['weight']:.2f}", styles["mono_data"]),
            Paragraph(f"{c['contribution']:.2f}", styles["mono_data"]),
            drivers_p,
        ])

    rows.append([
        Paragraph("<b>Total composite</b>", styles["small"]),
        "",
        "",
        Paragraph(f"<b>{headline_score:.1f}</b>", styles["mono_data"]),
        Paragraph(
            "<i>= §2 posture score (single source of truth)</i>",
            styles["small_italic"],
        ),
    ])

    tbl = Table(
        rows,
        colWidths=[1.0 * inch, 0.6 * inch, 0.6 * inch, 0.9 * inch, 3.9 * inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), F_BODY_SEMI),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -2), F_BODY),
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
        Spacer(1, 4),
        tbl,
        Spacer(1, 2),
        Paragraph(
            f"<i>Reconciliation note. Total composite = "
            f"round(sum of full-precision contributions, 1). "
            f"Raw sum = {raw_sum:.4f}, displayed = {headline_score:.1f}. "
            f"Individual contributions are displayed at 2-decimal precision; "
            f"a column-wise sum of the displayed values may differ from the "
            f"composite by ≤ 0.1 due to per-row rounding.</i>",
            styles["small_italic"],
        ),
        Spacer(1, 2),
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
            Paragraph(
                str(s.get("latest_value") if s.get("latest_value") is not None else "—"),
                styles["mono_data"],
            ),
            Paragraph(s.get("latest_date") or "—", styles["mono_data"]),
            Paragraph(str(s.get("source_count", 0)), styles["mono_data"]),
        ])

    tbl = Table(
        rows,
        colWidths=[0.3*inch, 1.2*inch, 3.05*inch, 0.95*inch, 1.0*inch, 0.5*inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), F_BODY_SEMI),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), F_BODY),
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
        Spacer(1, 4),
        tbl,
        Spacer(1, 2),
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
        Spacer(1, 6),
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
    flow.append(Spacer(1, 4))
    pass_marker = f'<font color="{C_STABLE.hexval()}"><b>PASS</b></font>'
    fail_marker = f'<font color="{C_CRITICAL.hexval()}"><b>FAIL</b></font>'
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
        Spacer(1, 4),
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
                f'<link href="{_escape_attr(url)}" color="{C_BRAND.hexval()}">{_para_safe(url)}</link>',
                styles["mono_link"],
            )
        else:
            url_p = Paragraph(_para_safe(url) or "—", styles["mono"])
        rows.append([
            Paragraph(f"[{c.get('n')}]", styles["mono_data"]),
            c.get("metric") or "—",
            Paragraph(c.get("capture_date") or "—", styles["mono_data"]),
            Paragraph(_para_safe(c.get("snippet") or "—"), styles["small"]),
            url_p,
        ])

    tbl = Table(
        rows,
        colWidths=[0.5*inch, 1.05*inch, 0.95*inch, 2.25*inch, 2.25*inch],
        repeatRows=1,
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_INK_MUTED),
        ("FONTNAME", (0, 0), (-1, 0), F_BODY_SEMI),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), F_BODY),
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
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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
        bottomMargin=0.85 * inch,
        title=f"Foreshock vendor risk report — {vendor_name}",
        author="Foreshock",
        subject="Third-party ICT vendor risk profile",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        showBoundary=0,
    )
    # Pass the per-vendor citation audit into the page chrome so every
    # page footer can display the trust verdict. Vendors with no AI
    # summary (stable, no alert) have no audit and the footer line is
    # silently skipped.
    audit_for_footer = (detail.get("summary") or {}).get("audit")

    def chrome_with_audit(canvas, doc):
        _draw_chrome(canvas, doc, audit=audit_for_footer)

    doc.addPageTemplates([PageTemplate(
        id="all",
        frames=[frame],
        onPage=chrome_with_audit,
    )])
    doc.build(story)
    return buf.getvalue()
