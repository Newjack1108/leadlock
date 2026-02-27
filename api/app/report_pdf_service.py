"""
Service for generating PDF documents for sales reports.
Includes company logo, green theme, and charts.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.legends import Legend
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import urllib.request

# Green theme colors
PRIMARY_GREEN = colors.HexColor("#16a34a")  # Green-600
LIGHT_GREEN = colors.HexColor("#dcfce7")    # Green-100
DARK_GREEN = colors.HexColor("#166534")     # Green-800
ACCENT_GREEN = colors.HexColor("#22c55e")   # Green-500

# Chart color palette (greens and complementary)
CHART_COLORS = [
    colors.HexColor("#16a34a"),  # Green-600
    colors.HexColor("#22c55e"),  # Green-500
    colors.HexColor("#4ade80"),  # Green-400
    colors.HexColor("#86efac"),  # Green-300
    colors.HexColor("#bbf7d0"),  # Green-200
    colors.HexColor("#14532d"),  # Green-900
    colors.HexColor("#15803d"),  # Green-700
]


def format_currency(amount: Any, currency: str = "GBP") -> str:
    """Format decimal/float amount as currency string."""
    if isinstance(amount, Decimal):
        val = float(amount)
    else:
        val = float(amount or 0)
    if currency == "GBP":
        return f"£{val:,.2f}"
    return f"{currency} {val:,.2f}"


def _resolve_logo() -> Tuple[Optional[str], Optional[bytes]]:
    """Resolve logo from static files or frontend URL."""
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    # 1. Try local static files
    base_dirs = [
        Path(__file__).parent.parent / "static",
        Path("static"),
        Path(__file__).parent.parent.parent / "web" / "public",
    ]
    for fn in ["logo1.jpg", "logo1.png", "logo.png"]:
        for base in base_dirs:
            p = base / fn
            if p.exists():
                try:
                    with open(p, "rb") as f:
                        data = f.read()
                    if data and len(data) >= 50 and (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)):
                        return (None, data)
                except Exception:
                    pass

    # 2. Try frontend URL
    DEFAULT_LOGO_BASE = "https://leadlock-frontend-production.up.railway.app"
    env_frontend_url = (
        os.getenv("FRONTEND_BASE_URL")
        or os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_FRONTEND_URL")
        or DEFAULT_LOGO_BASE
    ).strip()

    for fn in ["logo1.jpg", "logo1.png", "logo.png"]:
        for base_url in [env_frontend_url, DEFAULT_LOGO_BASE]:
            try:
                url = f"{base_url.rstrip('/')}/{fn}"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "LeadLock-API/1.0 (Report PDF)"},
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                if data and len(data) >= 50 and (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)):
                    return (None, data)
            except Exception:
                continue

    return (None, None)


def _image_from_bytes(data: bytes, width: float, max_height: float = 20 * mm) -> Optional[Any]:
    """Create ReportLab Image from bytes."""
    try:
        if not data or len(data) < 10:
            return None
        from PIL import Image as PILImage
        pil_img = PILImage.open(BytesIO(data))
        iw, ih = pil_img.size
        pil_img.close()
        if ih <= 0:
            ih = 1
        ratio = iw / ih
        out_h = width / ratio
        if out_h > max_height:
            out_h = max_height
            out_w = max_height * ratio
        else:
            out_w = width
        ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(data)
            f.flush()
            path = f.name
        return Image(path, width=out_w, height=out_h)
    except Exception:
        return None


def _build_report_header(company_name: str, title: str, logo_bytes: Optional[bytes] = None) -> List:
    """Build header flowables with logo, company name, title, and date."""
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = ParagraphStyle(
        name="ReportHeading",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=DARK_GREEN,
        spaceAfter=6,
    )
    subheading = ParagraphStyle(
        name="ReportSubheading",
        parent=normal,
        fontSize=10,
        textColor=colors.grey,
    )
    company_style = ParagraphStyle(
        name="CompanyName",
        parent=normal,
        fontSize=14,
        textColor=PRIMARY_GREEN,
        fontName="Helvetica-Bold",
    )

    flowables = []

    # Logo and company name in header
    logo_img = None
    if logo_bytes:
        logo_img = _image_from_bytes(logo_bytes, width=45 * mm, max_height=18 * mm)

    if logo_img and company_name:
        company_para = Paragraph(company_name, company_style)
        header_table = Table([[logo_img, company_para]], colWidths=[50 * mm, 130 * mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        flowables.append(header_table)
    elif logo_img:
        flowables.append(logo_img)
    elif company_name:
        flowables.append(Paragraph(company_name, company_style))

    flowables.append(Spacer(1, 10))

    # Green accent line
    line_table = Table([[""]], colWidths=[180 * mm])
    line_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 3, PRIMARY_GREEN),
    ]))
    flowables.append(line_table)
    flowables.append(Spacer(1, 10))

    # Title and date
    flowables.append(Paragraph(title, heading))
    flowables.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", subheading))
    flowables.append(Spacer(1, 15))

    return flowables


def _table_style() -> TableStyle:
    """Green-themed table style for report tables."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREEN]),
    ])


def _create_bar_chart(data: List[Tuple[str, float]], title: str = "", width: int = 400, height: int = 200) -> Drawing:
    """Create a vertical bar chart with green theme."""
    drawing = Drawing(width, height)

    if not data:
        return drawing

    labels = [d[0][:12] for d in data]  # Truncate long labels
    values = [d[1] for d in data]

    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 30
    chart.width = width - 80
    chart.height = height - 60
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.boxAnchor = 'ne'
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 8
    chart.bars[0].fillColor = PRIMARY_GREEN
    chart.bars[0].strokeColor = DARK_GREEN
    chart.bars[0].strokeWidth = 0.5

    drawing.add(chart)

    if title:
        drawing.add(String(width / 2, height - 10, title,
                          textAnchor='middle', fontSize=10, fillColor=DARK_GREEN))

    return drawing


def _create_horizontal_bar_chart(data: List[Tuple[str, float]], title: str = "", width: int = 450, height: int = 200) -> Drawing:
    """Create a horizontal bar chart with green theme."""
    drawing = Drawing(width, height)

    if not data:
        return drawing

    labels = [d[0][:15] for d in data]
    values = [d[1] for d in data]

    chart = HorizontalBarChart()
    chart.x = 100
    chart.y = 20
    chart.width = width - 130
    chart.height = height - 50
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 8
    chart.bars[0].fillColor = PRIMARY_GREEN
    chart.bars[0].strokeColor = DARK_GREEN

    drawing.add(chart)

    if title:
        drawing.add(String(width / 2, height - 10, title,
                          textAnchor='middle', fontSize=10, fillColor=DARK_GREEN))

    return drawing


def _create_pie_chart(data: List[Tuple[str, float]], title: str = "", width: int = 350, height: int = 200) -> Drawing:
    """Create a pie chart with green theme."""
    drawing = Drawing(width, height)

    if not data or sum(d[1] for d in data) == 0:
        return drawing

    labels = [d[0] for d in data]
    values = [d[1] for d in data]

    pie = Pie()
    pie.x = 80
    pie.y = 30
    pie.width = 120
    pie.height = 120
    pie.data = values
    pie.labels = [f"{l} ({int(v)})" for l, v in zip(labels, values)]
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white

    for i, _ in enumerate(values):
        pie.slices[i].fillColor = CHART_COLORS[i % len(CHART_COLORS)]

    drawing.add(pie)

    # Legend
    legend = Legend()
    legend.x = 220
    legend.y = height - 50
    legend.dx = 8
    legend.dy = 8
    legend.fontName = 'Helvetica'
    legend.fontSize = 8
    legend.boxAnchor = 'nw'
    legend.columnMaximum = 10
    legend.strokeWidth = 0.5
    legend.strokeColor = colors.HexColor("#d1d5db")
    legend.deltax = 75
    legend.deltay = 10
    legend.autoXPadding = 5
    legend.yGap = 0
    legend.dxTextSpace = 5
    legend.alignment = 'right'
    legend.dividerLines = 1 | 2 | 4
    legend.dividerOffsY = 4.5
    legend.subCols.rpad = 30
    legend.colorNamePairs = [(CHART_COLORS[i % len(CHART_COLORS)], labels[i]) for i in range(len(labels))]

    drawing.add(legend)

    if title:
        drawing.add(String(width / 2, height - 10, title,
                          textAnchor='middle', fontSize=10, fillColor=DARK_GREEN))

    return drawing


def generate_pipeline_value_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Pipeline Value Report with logo and chart."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Pipeline Value Report", logo_bytes)

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"<b>Period:</b> {period}", normal))
    flowables.append(Spacer(1, 15))

    stages = data.get("stages", [])

    # Chart - weighted values by stage
    if stages:
        chart_data = [(s.get("stage", "")[:10], float(s.get("weighted_value", 0))) for s in stages if s.get("weighted_value", 0) > 0]
        if chart_data:
            chart = _create_horizontal_bar_chart(chart_data, "Weighted Pipeline by Stage", width=450, height=180)
            flowables.append(chart)
            flowables.append(Spacer(1, 15))

    # Table
    table_data = [["Stage", "Count", "Total Value", "Weighted Value"]]
    for s in stages:
        table_data.append([
            s.get("stage", ""),
            str(s.get("count", 0)),
            format_currency(s.get("total_value", 0)),
            format_currency(s.get("weighted_value", 0)),
        ])

    if len(table_data) > 1:
        t = Table(table_data, colWidths=[90, 50, 90, 90])
        t.setStyle(_table_style())
        flowables.append(t)

    flowables.append(Spacer(1, 15))

    # Summary box
    summary_data = [[
        f"Total Value: {format_currency(data.get('total_value', 0))}",
        f"Weighted Pipeline: {format_currency(data.get('total_weighted_value', 0))}"
    ]]
    summary_table = Table(summary_data, colWidths=[160, 160])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK_GREEN),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BOX", (0, 0), (-1, -1), 1, PRIMARY_GREEN),
    ]))
    flowables.append(summary_table)

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_source_performance_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Source Performance Report with logo and chart."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Source Performance Report", logo_bytes)

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"<b>Period:</b> {period} | <b>Total Leads:</b> {data.get('total_leads', 0)}", normal))
    flowables.append(Spacer(1, 15))

    sources = data.get("sources", [])

    # Chart - leads by source
    if sources:
        chart_data = [(s.get("source", "").replace("_", " ")[:12], s.get("leads_count", 0)) for s in sources[:8]]
        if chart_data:
            chart = _create_bar_chart(chart_data, "Leads by Source", width=420, height=180)
            flowables.append(chart)
            flowables.append(Spacer(1, 15))

    # Table
    table_data = [["Source", "Leads", "Quoted", "Won", "Conversion %"]]
    for s in sources:
        table_data.append([
            s.get("source", "").replace("_", " "),
            str(s.get("leads_count", 0)),
            str(s.get("quoted_count", 0)),
            str(s.get("won_count", 0)),
            f"{s.get('conversion_rate', 0):.1f}%",
        ])

    if len(table_data) > 1:
        t = Table(table_data, colWidths=[100, 60, 60, 60, 80])
        t.setStyle(_table_style())
        flowables.append(t)

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_closer_performance_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Closer Performance Report with logo and chart."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Closer Performance Report", logo_bytes)

    closers = data.get("closers", [])

    # Chart - revenue by closer
    if closers:
        chart_data = [(c.get("full_name", "")[:12], float(c.get("total_revenue", 0))) for c in closers if c.get("total_revenue", 0) > 0]
        if chart_data:
            chart = _create_horizontal_bar_chart(chart_data, "Revenue by Closer", width=450, height=min(180, 50 + len(chart_data) * 25))
            flowables.append(chart)
            flowables.append(Spacer(1, 15))

    # Table
    table_data = [["Closer", "Leads Assigned", "Won", "Total Revenue"]]
    for c in closers:
        table_data.append([
            c.get("full_name", ""),
            str(c.get("leads_assigned", 0)),
            str(c.get("won_count", 0)),
            format_currency(c.get("total_revenue", 0)),
        ])

    if len(table_data) > 1:
        t = Table(table_data, colWidths=[120, 80, 60, 100])
        t.setStyle(_table_style())
        flowables.append(t)
    else:
        flowables.append(Paragraph("No closer data available.", normal))

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_quote_engagement_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Quote Engagement Report with logo and pie chart."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Quote Engagement Report", logo_bytes)

    period = data.get("period") or "All time"
    flowables.append(Paragraph(f"<b>Period:</b> {period}", normal))
    flowables.append(Spacer(1, 15))

    # Pie chart - engagement breakdown
    sent = data.get("sent_count", 0)
    viewed = data.get("viewed_count", 0)
    not_opened = data.get("not_opened_count", 0)
    accepted = data.get("accepted_count", 0)
    rejected = data.get("rejected_count", 0)

    if sent > 0:
        chart_data = [
            ("Accepted", accepted),
            ("Rejected", rejected),
            ("Viewed (Pending)", viewed - accepted - rejected if viewed > accepted + rejected else 0),
            ("Not Opened", not_opened),
        ]
        chart_data = [(l, v) for l, v in chart_data if v > 0]
        if chart_data:
            chart = _create_pie_chart(chart_data, "Quote Status Breakdown", width=380, height=200)
            flowables.append(chart)
            flowables.append(Spacer(1, 15))

    # Table
    table_data = [
        ["Metric", "Count"],
        ["Total Sent", str(sent)],
        ["Viewed", str(viewed)],
        ["Not Opened", str(not_opened)],
        ["Viewed (No Reply)", str(data.get("viewed_no_reply_count", 0))],
        ["Accepted", str(accepted)],
        ["Rejected", str(rejected)],
    ]

    t = Table(table_data, colWidths=[180, 100])
    t.setStyle(_table_style())
    flowables.append(t)

    # Summary stats
    if sent > 0:
        flowables.append(Spacer(1, 15))
        view_rate = (viewed / sent * 100) if sent > 0 else 0
        accept_rate = (accepted / sent * 100) if sent > 0 else 0
        summary_text = f"<b>View Rate:</b> {view_rate:.1f}% | <b>Acceptance Rate:</b> {accept_rate:.1f}%"
        flowables.append(Paragraph(summary_text, ParagraphStyle(
            name="SummaryText",
            parent=normal,
            textColor=DARK_GREEN,
            fontSize=11,
        )))

    doc.build(flowables)
    buffer.seek(0)
    return buffer


def generate_weekly_summary_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate PDF for Weekly Pipeline Summary Report with logo and chart."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Weekly Pipeline Summary", logo_bytes)

    flowables.append(Paragraph(f"<b>Week:</b> {data.get('week_label', '')}", normal))
    flowables.append(Spacer(1, 15))

    new_count = data.get("new_count", 0)
    quoted_count = data.get("quoted_count", 0)
    won_count = data.get("won_count", 0)
    lost_count = data.get("lost_count", 0)

    # Bar chart
    chart_data = [
        ("New", new_count),
        ("Quoted", quoted_count),
        ("Won", won_count),
        ("Lost", lost_count),
    ]
    if any(v > 0 for _, v in chart_data):
        chart = _create_bar_chart(chart_data, "Weekly Pipeline Activity", width=350, height=180)
        flowables.append(chart)
        flowables.append(Spacer(1, 15))

    # Table
    table_data = [
        ["Metric", "Count"],
        ["New Leads", str(new_count)],
        ["Quoted", str(quoted_count)],
        ["Won", str(won_count)],
        ["Lost", str(lost_count)],
    ]

    t = Table(table_data, colWidths=[180, 100])
    t.setStyle(_table_style())
    flowables.append(t)

    # Summary
    total_activity = new_count + quoted_count + won_count + lost_count
    if total_activity > 0:
        flowables.append(Spacer(1, 15))
        win_rate = (won_count / (won_count + lost_count) * 100) if (won_count + lost_count) > 0 else 0
        summary_data = [[
            f"Total Activity: {total_activity}",
            f"Win Rate: {win_rate:.1f}%"
        ]]
        summary_table = Table(summary_data, colWidths=[140, 140])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, -1), DARK_GREEN),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), 1, PRIMARY_GREEN),
        ]))
        flowables.append(summary_table)

    doc.build(flowables)
    buffer.seek(0)
    return buffer
