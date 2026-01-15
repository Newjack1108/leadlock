"""
Service for generating PDF documents from quotes.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.pdfgen import canvas
from typing import Optional
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from app.models import Quote, Customer, QuoteItem, CompanySettings
from sqlmodel import Session, select
import os
from pathlib import Path


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
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=20*mm, rightMargin=20*mm)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0b3d2e")
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=brand_color,
        spaceAfter=12,
        fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=brand_color,
        spaceAfter=8,
        spaceBefore=12,
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "Normal",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
    )
    company_name_style = ParagraphStyle(
        "CompanyName",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=brand_color,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    
    # Header - Company Info with Logo
    if company_settings:
        # Try to load logo
        logo = None
        logo_path = None
        
        # Try multiple possible logo locations
        possible_logo_paths = [
            Path(__file__).parent.parent / "static" / company_settings.logo_filename,
            Path("static") / company_settings.logo_filename,
            Path(__file__).parent.parent.parent / "web" / "public" / company_settings.logo_filename,
            company_settings.logo_filename,  # Absolute path
        ]
        
        for path in possible_logo_paths:
            if isinstance(path, str):
                if os.path.exists(path):
                    logo_path = path
                    break
            else:
                if path.exists():
                    logo_path = str(path)
                    break
        
        if logo_path and os.path.exists(logo_path):
            try:
                # Load logo with appropriate size (max width 60mm, maintain aspect ratio)
                logo = Image(logo_path, width=60*mm, height=None)
                # Maintain aspect ratio
                if logo.imageHeight > 0:
                    aspect_ratio = logo.imageWidth / logo.imageHeight
                    logo.height = logo.width / aspect_ratio
                    # Limit height to 25mm max
                    if logo.height > 25*mm:
                        logo.height = 25*mm
                        logo.width = logo.height * aspect_ratio
            except Exception as e:
                print(f"Warning: Could not load logo from {logo_path}: {e}", file=__import__('sys').stderr, flush=True)
                logo = None
        
        # Create header table with logo and company info
        if logo:
            # Logo on left, company info on right
            # Build company info as HTML text with line breaks
            company_info_lines = []
            trading_name = company_settings.trading_name or "Cheshire Stables"
            company_info_lines.append(f"<font size='14'><b>{trading_name}</b></font>")
            
            if company_settings.address_line1:
                address_parts = [
                    company_settings.address_line1,
                    company_settings.address_line2,
                    company_settings.city,
                    company_settings.county,
                    company_settings.postcode
                ]
                address = ", ".join([p for p in address_parts if p])
                company_info_lines.append(address)
            
            if company_settings.company_registration_number:
                company_info_lines.append(f"Company Reg: {company_settings.company_registration_number}")
            if company_settings.vat_number:
                company_info_lines.append(f"VAT Number: {company_settings.vat_number}")
            
            if company_settings.phone:
                company_info_lines.append(f"Phone: {company_settings.phone}")
            if company_settings.email:
                company_info_lines.append(f"Email: {company_settings.email}")
            if company_settings.website:
                company_info_lines.append(f"Website: {company_settings.website}")
            
            company_info_text = "<br/>".join(company_info_lines)
            company_info_para = Paragraph(company_info_text, normal_style)
            
            header_table = Table([[logo, company_info_para]], colWidths=[70*mm, 110*mm])
            header_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(header_table)
        else:
            # No logo - just company info
            trading_name = company_settings.trading_name or "Cheshire Stables"
            elements.append(Paragraph(trading_name, company_name_style))
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
            if company_settings.company_registration_number:
                elements.append(Paragraph(f"Company Reg: {company_settings.company_registration_number}", normal_style))
            if company_settings.vat_number:
                elements.append(Paragraph(f"VAT Number: {company_settings.vat_number}", normal_style))
            if company_settings.phone:
                elements.append(Paragraph(f"Phone: {company_settings.phone}", normal_style))
            if company_settings.email:
                elements.append(Paragraph(f"Email: {company_settings.email}", normal_style))
            if company_settings.website:
                elements.append(Paragraph(f"Website: {company_settings.website}", normal_style))
        
        elements.append(Spacer(1, 15))
    
    # Quote Title and Details Section
    quote_header_data = [
        [Paragraph("<b>QUOTE</b>", title_style), ""],
    ]
    
    quote_details = [
        ["Quote Number:", quote.quote_number],
        ["Date:", quote.created_at.strftime("%d %B %Y")],
        ["Version:", str(quote.version)],
    ]
    if quote.valid_until:
        quote_details.append(["Valid Until:", quote.valid_until.strftime("%d %B %Y")])
    
    # Combine title and details in a table
    quote_header_table = Table(quote_header_data, colWidths=[100*mm, 80*mm])
    quote_header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(quote_header_table)
    elements.append(Spacer(1, 8))
    
    quote_table = Table(quote_details, colWidths=[50*mm, 130*mm])
    quote_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(quote_table)
    elements.append(Spacer(1, 15))
    
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
    
    items_table = Table(table_data, colWidths=[90*mm, 25*mm, 30*mm, 35*mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), brand_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("FONTSIZE", (0, 1), (-1, -2), 10),
        ("FONTSIZE", (0, -3), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#e0e0e0")),
        ("LINEBELOW", (0, -3), (-1, -1), 1.5, brand_color),
        ("LINEABOVE", (0, -3), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 20))
    
    # Terms and Conditions
    if quote.terms_and_conditions:
        elements.append(Paragraph("Terms and Conditions:", heading_style))
        terms_style = ParagraphStyle(
            "Terms",
            parent=normal_style,
            fontSize=9,
            leftIndent=5*mm,
            spaceAfter=6,
        )
        # Split terms by newlines and add each as a paragraph
        for line in quote.terms_and_conditions.split('\n'):
            if line.strip():
                elements.append(Paragraph(line.strip(), terms_style))
        elements.append(Spacer(1, 15))
    
    # Footer with company details
    if company_settings:
        elements.append(Spacer(1, 20))
        footer_style = ParagraphStyle(
            "Footer",
            parent=normal_style,
            fontSize=8,
            textColor=colors.HexColor("#888888"),
            alignment=1,  # Center
        )
        footer_lines = []
        if company_settings.company_name:
            footer_lines.append(company_settings.company_name)
        if company_settings.address_line1:
            address_parts = [
                company_settings.address_line1,
                company_settings.city,
                company_settings.postcode
            ]
            footer_lines.append(", ".join([p for p in address_parts if p]))
        if company_settings.phone or company_settings.email:
            contact = []
            if company_settings.phone:
                contact.append(f"Tel: {company_settings.phone}")
            if company_settings.email:
                contact.append(f"Email: {company_settings.email}")
            footer_lines.append(" | ".join(contact))
        
        for line in footer_lines:
            elements.append(Paragraph(line, footer_style))
    
    # Notes (Internal - typically not shown to customer, but included for completeness)
    # Note: In a real scenario, you might want to exclude this from customer-facing PDFs
    # if quote.notes:
    #     elements.append(Spacer(1, 10))
    #     elements.append(Paragraph("Internal Notes:", heading_style))
    #     elements.append(Paragraph(quote.notes, normal_style))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
