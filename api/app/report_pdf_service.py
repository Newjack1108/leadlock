"""
Service for generating PDF documents for sales reports.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from typing import Any, Dict, List, Optional
from io import BytesIO
from datetime import datetime
from decimal import Decimal


def format_currency(amount: Any, currency: str = "GBP") -> str:
    """Format decimal/float amount as currency string."""
    if isinstance(amount, Decimal):
        val = float(amount)
    else:
        val = float(amount or 0)
    if currency == "GBP":
        return f"£{val:,.2f}"
    return f"{currency} {val:,.2f}"


def _build_report_header(company_name: str, title: str) -> List:
    """Build header flowables for a report (company name, title, date)."""
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = ParagraphStyle(
        name="ReportHeading",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=12,
    )
    flowables = []
    if company_name:
        flowables.append(Paragraph(f"<b>{company_name}</b>", normal))
        flowables.append(Spacer(1, 6))
    flowables.append(Paragraph(title, heading))
    flowables.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", normal))
    flowables.append(Spacer(1, 12))
    return flowables


def _table_style() -> TableStyle:
    """Standard table style for report tables."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ])


def generate_pipeline_value_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Pipeline Value Report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    flowables = _build_report_header(company_name, "Pipeline Value Report")

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"Period: {period}", doc.styles["Normal"]))
    flowables.append(Spacer(1, 12))

    stages = data.get("stages", [])
    table_data = [["Stage", "Count", "Total Value", "Weighted Value"]]
    for s in stages:
        table_data.append([
            s.get("stage", ""),
            str(s.get("count", 0)),
            format_currency(s.get("total_value", 0)),
            format_currency(s.get("weighted_value", 0)),
        ])

    if table_data:
        t = Table(table_data, colWidths=[80, 50, 70, 80])
        t.setStyle(_table_style())
        flowables.append(t)

    flowables.append(Spacer(1, 12))
    flowables.append(Paragraph(
        f"<b>Total Value:</b> {format_currency(data.get('total_value', 0))} | "
        f"<b>Total Weighted:</b> {format_currency(data.get('total_weighted_value', 0))}",
        doc.styles["Normal"]
    ))

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_source_performance_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Source Performance Report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    flowables = _build_report_header(company_name, "Source Performance Report")

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"Period: {period} | Total Leads: {data.get('total_leads', 0)}", doc.styles["Normal"]))
    flowables.append(Spacer(1, 12))

    sources = data.get("sources", [])
    table_data = [["Source", "Leads", "Quoted", "Won", "Conversion %"]]
    for s in sources:
        table_data.append([
            s.get("source", "").replace("_", " "),
            str(s.get("leads_count", 0)),
            str(s.get("quoted_count", 0)),
            str(s.get("won_count", 0)),
            f"{s.get('conversion_rate', 0):.1f}%",
        ])

    if table_data:
        t = Table(table_data, colWidths=[80, 50, 50, 50, 60])
        t.setStyle(_table_style())
        flowables.append(t)

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_closer_performance_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Closer Performance Report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    flowables = _build_report_header(company_name, "Closer Performance Report")

    closers = data.get("closers", [])
    table_data = [["Closer", "Leads Assigned", "Won", "Total Revenue"]]
    for c in closers:
        table_data.append([
            c.get("full_name", ""),
            str(c.get("leads_assigned", 0)),
            str(c.get("won_count", 0)),
            format_currency(c.get("total_revenue", 0)),
        ])

    if table_data:
        t = Table(table_data, colWidths=[100, 70, 50, 80])
        t.setStyle(_table_style())
        flowables.append(t)
    else:
        flowables.append(Paragraph("No closer data available.", doc.styles["Normal"]))

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_quote_engagement_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Quote Engagement Report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    flowables = _build_report_header(company_name, "Quote Engagement Report")

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"Period: {period}", doc.styles["Normal"]))
    flowables.append(Spacer(1, 12))

    table_data = [
        ["Metric", "Count"],
        ["Sent", str(data.get("sent_count", 0))],
        ["Viewed", str(data.get("viewed_count", 0))],
        ["Not Opened", str(data.get("not_opened_count", 0))],
        ["Viewed (No Reply)", str(data.get("viewed_no_reply_count", 0))],
        ["Accepted", str(data.get("accepted_count", 0))],
        ["Rejected", str(data.get("rejected_count", 0))],
    ]

    t = Table(table_data, colWidths=[150, 80])
    t.setStyle(_table_style())
    flowables.append(t)

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_weekly_summary_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Weekly Pipeline Summary Report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    flowables = _build_report_header(company_name, "Weekly Pipeline Summary")

    flowables.append(Paragraph(f"Week: {data.get('week_label', '')}", doc.styles["Normal"]))
    flowables.append(Spacer(1, 12))

    table_data = [
        ["Metric", "Count"],
        ["New Leads", str(data.get("new_count", 0))],
        ["Quoted", str(data.get("quoted_count", 0))],
        ["Won", str(data.get("won_count", 0))],
        ["Lost", str(data.get("lost_count", 0))],
    ]

    t = Table(table_data, colWidths=[150, 80])
    t.setStyle(_table_style())
    flowables.append(t)

    doc.build(flowables)
    buffer.seek(0)
    return buffer
