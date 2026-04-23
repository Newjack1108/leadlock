"""
Service for generating lead handover PDF documents.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlmodel import Session, select, or_
from sqlalchemy import func

from app.models import (
    Activity,
    Customer,
    Email,
    Lead,
    MessengerMessage,
    Quote,
    SmsMessage,
    User,
)


def _fmt_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    return value.strftime("%d %b %Y %H:%M")


def _fmt_currency(value: Decimal | float | int | None, currency: str = "GBP") -> str:
    amount = float(value or 0)
    if currency == "GBP":
        return f"GBP {amount:,.2f}"
    return f"{currency} {amount:,.2f}"


def _activity_label(raw: object) -> str:
    if raw is None:
        return "Activity"
    text = getattr(raw, "value", str(raw))
    return str(text).replace("_", " ").title()


def _count_result_to_int(value: object) -> int:
    if isinstance(value, (tuple, list)):
        return int(value[0] or 0)
    return int(value or 0)


def generate_lead_handover_pdf(
    session: Session,
    lead: Lead,
    customer: Optional[Customer],
    days: int = 14,
) -> BytesIO:
    lookback_days = max(1, min(days, 90))
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)

    assigned_to_name: str = "Unassigned"
    if lead.assigned_to_id:
        assigned_user = session.get(User, lead.assigned_to_id)
        if assigned_user and assigned_user.full_name:
            assigned_to_name = assigned_user.full_name

    activities: List[Activity] = []
    if customer:
        activities = list(
            session.exec(
                select(Activity)
                .where(Activity.customer_id == customer.id, Activity.created_at >= cutoff)
                .order_by(Activity.created_at.desc())
            ).all()
        )

    recent_quotes: List[Quote] = list(
        session.exec(
            select(Quote)
            .where(
                Quote.lead_id == lead.id,
                or_(Quote.updated_at >= cutoff, Quote.created_at >= cutoff),
            )
            .order_by(Quote.updated_at.desc())
        ).all()
    )

    email_count = 0
    sms_count = 0
    messenger_count = 0
    if customer:
        email_count = _count_result_to_int(
            session.exec(
                select(func.count(Email.id))
                .where(Email.customer_id == customer.id, Email.created_at >= cutoff)
            ).one()
        )
        sms_count = _count_result_to_int(
            session.exec(
                select(func.count(SmsMessage.id))
                .where(
                    SmsMessage.customer_id == customer.id,
                    SmsMessage.created_at >= cutoff,
                )
            ).one()
        )
        messenger_count = _count_result_to_int(
            session.exec(
                select(func.count(MessengerMessage.id))
                .where(
                    MessengerMessage.customer_id == customer.id,
                    MessengerMessage.created_at >= cutoff,
                )
            ).one()
        )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HandoverTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#0f5132"),
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "HandoverHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#0f5132"),
        spaceBefore=8,
        spaceAfter=4,
    )
    normal_style = ParagraphStyle(
        "HandoverNormal",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#222222"),
        leading=12,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=32,
        leftMargin=32,
        topMargin=28,
        bottomMargin=28,
    )
    elements = []

    generated_at = datetime.utcnow()
    elements.append(Paragraph("Lead Handover Summary", title_style))
    elements.append(
        Paragraph(
            f"Generated: {_fmt_datetime(generated_at)} UTC | Window: last {lookback_days} days",
            normal_style,
        )
    )
    elements.append(Spacer(1, 10))

    lead_info = [
        ["Lead name", lead.name or "-"],
        ["Status", str(getattr(lead.status, "value", lead.status or "-"))],
        ["Assigned to", assigned_to_name],
        ["Email", lead.email or "-"],
        ["Phone", lead.phone or "-"],
        ["Postcode", lead.postcode or "-"],
        ["Lead source", str(getattr(lead.lead_source, "value", lead.lead_source or "-"))],
        ["Created", _fmt_datetime(lead.created_at)],
        ["Last updated", _fmt_datetime(lead.updated_at)],
    ]
    info_table = Table(lead_info, colWidths=[110, 390])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5e9")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    elements.append(info_table)

    if customer:
        elements.append(Spacer(1, 8))
        customer_info = [
            ["Customer number", customer.customer_number or "-"],
            ["Customer name", customer.name or "-"],
            ["Customer email", customer.email or "-"],
            ["Customer phone", customer.phone or "-"],
            ["Customer since", _fmt_datetime(customer.customer_since)],
        ]
        customer_table = Table(customer_info, colWidths=[110, 390])
        customer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2ff")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(customer_table)

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Recent Communication Summary", heading_style))
    elements.append(
        Paragraph(
            f"Emails: {email_count} | SMS: {sms_count} | Messenger: {messenger_count}",
            normal_style,
        )
    )

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Recent Activity Timeline", heading_style))
    if activities:
        timeline_rows = [["When", "Type", "Notes"]]
        for activity in activities[:30]:
            timeline_rows.append(
                [
                    _fmt_datetime(activity.created_at),
                    _activity_label(activity.activity_type),
                    (activity.notes or "-")[:180],
                ]
            )
        timeline_table = Table(timeline_rows, colWidths=[95, 125, 280])
        timeline_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5132")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(timeline_table)
    else:
        elements.append(Paragraph("No activity recorded in this window.", normal_style))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Related Quotes (Recent)", heading_style))
    if recent_quotes:
        quote_rows = [["Quote", "Status", "Updated", "Total"]]
        for quote in recent_quotes[:20]:
            quote_rows.append(
                [
                    quote.quote_number,
                    str(getattr(quote.status, "value", quote.status or "-")),
                    _fmt_datetime(quote.updated_at),
                    _fmt_currency(quote.total_amount, quote.currency or "GBP"),
                ]
            )
        quote_table = Table(quote_rows, colWidths=[110, 110, 150, 130])
        quote_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f5132")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
                ]
            )
        )
        elements.append(quote_table)
    else:
        elements.append(Paragraph("No recent quotes found for this lead.", normal_style))

    elements.append(Spacer(1, 10))
    elements.append(Paragraph("Open Items / Next Actions", heading_style))
    open_items: List[str] = []
    if not activities:
        open_items.append("No recent activity logged; check if outreach is due.")
    if recent_quotes and any(str(getattr(q.status, "value", q.status)) in ("SENT", "VIEWED") for q in recent_quotes):
        open_items.append("Follow up on sent/viewed quotes still awaiting decision.")
    if lead.status and str(getattr(lead.status, "value", lead.status)) in ("NEW", "ENGAGED", "QUALIFIED"):
        open_items.append(f"Lead currently {str(getattr(lead.status, 'value', lead.status)).replace('_', ' ').title()}; review next pipeline step.")
    if not open_items:
        open_items.append("No immediate open items auto-detected. Review latest timeline entries.")

    for item in open_items:
        elements.append(Paragraph(f"- {item}", normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
