"""PDF report generation for crop-health cases.

Builds a self-contained PDF from the same structured data the JSON report
endpoint returns, so the on-screen report and the downloadable file can never
disagree. The document is deliberately conservative: it states the AI findings
as preliminary, names the agronomist who confirmed them, and prints the
treatment cost breakdown line by line.

Images are embedded only when the artwork file exists, so report generation
never fails because a decorative asset is missing.
"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[3]
IMAGES_DIR = ROOT / "frontend" / "assets" / "images"

GREEN = colors.HexColor("#1f6f43")
GREEN_LIGHT = colors.HexColor("#e6f2ea")
INK = colors.HexColor("#1c2620")
MUTED = colors.HexColor("#5b6b62")
AMBER = colors.HexColor("#b5761a")
RED = colors.HexColor("#a8322c")

SEV_COLOR = {"low": GREEN, "medium": AMBER, "high": RED, "unknown": MUTED}


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=20, leading=24,
                                textColor=INK, alignment=TA_LEFT, spaceAfter=2),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=9.5, leading=13,
                                   textColor=MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, leading=16,
                             textColor=GREEN, spaceBefore=12, spaceAfter=5),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13.5,
                               textColor=INK),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=8.2, leading=11,
                                textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.6, leading=11.5,
                               textColor=INK),
        "cellr": ParagraphStyle("cr", parent=base["Normal"], fontSize=8.6, leading=11.5,
                                textColor=INK, alignment=2),
    }


def _kv_table(rows: list[tuple[str, str]], styles: dict, width: float = 170 * mm) -> Table:
    data = [[Paragraph(f"<b>{k}</b>", styles["cell"]), Paragraph(v or "—", styles["cell"])]
            for k, v in rows]
    table = Table(data, colWidths=[45 * mm, width - 45 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e2e8e4")),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
    ]))
    return table


def _esc(text) -> str:
    return (str(text) if text is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _money(value) -> str:
    try:
        return f"INR {float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def build_case_pdf(report: dict) -> bytes:
    """Render a case report dict to PDF bytes.

    The input is exactly the payload of ``GET /api/cases/{id}/report`` so the
    two representations stay in lockstep.
    """
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"AgroSphere report {report.get('report_id', '')}",
        author="AgroSphere", subject="Crop-health case report",
    )
    story: list = []

    # ---- masthead -------------------------------------------------------- #
    logo = IMAGES_DIR / "logo_mark.jpg"
    header_cells = []
    if logo.exists():
        header_cells.append(Image(str(logo), width=16 * mm, height=16 * mm))
    header_cells.append(Paragraph(
        "AgroSphere<br/><font size=9 color='#5b6b62'>Crop-health case report</font>",
        styles["title"]))
    head = Table([header_cells], colWidths=[20 * mm, 150 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (1, 0), (1, 0), 6)]))
    story.append(head)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Report <b>{_esc(report.get('report_id'))}</b> &nbsp;&middot;&nbsp; "
        f"generated {_esc((report.get('generated_at') or '')[:19].replace('T', ' '))} UTC",
        styles["subtitle"]))
    story.append(Paragraph(
        "This document contains preliminary machine-assisted findings reviewed under "
        "AgroSphere's crop-health workflow. It is not a substitute for a licensed "
        "agronomist's on-site inspection.", styles["small"]))
    story.append(Spacer(1, 6))

    case = report.get("case") or {}
    farm = report.get("farm") or {}
    field = report.get("field") or {}
    farmer = report.get("farmer") or {}

    # ---- summary --------------------------------------------------------- #
    story.append(Paragraph("Case summary", styles["h2"]))
    story.append(_kv_table([
        ("Farmer", _esc(farmer.get("name"))),
        ("Farm", f"{_esc(farm.get('name'))} — {_esc(farm.get('district'))}, {_esc(farm.get('state'))}"),
        ("Field", f"{_esc(field.get('name'))} ({_esc(field.get('crop'))}"
                  + (f", {_esc(field.get('variety'))}" if field.get("variety") else "") + ")"),
        ("Acres", str(field.get("computed_acres") or field.get("acreage") or "—")),
        ("Case title", _esc(case.get("title"))),
        ("Workflow state", _esc((case.get("state") or "").replace("_", " ").title())),
        ("Severity", _esc(case.get("severity"))),
        ("Observations", _esc(case.get("observations"))),
    ], styles))
    story.append(Spacer(1, 6))

    # ---- AI analysis ----------------------------------------------------- #
    analyses = case.get("analyses") or []
    story.append(Paragraph("AI-assisted analysis (preliminary)", styles["h2"]))
    if not analyses:
        story.append(Paragraph("No analysis has been run for this case yet.", styles["body"]))
    for a in analyses[:2]:
        story.append(Paragraph(
            f"Model <b>{_esc(a.get('model_version'))}</b> &nbsp;&middot;&nbsp; "
            f"uncertainty {float(a.get('uncertainty') or 0):.0%} &nbsp;&middot;&nbsp; "
            f"latency {a.get('latency_ms') or 0} ms &nbsp;&middot;&nbsp; "
            + (f"affected area {a.get('affected_area_pct')}%" if a.get("affected_area_pct") is not None
               else "affected area not estimated"),
            styles["small"]))
        story.append(Spacer(1, 3))
        if a.get("summary"):
            story.append(Paragraph(_esc(a["summary"]), styles["body"]))
            story.append(Spacer(1, 4))
        rows = [[Paragraph("<b>Finding</b>", styles["cell"]),
                 Paragraph("<b>Confidence</b>", styles["cellr"]),
                 Paragraph("<b>Severity</b>", styles["cell"]),
                 Paragraph("<b>Evidence / alternative</b>", styles["cell"])]]
        for f in a.get("findings") or []:
            sev = (f.get("severity") or "unknown").lower()
            rows.append([
                Paragraph(_esc(f.get("label")), styles["cell"]),
                Paragraph(f"{float(f.get('confidence') or 0):.0%}", styles["cellr"]),
                Paragraph(f"<font color='{SEV_COLOR.get(sev, MUTED).hexval()}'>{_esc(sev)}</font>", styles["cell"]),
                Paragraph(_esc(f.get("evidence")) + (f"<br/><font color='#5b6b62'>Alt: {_esc(f.get('alternative'))}</font>"
                                                     if f.get("alternative") else ""), styles["cell"]),
            ])
        table = Table(rows, colWidths=[52 * mm, 20 * mm, 20 * mm, 78 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e2db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    story.append(Spacer(1, 6))

    # ---- treatment plan -------------------------------------------------- #
    plan = case.get("plan")
    story.append(Paragraph("Treatment plan", styles["h2"]))
    if not plan:
        story.append(Paragraph("No treatment plan has been recorded for this case.", styles["body"]))
    else:
        story.append(_kv_table([
            ("Problem", _esc(plan.get("problem"))),
            ("Confidence", f"{float(plan.get('confidence') or 0):.0%}"),
            ("Status", _esc((plan.get("status") or "").replace("_", " ").title())),
            ("Product", _esc(plan.get("product"))),
            ("Active ingredient", _esc(plan.get("active_ingredient"))),
            ("Dosage", _esc(plan.get("dosage"))),
            ("Application", _esc(plan.get("application"))),
            ("Weather restrictions", _esc(plan.get("weather_restrictions"))),
            ("PPE", _esc(plan.get("ppe"))),
            ("Pre-harvest interval", _esc(plan.get("pre_harvest_interval"))),
            ("Re-entry interval", _esc(plan.get("re_entry_interval"))),
            ("Follow-up", _esc(plan.get("follow_up"))),
        ], styles))
        measures = plan.get("measures") or []
        if measures:
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>Measures</b>", styles["cell"]))
            for m in measures:
                story.append(Paragraph(f"&bull; {_esc(m)}", styles["body"]))
    story.append(Spacer(1, 6))

    # ---- costing --------------------------------------------------------- #
    costs = case.get("cost")
    story.append(Paragraph("Cost estimate", styles["h2"]))
    if not costs:
        story.append(Paragraph("No cost estimate has been prepared for this case.", styles["body"]))
    else:
        rows = [[Paragraph("<b>Item</b>", styles["cell"]), Paragraph("<b>Qty</b>", styles["cellr"]),
                 Paragraph("<b>Unit</b>", styles["cell"]), Paragraph("<b>Rate</b>", styles["cellr"]),
                 Paragraph("<b>Amount</b>", styles["cellr"])]]
        for line in costs.get("lines") or []:
            rows.append([
                Paragraph(_esc(line.get("label")), styles["cell"]),
                Paragraph(str(line.get("qty", "")), styles["cellr"]),
                Paragraph(_esc(line.get("unit")), styles["cell"]),
                Paragraph(_money(line.get("rate")), styles["cellr"]),
                Paragraph(_money(line.get("amount")), styles["cellr"]),
            ])
        rows.append([Paragraph("<b>Subtotal</b>", styles["cell"]), "", "",
                     "", Paragraph(f"<b>{_money(costs.get('subtotal'))}</b>", styles["cellr"])])
        rows.append([Paragraph(f"Tax {costs.get('tax_pct')}%", styles["cell"]), "", "",
                     "", Paragraph(_money(round((costs.get('subtotal') or 0) * (costs.get('tax_pct') or 0) / 100, 2)), styles["cellr"])])
        if costs.get("discount"):
            rows.append([Paragraph("Discount", styles["cell"]), "", "", "",
                         Paragraph(f"-{_money(costs.get('discount'))}", styles["cellr"])])
        rows.append([Paragraph("<b>Total</b>", styles["cell"]), "", "",
                     "", Paragraph(f"<b>{_money(costs.get('total'))}</b>", styles["cellr"])])
        if costs.get("actual_total") is not None:
            rows.append([Paragraph("Actual spend", styles["cell"]), "", "", "",
                         Paragraph(_money(costs.get("actual_total")), styles["cellr"])])
        table = Table(rows, colWidths=[78 * mm, 16 * mm, 20 * mm, 28 * mm, 28 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN_LIGHT),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e2db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f3f8f4")),
        ]))
        story.append(table)
        if costs.get("notes"):
            story.append(Spacer(1, 3))
            story.append(Paragraph(f"<b>Notes:</b> {_esc(costs.get('notes'))}", styles["small"]))
    story.append(Spacer(1, 6))

    # ---- sources & disclaimer ------------------------------------------- #
    sources = report.get("sources") or []
    if sources:
        story.append(Paragraph("Verified sources", styles["h2"]))
        for s in sources:
            story.append(Paragraph(
                f"&bull; <b>{_esc(s.get('title'))}</b> — {_esc(s.get('organization'))} "
                f"({_esc(s.get('published'))})", styles["small"]))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Disclaimer", styles["h2"]))
    story.append(Paragraph(_esc(report.get("disclaimer")), styles["small"]))

    doc.build(story)
    return buf.getvalue()


def _now_stamp() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%d-%H%M")
