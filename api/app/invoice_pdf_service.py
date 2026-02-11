"""
Service for generating invoice PDF documents from orders.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from typing import Optional, List, Any
from io import BytesIO
from decimal import Decimal
from app.models import Order, Customer, OrderItem, CompanySettings
from app.constants import VAT_RATE_DECIMAL
from app.quote_pdf_service import (
    format_currency,
    _build_header_flowables,
    _build_footer_flowables,
    _resolve_logo,
)
from sqlmodel import Session, select


def _build_invoice_elements(
    order: Order,
    customer: Customer,
    order_items: List[OrderItem],
    company_settings: Optional[CompanySettings],
    session: Optional[Session],
    title: str,
    deposit_paid_label: str,
    balance_label: Optional[str],
    balance_bold: bool,
    note_text: Optional[str],
    invoice_display_number: Optional[str] = None,
) -> BytesIO:
    """Shared logic for building invoice PDF elements. Returns PDF buffer."""
    if not company_settings and session:
        company_settings = session.exec(select(CompanySettings).limit(1)).first()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )
    elements: List[Any] = []

    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0b3d2e")
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=brand_color,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "InvoiceHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=brand_color,
        spaceAfter=3,
        spaceBefore=6,
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "Normal",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#555555"),
    )
    company_name_style = ParagraphStyle(
        "CompanyName",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=brand_color,
        spaceAfter=2,
        fontName="Helvetica-Bold",
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=normal_style,
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        alignment=1,
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.white,
        fontName="Helvetica-Bold",
        alignment=0,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=normal_style,
        fontSize=10,
        fontName="Helvetica-Bold",
        spaceBefore=8,
        spaceAfter=4,
    )

    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    if company_settings:
        logo_path, logo_bytes = _resolve_logo(company_settings)
        customer_number = getattr(customer, "customer_number", None)
        elements.extend(
            _build_header_flowables(
                company_settings,
                logo_path,
                logo_bytes,
                normal_style,
                company_name_style,
                customer_number,
            )
        )

    # Invoice title and details
    invoice_header_data = [[Paragraph(f"<b>{title}</b>", title_style), ""]]
    invoice_details = [
        ["Invoice Number:", invoice_display_number or (order.invoice_number or "")],
        ["Order Number:", order.order_number],
        ["Date:", order.created_at.strftime("%d %B %Y")],
    ]
    invoice_header_table = Table(invoice_header_data, colWidths=[100 * mm, 80 * mm])
    invoice_header_table.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    elements.append(invoice_header_table)
    elements.append(Spacer(1, 4))

    invoice_table = Table(invoice_details, colWidths=[50 * mm, 130 * mm])
    invoice_table.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
        ])
    )
    elements.append(invoice_table)
    elements.append(Spacer(1, 8))

    # Customer details
    elements.append(Paragraph("Bill To:", heading_style))
    customer_info = [
        customer.name,
        customer.email or "",
        customer.phone or "",
    ]
    if customer.address_line1:
        address_parts = [
            customer.address_line1,
            customer.address_line2,
            customer.city,
            customer.county,
            customer.postcode,
        ]
        customer_info.append(", ".join([p for p in address_parts if p]))
    for info in customer_info:
        if info:
            elements.append(Paragraph(info, normal_style))
    elements.append(Spacer(1, 8))

    # Line items
    elements.append(Paragraph("Items:", heading_style))
    table_data = [
        [
            Paragraph("Description", table_header_style),
            Paragraph("Quantity", table_header_style),
            Paragraph("Unit Price <font size='6'>(Ex VAT)</font>", table_header_style),
            Paragraph("Total <font size='6'>(Ex VAT)</font>", table_header_style),
        ]
    ]
    sorted_items = sorted(order_items, key=lambda i: getattr(i, "sort_order", 0) or 0)
    for item in sorted_items:
        table_data.append([
            item.description or "",
            str(item.quantity),
            format_currency(item.unit_price, order.currency),
            format_currency(item.final_line_total, order.currency),
        ])

    subtotal_row_index = len(table_data)
    table_data.append(["Subtotal (Ex VAT):", "", "", format_currency(order.subtotal, order.currency)])
    discount_row_index = None
    if order.discount_total > 0:
        discount_row_index = len(table_data)
        table_data.append(["Discount:", "", "", format_currency(order.discount_total, order.currency)])
    total_ex_vat_row_index = len(table_data)
    table_data.append(["Total (Ex VAT):", "", "", format_currency(order.total_amount, order.currency)])
    vat_amount = order.total_amount * VAT_RATE_DECIMAL
    total_inc_vat = order.total_amount + vat_amount
    vat_row_index = len(table_data)
    table_data.append(["VAT @ 20%:", "", "", format_currency(vat_amount, order.currency)])
    total_row_index = len(table_data)
    table_data.append(["Total (inc VAT):", "", "", format_currency(total_inc_vat, order.currency)])

    deposit_row_index = None
    balance_row_index = None
    if order.total_amount > 0:
        deposit_row_index = len(table_data)
        table_data.append([deposit_paid_label, "", "", format_currency(order.deposit_amount, order.currency)])
        if balance_label is not None:
            balance_row_index = len(table_data)
            table_data.append([balance_label, "", "", format_currency(order.balance_amount, order.currency)])

    table_style_list = [
        ("BACKGROUND", (0, 0), (-1, 0), brand_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 1), (-1, -2), 9),
        ("FONTSIZE", (0, -3), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#e0e0e0")),
        ("LINEBELOW", (0, total_row_index), (-1, total_row_index), 1.5, brand_color),
        ("LINEABOVE", (0, total_row_index), (-1, total_row_index), 0.5, colors.HexColor("#e0e0e0")),
        ("SPAN", (0, subtotal_row_index), (2, subtotal_row_index)),
        ("ALIGN", (0, subtotal_row_index), (2, subtotal_row_index), "RIGHT"),
        ("FONTNAME", (0, subtotal_row_index), (3, subtotal_row_index), "Helvetica-Bold"),
        ("SPAN", (0, total_ex_vat_row_index), (2, total_ex_vat_row_index)),
        ("ALIGN", (0, total_ex_vat_row_index), (2, total_ex_vat_row_index), "RIGHT"),
        ("SPAN", (0, vat_row_index), (2, vat_row_index)),
        ("ALIGN", (0, vat_row_index), (2, vat_row_index), "RIGHT"),
        ("FONTNAME", (0, vat_row_index), (3, vat_row_index), "Helvetica-Bold"),
        ("SPAN", (0, total_row_index), (2, total_row_index)),
        ("ALIGN", (0, total_row_index), (2, total_row_index), "RIGHT"),
        ("FONTNAME", (0, total_row_index), (3, total_row_index), "Helvetica-Bold"),
    ]
    if discount_row_index is not None:
        table_style_list.append(("SPAN", (0, discount_row_index), (2, discount_row_index)))
        table_style_list.append(("ALIGN", (0, discount_row_index), (2, discount_row_index), "RIGHT"))
    if deposit_row_index is not None:
        table_style_list.append(("SPAN", (0, deposit_row_index), (2, deposit_row_index)))
        table_style_list.append(("ALIGN", (0, deposit_row_index), (2, deposit_row_index), "RIGHT"))
        table_style_list.append(("FONTNAME", (0, deposit_row_index), (3, deposit_row_index), "Helvetica-Bold"))
    if balance_row_index is not None:
        table_style_list.append(("SPAN", (0, balance_row_index), (2, balance_row_index)))
        table_style_list.append(("ALIGN", (0, balance_row_index), (2, balance_row_index), "RIGHT"))
        font_weight = "Helvetica-Bold" if balance_bold else "Helvetica"
        table_style_list.append(("FONTNAME", (0, balance_row_index), (3, balance_row_index), font_weight))

    items_table = Table(table_data, colWidths=[90 * mm, 25 * mm, 30 * mm, 35 * mm])
    items_table.setStyle(TableStyle(table_style_list))
    elements.append(items_table)
    elements.append(Spacer(1, 8))

    if note_text:
        elements.append(Paragraph(note_text, note_style))

    if company_settings:
        elements.append(Spacer(1, 8))
        elements.extend(_build_footer_flowables(company_settings, footer_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_deposit_paid_invoice_pdf(
    order: Order,
    customer: Customer,
    order_items: List[OrderItem],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
    invoice_display_number: Optional[str] = None,
) -> BytesIO:
    """
    Generate Deposit Paid invoice PDF: deposit paid, outstanding balance due in bold,
    with note "Balance will be required when contacted to book in Installation or delivery".
    """
    return _build_invoice_elements(
        order=order,
        customer=customer,
        order_items=order_items,
        company_settings=company_settings,
        session=session,
        title="INVOICE",
        deposit_paid_label="Deposit paid:",
        balance_label="Outstanding balance due:",
        balance_bold=True,
        note_text="Balance will be required when contacted to book in Installation or delivery.",
        invoice_display_number=invoice_display_number or (f"{order.invoice_number}-1" if order.invoice_number else None),
    )


def generate_paid_in_full_invoice_pdf(
    order: Order,
    customer: Customer,
    order_items: List[OrderItem],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
    invoice_display_number: Optional[str] = None,
) -> BytesIO:
    """
    Generate Paid in Full invoice PDF: shows deposit and balance both paid, no outstanding balance.
    """
    return _build_invoice_elements(
        order=order,
        customer=customer,
        order_items=order_items,
        company_settings=company_settings,
        session=session,
        title="INVOICE - PAID IN FULL",
        deposit_paid_label="Deposit paid:",
        balance_label="Balance paid:",
        balance_bold=False,
        note_text=None,
        invoice_display_number=invoice_display_number or (f"{order.invoice_number}-2" if order.invoice_number else None),
    )
