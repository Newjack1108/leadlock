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
from app.constants import VAT_RATE_DECIMAL
from sqlmodel import Session, select
import os
import urllib.request
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
        
        # #region agent log
        import json
        log_data = {
            "location": "quote_pdf_service.py:generate_quote_pdf",
            "message": "Starting logo search",
            "data": {
                "logo_filename": company_settings.logo_filename,
                "current_file": str(__file__),
                "parent_parent": str(Path(__file__).parent.parent) if Path(__file__).exists() else "N/A"
            },
            "timestamp": int(datetime.now().timestamp() * 1000),
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "E"
        }
        try:
            with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data) + "\n")
        except: pass
        # #endregion
        
        # Try multiple possible logo locations
        possible_logo_paths = [
            Path(__file__).parent.parent / "static" / company_settings.logo_filename,
            Path("static") / company_settings.logo_filename,
            Path(__file__).parent.parent.parent / "web" / "public" / company_settings.logo_filename,
            company_settings.logo_filename,  # Absolute path
        ]
        
        # #region agent log
        checked_paths = []
        for p in possible_logo_paths:
            path_str = str(p) if not isinstance(p, str) else p
            exists = os.path.exists(path_str) if isinstance(p, str) else p.exists()
            checked_paths.append({"path": path_str, "exists": exists})
        log_data2 = {
            "location": "quote_pdf_service.py:generate_quote_pdf",
            "message": "Checked file paths",
            "data": {"checked_paths": checked_paths},
            "timestamp": int(datetime.now().timestamp() * 1000),
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "F"
        }
        try:
            with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data2) + "\n")
        except: pass
        # #endregion
        
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
            # #region agent log
            log_data3 = {
                "location": "quote_pdf_service.py:generate_quote_pdf",
                "message": "Found logo file path",
                "data": {"logo_path": logo_path, "file_exists": os.path.exists(logo_path)},
                "timestamp": int(datetime.now().timestamp() * 1000),
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "G"
            }
            try:
                with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data3) + "\n")
            except: pass
            # #endregion
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
                # #region agent log
                log_data4 = {
                    "location": "quote_pdf_service.py:generate_quote_pdf",
                    "message": "Logo loaded successfully from file",
                    "data": {"logo_path": logo_path, "width": logo.width, "height": logo.height},
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H"
                }
                try:
                    with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_data4) + "\n")
                except: pass
                # #endregion
            except Exception as e:
                # #region agent log
                log_data5 = {
                    "location": "quote_pdf_service.py:generate_quote_pdf",
                    "message": "Failed to load logo from file",
                    "data": {"logo_path": logo_path, "error": str(e)},
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "I"
                }
                try:
                    with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                        f.write(json.dumps(log_data5) + "\n")
                except: pass
                # #endregion
                print(f"Warning: Could not load logo from {logo_path}: {e}", file=__import__('sys').stderr, flush=True)
                logo = None

        if not logo:
            # Try loading logo from URL (e.g., frontend public URL)
            logo_filename = company_settings.logo_filename or "logo1.jpg"
            url_candidates = []
            env_logo_url = os.getenv("LOGO_URL")
            env_logo_base = os.getenv("LOGO_BASE_URL")
            env_frontend_url = os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL")
            cors_origins = os.getenv("CORS_ORIGINS", "")

            if env_logo_url:
                url_candidates.append(env_logo_url)
            if env_logo_base:
                url_candidates.append(env_logo_base.rstrip("/") + "/" + logo_filename)
            if env_frontend_url:
                url_candidates.append(env_frontend_url.rstrip("/") + "/" + logo_filename)

            if cors_origins:
                origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
                # Prefer frontend origin if present
                frontend_origin = next((o for o in origins if "frontend" in o), None)
                if frontend_origin:
                    url_candidates.append(frontend_origin.rstrip("/") + "/" + logo_filename)
                elif origins:
                    url_candidates.append(origins[0].rstrip("/") + "/" + logo_filename)

            # #region agent log
            log_data6 = {
                "location": "quote_pdf_service.py:generate_quote_pdf",
                "message": "Trying URL fallback for logo",
                "data": {
                    "logo_filename": logo_filename,
                    "url_candidates": url_candidates,
                    "env_vars": {
                        "LOGO_URL": bool(env_logo_url),
                        "LOGO_BASE_URL": bool(env_logo_base),
                        "FRONTEND_URL": bool(env_frontend_url),
                        "CORS_ORIGINS": bool(cors_origins)
                    }
                },
                "timestamp": int(datetime.now().timestamp() * 1000),
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "J"
            }
            try:
                with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data6) + "\n")
            except: pass
            # #endregion

            for logo_url in url_candidates:
                try:
                    with urllib.request.urlopen(logo_url, timeout=5) as response:
                        logo_bytes = BytesIO(response.read())
                    logo = Image(logo_bytes, width=60*mm, height=None)
                    if logo.imageHeight > 0:
                        aspect_ratio = logo.imageWidth / logo.imageHeight
                        logo.height = logo.width / aspect_ratio
                        if logo.height > 25*mm:
                            logo.height = 25*mm
                            logo.width = logo.height * aspect_ratio
                    # #region agent log
                    log_data7 = {
                        "location": "quote_pdf_service.py:generate_quote_pdf",
                        "message": "Logo loaded successfully from URL",
                        "data": {"logo_url": logo_url},
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "K"
                    }
                    try:
                        with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                            f.write(json.dumps(log_data7) + "\n")
                    except: pass
                    # #endregion
                    break
                except Exception as e:
                    # #region agent log
                    log_data8 = {
                        "location": "quote_pdf_service.py:generate_quote_pdf",
                        "message": "Failed to load logo from URL",
                        "data": {"logo_url": logo_url, "error": str(e)},
                        "timestamp": int(datetime.now().timestamp() * 1000),
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "L"
                    }
                    try:
                        with open("c:\\projects\\LeadLock\\.cursor\\debug.log", "a", encoding="utf-8") as f:
                            f.write(json.dumps(log_data8) + "\n")
                    except: pass
                    # #endregion
                    print(f"Warning: Could not load logo from URL {logo_url}: {e}", file=__import__('sys').stderr, flush=True)
        
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
    
    # Quote Items Table (grouped: main items first, then optional extras indented under parent)
    elements.append(Paragraph("Items:", heading_style))
    elements.append(Paragraph("All prices Ex VAT @ 20%.", ParagraphStyle("TableNote", parent=normal_style, fontSize=9, textColor=colors.HexColor("#666666"), spaceAfter=4)))
    table_data = [["Description", "Quantity", "Unit Price (Ex VAT)", "Total (Ex VAT)"]]
    
    main_items = [i for i in quote_items if getattr(i, "parent_quote_item_id", None) is None]
    main_items.sort(key=lambda i: getattr(i, "sort_order", 0) or 0)
    for main_item in main_items:
        table_data.append([
            main_item.description or "",
            str(main_item.quantity),
            format_currency(main_item.unit_price, quote.currency),
            format_currency(main_item.final_line_total, quote.currency),
        ])
        children = [i for i in quote_items if getattr(i, "parent_quote_item_id", None) == main_item.id]
        children.sort(key=lambda i: getattr(i, "sort_order", 0) or 0)
        for child in children:
            table_data.append([
                "    — " + (child.description or ""),
                str(child.quantity),
                format_currency(child.unit_price, quote.currency),
                format_currency(child.final_line_total, quote.currency),
            ])
    
    # Add totals (no HTML tags; use table styling for emphasis). All amounts Ex VAT.
    subtotal_row_index = len(table_data)
    table_data.append(["", "", "Subtotal (Ex VAT):", format_currency(quote.subtotal, quote.currency)])
    if quote.discount_total > 0:
        table_data.append(["", "", "Discount:", format_currency(quote.discount_total, quote.currency)])
    total_ex_vat_row_index = len(table_data)
    table_data.append(["", "", "Total (Ex VAT):", format_currency(quote.total_amount, quote.currency)])
    vat_amount = quote.total_amount * VAT_RATE_DECIMAL
    total_inc_vat = quote.total_amount + vat_amount
    vat_row_index = len(table_data)
    table_data.append(["", "", "VAT @ 20%:", format_currency(vat_amount, quote.currency)])
    total_row_index = len(table_data)
    table_data.append(["", "", "Total (inc VAT):", format_currency(total_inc_vat, quote.currency)])

    # Add deposit and balance rows (always show if total > 0) — Ex VAT
    deposit_row_index = None
    balance_row_index = None
    if quote.total_amount > 0:
        deposit_row_index = len(table_data)
        table_data.append(["", "", "Deposit (on order, Ex VAT):", format_currency(quote.deposit_amount, quote.currency)])
        balance_row_index = len(table_data)
        table_data.append(["", "", "Balance (Ex VAT):", format_currency(quote.balance_amount, quote.currency)])
    
    # Build table style list
    table_style_list = [
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
        ("LINEBELOW", (0, total_row_index), (-1, total_row_index), 1.5, brand_color),
        ("LINEABOVE", (0, total_row_index), (-1, total_row_index), 0.5, colors.HexColor("#e0e0e0")),
        ("FONTNAME", (2, subtotal_row_index), (3, subtotal_row_index), "Helvetica-Bold"),
        ("FONTNAME", (2, vat_row_index), (3, vat_row_index), "Helvetica-Bold"),
        ("FONTNAME", (2, total_row_index), (3, total_row_index), "Helvetica-Bold"),
    ]
    # Add deposit and balance styling if they exist
    if deposit_row_index is not None:
        table_style_list.append(("FONTNAME", (2, deposit_row_index), (3, deposit_row_index), "Helvetica-Bold"))
    if balance_row_index is not None:
        table_style_list.append(("FONTNAME", (2, balance_row_index), (3, balance_row_index), "Helvetica-Bold"))
    
    items_table = Table(table_data, colWidths=[90*mm, 25*mm, 30*mm, 35*mm])
    items_table.setStyle(TableStyle(table_style_list))
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
        if company_settings.company_registration_number:
            footer_lines.append(f"Company No: {company_settings.company_registration_number}")
        if company_settings.vat_number:
            footer_lines.append(f"VAT No: {company_settings.vat_number}")
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
