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

FACEBOOK_REPORT_COLORS = [
    colors.HexColor("#1877F2"),
    colors.HexColor("#7C3AED"),
    colors.HexColor("#F97316"),
    colors.HexColor("#06B6D4"),
    colors.HexColor("#10B981"),
    colors.HexColor("#EC4899"),
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


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _format_range_label(data: Dict[str, Any]) -> str:
    period = (data.get("period") or "").strip().lower()
    start = _coerce_datetime(data.get("start_date"))
    end = _coerce_datetime(data.get("end_date"))

    if period == "all":
        return "All time"

    if start and end and period == "custom":
        return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"

    if period == "week":
        return f"This week ({start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')})" if start and end else "This week"
    if period == "month":
        return f"This month ({start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')})" if start and end else "This month"
    if period == "quarter":
        return f"This quarter ({start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')})" if start and end else "This quarter"
    if period == "year":
        return f"This year ({start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')})" if start and end else "This year"
    if start and end:
        return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"
    return "All time"


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


def _create_colorful_horizontal_bar_chart(
    data: List[Tuple[str, float]],
    title: str = "",
    width: int = 450,
    height: int = 200,
) -> Drawing:
    """Create a horizontal bar chart with multiple accent colours."""
    drawing = Drawing(width, height)

    if not data:
        return drawing

    labels = [d[0][:18] for d in data]
    values = [d[1] for d in data]

    chart = HorizontalBarChart()
    chart.x = 110
    chart.y = 20
    chart.width = width - 140
    chart.height = height - 50
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 8
    chart.bars.strokeColor = colors.white
    chart.bars.strokeWidth = 0.5

    for i, _ in enumerate(values):
        chart.bars[(0, i)].fillColor = FACEBOOK_REPORT_COLORS[i % len(FACEBOOK_REPORT_COLORS)]

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

    flowables.append(Paragraph(f"<b>Range:</b> {_format_range_label(data)}", normal))
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

    flowables.append(Paragraph(
        f"<b>Range:</b> {_format_range_label(data)} | <b>Total Leads:</b> {data.get('total_leads', 0)}",
        normal,
    ))
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

    flowables.append(Paragraph(f"<b>Range:</b> {_format_range_label(data)}", normal))
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


def generate_facebook_lead_conversion_pdf(data: Dict[str, Any], company_name: str = "") -> BytesIO:
    """Generate a condensed printable PDF for the Facebook lead-to-order report."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=32, leftMargin=32, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    section_heading = ParagraphStyle(
        name="FacebookSectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=DARK_GREEN,
        spaceAfter=6,
    )
    muted = ParagraphStyle(
        name="FacebookMuted",
        parent=normal,
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
    )

    _, logo_bytes = _resolve_logo()
    flowables = _build_report_header(company_name, "Facebook Lead-to-Order Report", logo_bytes)
    flowables.append(Paragraph(f"<b>Range:</b> {_format_range_label(data)}", normal))
    flowables.append(Paragraph("Condensed printable summary for marketing review and team handover.", muted))
    flowables.append(Spacer(1, 12))

    summary = data.get("summary", {}) or {}
    kpi_cards = [
        ("Facebook leads", summary.get("total_facebook_leads", 0), FACEBOOK_REPORT_COLORS[0], None),
        ("Converted leads", summary.get("converted_leads", 0), FACEBOOK_REPORT_COLORS[1], f"{summary.get('total_orders', 0)} linked orders"),
        ("Conversion rate", f"{summary.get('conversion_rate', 0):.1f}%", FACEBOOK_REPORT_COLORS[2], "Lead to order"),
        ("Order revenue", format_currency(summary.get("total_order_revenue", 0)), FACEBOOK_REPORT_COLORS[3], None),
        ("Average order", format_currency(summary.get("average_order_value", 0)), FACEBOOK_REPORT_COLORS[4], None),
        ("Avg days", f"{summary.get('average_days_to_convert', 0):.1f} days", FACEBOOK_REPORT_COLORS[5], "Converted leads"),
    ]

    def build_kpi_card(title: str, value: Any, accent: colors.Color, note: Optional[str]) -> Table:
        title_style = ParagraphStyle(
            name=f"KpiTitle{title}",
            parent=normal,
            fontSize=8,
            textColor=colors.HexColor("#475569"),
            uppercase=True,
        )
        value_style = ParagraphStyle(
            name=f"KpiValue{title}",
            parent=normal,
            fontSize=15,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        note_style = ParagraphStyle(
            name=f"KpiNote{title}",
            parent=normal,
            fontSize=7.5,
            textColor=colors.HexColor("#64748b"),
        )
        rows = [
            [Paragraph(title, title_style)],
            [Paragraph(str(value), value_style)],
        ]
        if note:
            rows.append([Paragraph(note, note_style)])
        card = Table(rows, colWidths=[58 * mm])
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#dbe4f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return card

    kpi_rows = []
    for start_idx in range(0, len(kpi_cards), 3):
        slice_cards = kpi_cards[start_idx:start_idx + 3]
        built = [build_kpi_card(*card) for card in slice_cards]
        while len(built) < 3:
            built.append("")
        kpi_rows.append(built)
    kpi_table = Table(kpi_rows, colWidths=[60 * mm, 60 * mm, 60 * mm], hAlign="LEFT")
    kpi_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    flowables.append(kpi_table)
    flowables.append(Spacer(1, 10))

    advert_breakdown = data.get("advert_breakdown", []) or []
    product_breakdown = data.get("product_type_breakdown", []) or []
    rows = data.get("rows", []) or []

    if not rows:
        empty_box = Table(
            [[Paragraph("No Facebook leads were found for the selected range.", normal)]],
            colWidths=[175 * mm],
        )
        empty_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        flowables.append(empty_box)
        doc.build(flowables)
        buffer.seek(0)
        return buffer

    def build_breakdown_table(title: str, items: List[Dict[str, Any]], accent_color: colors.Color) -> None:
        flowables.append(Paragraph(title, section_heading))
        chart_data = [
            (item.get("name", "")[:18], float(item.get("total_revenue", 0) or 0))
            for item in items[:6]
            if float(item.get("total_revenue", 0) or 0) > 0
        ]
        if chart_data:
            flowables.append(_create_colorful_horizontal_bar_chart(chart_data, f"{title} by revenue", width=460, height=180))
            flowables.append(Spacer(1, 10))

        table_data = [["Name", "Leads", "Conv %", "Revenue", "Avg order", "Avg days"]]
        for item in items[:8]:
            table_data.append([
                item.get("name", ""),
                str(item.get("leads_count", 0)),
                f"{item.get('conversion_rate', 0):.1f}%",
                format_currency(item.get("total_revenue", 0)),
                format_currency(item.get("average_order_value", 0)),
                f"{item.get('average_days_to_convert', 0):.1f}",
            ])
        table = Table(table_data, colWidths=[58 * mm, 18 * mm, 20 * mm, 28 * mm, 28 * mm, 20 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), accent_color),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        flowables.append(table)
        flowables.append(Spacer(1, 14))

    build_breakdown_table("Advert profile summary", advert_breakdown, FACEBOOK_REPORT_COLORS[0])
    build_breakdown_table("Product type summary", product_breakdown, FACEBOOK_REPORT_COLORS[4])

    flowables.append(Paragraph("Exceptions and recent conversions", section_heading))
    exceptions = Table([
        ["Unknown advert tags", str(summary.get("unknown_advert_profile_leads", 0))],
        ["Won without order", str(summary.get("won_without_order_leads", 0))],
    ], colWidths=[80 * mm, 24 * mm])
    exceptions.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#9a3412")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#fdba74")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#fed7aa")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    flowables.append(exceptions)
    flowables.append(Spacer(1, 10))

    converted_rows = [row for row in rows if row.get("converted")]
    converted_rows.sort(
        key=lambda row: (
            _coerce_datetime(row.get("order_created_at")) or datetime.min,
            float(row.get("order_amount", 0) or 0),
        ),
        reverse=True,
    )

    recent_table_data = [["Lead", "Advert", "Order", "Revenue", "Days"]]
    for row in converted_rows[:8]:
        recent_table_data.append([
            row.get("lead_name", ""),
            row.get("advert_profile_name", ""),
            row.get("order_number", "") or f"{row.get('order_count', 0)} orders",
            format_currency(row.get("order_amount", 0)),
            f"{row.get('days_to_convert', 0):.1f}" if row.get("days_to_convert") is not None else "—",
        ])
    recent_table = Table(recent_table_data, colWidths=[38 * mm, 50 * mm, 30 * mm, 28 * mm, 16 * mm], repeatRows=1)
    recent_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FACEBOOK_REPORT_COLORS[3]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
    ]))
    flowables.append(recent_table)

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
    closed_count = data.get("closed_count", 0)

    # Bar chart
    chart_data = [
        ("New", new_count),
        ("Quoted", quoted_count),
        ("Won", won_count),
        ("Lost", lost_count),
        ("Closed (qualified)", closed_count),
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
        ["Closed (qualified)", str(closed_count)],
    ]

    t = Table(table_data, colWidths=[180, 100])
    t.setStyle(_table_style())
    flowables.append(t)

    # Summary
    total_activity = new_count + quoted_count + won_count + lost_count + closed_count
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
