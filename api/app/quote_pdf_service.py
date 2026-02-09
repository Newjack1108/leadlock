"""
Service for generating PDF documents from quotes.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from typing import Optional, Tuple, List, Any
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from app.models import Quote, Customer, QuoteItem, CompanySettings
from app.constants import VAT_RATE_DECIMAL
from sqlmodel import Session, select
import os
import urllib.request
from pathlib import Path
from urllib.parse import quote

# Tracking links for quote PDF header (each URL gets ?ltk=customer_number when generating)
QUOTE_WEBSITE_BASE_URLS = [
    ("https://www.csgbgroup.co.uk", "www.csgbgroup.co.uk"),
    ("https://www.beaverlogcabins.co.uk", "www.beaverlogcabins.co.uk"),
    ("https://www.cheshirestables.co.uk", "www.cheshirestables.co.uk"),
]


def format_currency(amount: Decimal, currency: str = "GBP") -> str:
    """Format decimal amount as currency string."""
    if currency == "GBP":
        return f"£{amount:,.2f}"
    return f"{currency} {amount:,.2f}"


def _build_header_flowables(
    company_settings: CompanySettings,
    logo_path: Optional[str],
    logo_bytes: Optional[bytes],
    normal_style: ParagraphStyle,
    company_name_style: ParagraphStyle,
    customer_number: Optional[str] = None,
) -> List[Any]:
    """Build header flowables (logo + company info). When no logo is found, a placeholder is shown."""
    result: List[Any] = []
    logo = None
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=50*mm, height=None)
            if logo.imageHeight > 0:
                aspect_ratio = logo.imageWidth / logo.imageHeight
                logo.height = logo.width / aspect_ratio
                if logo.height > 18*mm:
                    logo.height = 18*mm
                    logo.width = logo.height * aspect_ratio
        except Exception:
            logo = None
    elif logo_bytes:
        try:
            # Use ImageReader + fresh BytesIO so ReportLab can read the image reliably
            buf = BytesIO(logo_bytes)
            buf.seek(0)
            reader = ImageReader(buf)
            logo = Image(reader, width=50*mm, height=None)
            if logo.imageHeight > 0:
                aspect_ratio = logo.imageWidth / logo.imageHeight
                logo.height = logo.width / aspect_ratio
                if logo.height > 18*mm:
                    logo.height = 18*mm
                    logo.width = logo.height * aspect_ratio
        except Exception:
            logo = None
    # Company info (used with or without logo)
    company_info_lines = []
    trading_name = company_settings.trading_name or "Cheshire Stables"
    company_info_lines.append(f"<font size='12'><b>{trading_name}</b></font>")
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
    if company_settings.phone:
        company_info_lines.append(f"Phone: {company_settings.phone}")
    if company_settings.email:
        company_info_lines.append(f"Email: {company_settings.email}")
    if customer_number:
        # Three tracking links with ltk=customer_number for website visit attribution
        token = quote(customer_number, safe="")
        link_parts = [
            f'<a href="{base}?ltk={token}">{label}</a>'
            for base, label in QUOTE_WEBSITE_BASE_URLS
        ]
        company_info_lines.append("Websites: " + " | ".join(link_parts))
    elif company_settings.website:
        company_info_lines.append(f"Website: {company_settings.website}")
    company_info_text = "<br/>".join(company_info_lines)
    company_info_para = Paragraph(company_info_text, normal_style)

    if logo:
        header_table = Table([[logo, company_info_para]], colWidths=[60*mm, 120*mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        result.append(header_table)
    else:
        # Placeholder so layout matches and you know where to put the logo
        placeholder_style = ParagraphStyle(
            "LogoPlaceholder",
            parent=normal_style,
            fontSize=8,
            textColor=colors.HexColor("#888888"),
            alignment=1,  # center
        )
        placeholder_para = Paragraph(
            "<b>Your logo here</b><br/><font size='6'>See QUOTE_PDF_LOGO.md</font>",
            placeholder_style,
        )
        placeholder_table = Table([[placeholder_para]], colWidths=[50*mm])
        placeholder_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f0f0")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        header_table = Table([[placeholder_table, company_info_para]], colWidths=[60*mm, 120*mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        result.append(header_table)
    result.append(Spacer(1, 8))
    return result


def _build_footer_flowables(
    company_settings: CompanySettings,
    footer_style: ParagraphStyle,
) -> List[Any]:
    """Build footer flowables (company details)."""
    result: List[Any] = []
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
        result.append(Paragraph(line, footer_style))
    return result


def _resolve_logo(company_settings: CompanySettings) -> Tuple[Optional[str], Optional[bytes]]:
    """Resolve logo to file path or raw bytes. Prefers company logo_url (upload); else logo_filename + static/env fallback."""
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    # Prefer uploaded logo URL (from Settings -> Company -> upload)
    logo_url = (company_settings.logo_url or "").strip()
    if logo_url:
        if logo_url.startswith("http://") or logo_url.startswith("https://"):
            try:
                req = urllib.request.Request(
                    logo_url,
                    headers={"User-Agent": "LeadLock-API/1.0 (Quote PDF)"},
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = response.read()
                if data and len(data) >= 100 and (data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC)):
                    return (None, data)
            except Exception:
                pass
        elif logo_url.startswith("/static/"):
            # API static path e.g. /static/products/uuid.jpg
            static_base = Path(__file__).parent.parent
            local_path = static_base / logo_url.lstrip("/")
            if local_path.exists():
                try:
                    with open(local_path, "rb") as f:
                        return (None, f.read())
                except Exception:
                    pass

    # Fallback: logo_filename + local paths + env URL candidates
    primary_filename = company_settings.logo_filename or "logo1.jpg"
    base_dirs = [
        Path(__file__).parent.parent / "static",
        Path("static"),
        Path(__file__).parent.parent.parent / "web" / "public",
    ]
    filenames_to_try = [primary_filename]
    if primary_filename != "logo1.png":
        filenames_to_try.append("logo1.png")
    if primary_filename != "logo1.jpg":
        filenames_to_try.append("logo1.jpg")
    for fn in filenames_to_try:
        for base in base_dirs:
            p = base / fn
            if p.exists():
                logo_path = str(p)
                return (logo_path, None)
        if os.path.exists(fn):
            logo_path = fn
            return (logo_path, None)
    # URL fallback (needed when API runs separately from frontend, e.g. on Railway).
    # Set LOGO_URL on the API service to the full image URL (e.g. https://your-frontend.up.railway.app/logo1.jpg)
    # or FRONTEND_URL to the frontend origin (e.g. https://your-frontend.up.railway.app).
    DEFAULT_LOGO_BASE = "https://leadlock-frontend-production.up.railway.app"
    url_candidates = []
    env_logo_url = (os.getenv("LOGO_URL") or "").strip()
    env_logo_base = os.getenv("LOGO_BASE_URL")
    env_frontend_url = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not env_frontend_url:
        env_frontend_url = DEFAULT_LOGO_BASE
    cors_origins = os.getenv("CORS_ORIGINS", "")
    if env_logo_url:
        url_candidates.append(env_logo_url)
    for fn in filenames_to_try:
        if env_logo_base:
            url_candidates.append(env_logo_base.rstrip("/") + "/" + fn)
        if env_frontend_url:
            url_candidates.append(env_frontend_url.rstrip("/") + "/" + fn)
        if cors_origins:
            origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
            frontend_origin = next((o for o in origins if "frontend" in o), None)
            if frontend_origin:
                url_candidates.append(frontend_origin.rstrip("/") + "/" + fn)
            elif origins:
                url_candidates.append(origins[0].rstrip("/") + "/" + fn)
    # Always try the known production logo URL so PDFs get the logo even if env vars differ
    for fn in filenames_to_try:
        url_candidates.append(f"{DEFAULT_LOGO_BASE.rstrip('/')}/{fn}")

    for candidate_url in url_candidates:
        try:
            req = urllib.request.Request(
                candidate_url,
                headers={"User-Agent": "LeadLock-API/1.0 (Quote PDF)"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
            if not data or len(data) < 100:
                continue
            if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                return (None, data)
        except Exception:
            continue
    return (None, None)


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
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=10*mm, bottomMargin=10*mm, leftMargin=15*mm, rightMargin=15*mm)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0b3d2e")
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=brand_color,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
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
    terms_style = ParagraphStyle(
        "Terms",
        parent=normal_style,
        fontSize=8,
        leftIndent=4*mm,
        spaceAfter=3,
    )

    # Header - Company Info with Logo
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    if company_settings:
        logo_path, logo_bytes = _resolve_logo(company_settings)
        elements.extend(_build_header_flowables(company_settings, logo_path, logo_bytes, normal_style, company_name_style, customer.customer_number))

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
    if company_settings and company_settings.installation_lead_time:
        quote_details.append(["Installation lead time:", company_settings.installation_lead_time.value])
    
    # Combine title and details in a table
    quote_header_table = Table(quote_header_data, colWidths=[100*mm, 80*mm])
    quote_header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(quote_header_table)
    elements.append(Spacer(1, 4))
    
    quote_table = Table(quote_details, colWidths=[50*mm, 130*mm])
    quote_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    elements.append(quote_table)
    elements.append(Spacer(1, 8))
    
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
    elements.append(Spacer(1, 8))
    
    # Quote Items Table (grouped: main items first, then optional extras indented under parent)
    elements.append(Paragraph("Items:", heading_style))
    # Header row: smaller font so headings fit; "(Ex VAT)" in smaller size
    table_data = [
        [
            Paragraph("Description", table_header_style),
            Paragraph("Quantity", table_header_style),
            Paragraph("Unit Price <font size='6'>(Ex VAT)</font>", table_header_style),
            Paragraph("Total <font size='6'>(Ex VAT)</font>", table_header_style),
        ]
    ]
    
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
        ("FONTSIZE", (0, 1), (-1, -2), 9),
        ("FONTSIZE", (0, -3), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
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
    elements.append(Spacer(1, 8))

    # Footer with company details (page 1)
    if company_settings:
        elements.append(Spacer(1, 8))
        elements.extend(_build_footer_flowables(company_settings, footer_style))

    # Page 2: Terms and Conditions – quote terms when present, else company default (same header and footer)
    terms_text = (quote.terms_and_conditions or "").strip() or (
        (company_settings.default_terms_and_conditions or "").strip() if company_settings else ""
    )
    if terms_text and company_settings:
        elements.append(PageBreak())
        elements.extend(_build_header_flowables(company_settings, logo_path, logo_bytes, normal_style, company_name_style, customer.customer_number))
        elements.append(Paragraph("Terms and Conditions:", heading_style))
        for line in terms_text.split("\n"):
            if line.strip():
                elements.append(Paragraph(line.strip(), terms_style))
        elements.append(Spacer(1, 8))
        elements.extend(_build_footer_flowables(company_settings, footer_style))
    
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
