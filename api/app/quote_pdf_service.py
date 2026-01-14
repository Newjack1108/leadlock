"""
Service for generating PDF documents from quotes.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.pdfgen import canvas
from typing import Optional
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from app.models import Quote, Customer, QuoteItem, CompanySettings
from sqlmodel import Session, select


def format_currency(amount: Decimal, currency: str = "GBP") -> str:
    """Format decimal amount as currency string."""
    if currency == "GBP":
        return f"£{amount:,.2f}"
    return f"{currency} {amount:,.2f}"


def generate_quote_pdf(
    quote: Quote,
    customer: Customer,
    quote_items: list[QuoteItem],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None
) -> BytesIO:
    """
    Generate a PDF document for a quote.
    
    Args:
        quote: Quote object
        customer: Customer object
        quote_items: List of QuoteItem objects
        company_settings: Optional CompanySettings for header/footer
        session: Optional database session to fetch company settings
    
    Returns:
        BytesIO buffer containing PDF data
    """
    # Fetch company settings if not provided
    if not company_settings and session:
        statement = select(CompanySettings).limit(1)
        company_settings = session.exec(statement).first()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=30,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=12,
    )
    normal_style = styles["Normal"]
    
    # Header - Company Info
    if company_settings:
        elements.append(Paragraph(company_settings.company_name or "Company", title_style))
        if company_settings.address_line1:
            address_parts = [
                company_settings.address_line1,
                company_settings.address_line2,
                company_settings.city,
                company_settings.county,
                company_settings.postcode
            ]
            address = ", ".join([p for p in address_parts if p])
            elements.append(Paragraph(address, normal_style))
        if company_settings.phone:
            elements.append(Paragraph(f"Phone: {company_settings.phone}", normal_style))
        if company_settings.email:
            elements.append(Paragraph(f"Email: {company_settings.email}", normal_style))
        elements.append(Spacer(1, 20))
    
    # Quote Title
    elements.append(Paragraph("QUOTE", title_style))
    elements.append(Spacer(1, 10))
    
    # Quote Details
    quote_data = [
        ["Quote Number:", quote.quote_number],
        ["Date:", quote.created_at.strftime("%d %B %Y")],
        ["Version:", str(quote.version)],
    ]
    if quote.valid_until:
        quote_data.append(["Valid Until:", quote.valid_until.strftime("%d %B %Y")])
    
    quote_table = Table(quote_data, colWidths=[80*mm, 100*mm])
    quote_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(quote_table)
    elements.append(Spacer(1, 20))
    
    # Customer Details
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
            customer.postcode
        ]
        customer_info.append(", ".join([p for p in address_parts if p]))
    
    for info in customer_info:
        if info:
            elements.append(Paragraph(info, normal_style))
    elements.append(Spacer(1, 20))
    
    # Quote Items Table
    elements.append(Paragraph("Items:", heading_style))
    
    table_data = [["Description", "Quantity", "Unit Price", "Total"]]
    
    for item in quote_items:
        table_data.append([
            item.description or "",
            str(item.quantity),
            format_currency(item.unit_price, quote.currency),
            format_currency(item.final_line_total, quote.currency)
        ])
    
    # Add totals
    table_data.append(["", "", "<b>Subtotal:</b>", format_currency(quote.subtotal, quote.currency)])
    if quote.discount_total > 0:
        table_data.append(["", "", "<b>Discount:</b>", format_currency(quote.discount_total, quote.currency)])
    table_data.append(["", "", "<b>Total:</b>", format_currency(quote.total_amount, quote.currency)])
    
    items_table = Table(table_data, colWidths=[100*mm, 30*mm, 30*mm, 30*mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -2), 1, colors.grey),
        ("LINEBELOW", (0, -3), (-1, -1), 2, colors.black),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 20))
    
    # Terms and Conditions
    if quote.terms_and_conditions:
        elements.append(Paragraph("Terms and Conditions:", heading_style))
        elements.append(Paragraph(quote.terms_and_conditions, normal_style))
        elements.append(Spacer(1, 20))
    
    # Notes
    if quote.notes:
        elements.append(Paragraph("Notes:", heading_style))
        elements.append(Paragraph(quote.notes, normal_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
