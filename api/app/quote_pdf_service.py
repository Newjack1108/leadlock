"""
Service for generating PDF documents from quotes.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.pdfgen import canvas
from typing import Optional, Tuple, List, Any
from io import BytesIO
from datetime import datetime
from decimal import Decimal
from app.models import Quote, Customer, QuoteItem, CompanySettings, Product, QuoteItemLineType
from app.constants import VAT_RATE_DECIMAL
from sqlmodel import Session, select
import os
import sys
import tempfile
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


def _image_from_bytes(
    data: bytes, width: float, height: Optional[float] = None, max_height: Optional[float] = None
) -> Optional[Any]:
    """Create ReportLab Image from bytes (writes temp file - platypus Image needs path)."""
    try:
        if not data or len(data) < 10:
            return None
        # Compute dimensions with PIL to avoid ReportLab attribute issues
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(BytesIO(data))
            iw, ih = pil_img.size
            pil_img.close()
        except Exception:
            iw, ih = 100, 100  # fallback
        if ih <= 0:
            ih = 1
        ratio = iw / ih
        out_h = width / ratio
        cap = max_height if max_height is not None else 18 * mm
        if out_h > cap:
            out_h = cap
            out_w = cap * ratio
        else:
            out_w = width
        ext = ".png" if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (AttributeError, OSError):
                pass
            path = f.name
        return Image(path, width=out_w, height=out_h)
    except Exception as e:
        print(f"PDF _image_from_bytes failed: {e}", file=sys.stderr, flush=True)
        return None


def _build_header_flowables(
    company_settings: CompanySettings,
    logo_path: Optional[str],
    logo_bytes: Optional[bytes],
    normal_style: ParagraphStyle,
    company_name_style: ParagraphStyle,
    customer_number: Optional[str] = None,
) -> List[Any]:
    """Build header flowables (logo + company info). Logo from company settings (logo_url) or local files."""
    result: List[Any] = []
    logo = None
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=50*mm, height=None)
            if logo.imageHeight > 0:
                ar = logo.imageWidth / logo.imageHeight
                logo.height = logo.width / ar
                if logo.height > 18*mm:
                    logo.height = 18*mm
                    logo.width = logo.height * ar
        except Exception:
            logo = None
    elif logo_bytes:
        logo = _image_from_bytes(logo_bytes, width=50*mm, height=None, max_height=18*mm)
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
        header_table = Table([[company_info_para, logo]], colWidths=[120*mm, 60*mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        result.append(header_table)
    else:
        result.append(company_info_para)
    result.append(Spacer(1, 8))
    return result


FOOTER_BOTTOM_MARGIN = 45 * mm  # Space for footer on every page (logo + text + padding)


def _resolve_logo_path_for_canvas(
    logo_path: Optional[str], logo_bytes: Optional[bytes]
) -> Tuple[Optional[str], float, float]:
    """Return (path, width_mm, height_mm) for canvas.drawImage. Width/height in points."""
    logo_file: Optional[str] = None
    w_pt, h_pt = 30 * mm, 12 * mm
    if logo_bytes:
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(BytesIO(logo_bytes))
            iw, ih = pil_img.size
            pil_img.close()
            if ih > 0:
                ratio = iw / ih
                h_pt = min(12 * mm, (30 * mm) / ratio)
                w_pt = h_pt * ratio
            ext = ".png" if len(logo_bytes) >= 8 and logo_bytes[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(logo_bytes)
                f.flush()
                logo_file = f.name
        except Exception:
            logo_file = None
    elif logo_path and os.path.exists(logo_path):
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(logo_path)
            iw, ih = pil_img.size
            pil_img.close()
            if ih > 0:
                ratio = iw / ih
                h_pt = min(12 * mm, (30 * mm) / ratio)
                w_pt = h_pt * ratio
            logo_file = logo_path
        except Exception:
            logo_file = logo_path
    return (logo_file, w_pt, h_pt)


def _make_footer_canvas_drawer(
    company_settings: CompanySettings,
    footer_style: ParagraphStyle,
    logo_path: Optional[str],
    logo_bytes: Optional[bytes],
):
    """Return (canvas, doc) -> None to draw footer at bottom of every page."""
    footer_lines = []
    if company_settings.company_name:
        footer_lines.append(company_settings.company_name)
    if company_settings.address_line1:
        address_parts = [
            company_settings.address_line1,
            company_settings.city,
            company_settings.postcode,
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
    bank_parts = []
    if company_settings.bank_name:
        bank_parts.append(f"Bank: {company_settings.bank_name}")
    if company_settings.bank_account_name:
        bank_parts.append(f"Account Name: {company_settings.bank_account_name}")
    if company_settings.sort_code:
        bank_parts.append(f"Sort Code: {company_settings.sort_code}")
    if company_settings.account_number:
        bank_parts.append(f"Account: {company_settings.account_number}")
    if bank_parts:
        footer_lines.append("<b>" + " | ".join(bank_parts) + "</b>")
    footer_para = Paragraph("<br/>".join(footer_lines), footer_style) if footer_lines else None
    logo_path_canvas, logo_w, logo_h = _resolve_logo_path_for_canvas(logo_path, logo_bytes)

    def drawer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        y = 3 * mm
        # Logo at bottom, centered
        if logo_path_canvas:
            try:
                x_logo = doc.leftMargin + (doc.width - logo_w) / 2
                canvas.drawImage(logo_path_canvas, x_logo, y, width=logo_w, height=logo_h)
            except Exception:
                pass
            y += logo_h + 3 * mm
        # Footer text above logo
        if footer_para:
            try:
                avail_h = FOOTER_BOTTOM_MARGIN - y
                pw, ph = footer_para.wrap(doc.width, avail_h)
                footer_para.drawOn(canvas, doc.leftMargin, y)
            except Exception:
                pass
        canvas.restoreState()

    return drawer


def _force_cloudinary_format(url: str, fmt: str = "png") -> str:
    """Force Cloudinary to deliver PNG/JPEG instead of WebP (ReportLab doesn't support WebP)."""
    if "res.cloudinary.com" in url and "/image/upload/" in url:
        # Insert f_png or f_jpg after upload/ e.g. .../upload/f_png/v123/...
        marker = "/image/upload/"
        transf = f"f_{fmt}/"
        if marker in url and transf not in url:
            idx = url.index(marker) + len(marker)
            url = url[:idx] + transf + url[idx:]
    return url


def _ensure_png_or_jpeg_bytes(data: bytes) -> Optional[bytes]:
    """Convert WebP or other formats to PNG so ReportLab can use them. Returns None on failure."""
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
        return data
    is_webp = len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP"
    if not is_webp:
        return None
    try:
        from PIL import Image as PILImage
        img = PILImage.open(BytesIO(data))
        img = img.convert("RGB")
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None


def _resolve_logo(company_settings: CompanySettings) -> Tuple[Optional[str], Optional[bytes]]:
    """Resolve logo: same source as header (logo1.jpg from static/public), then company logo_url fallback."""
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    _debug = os.getenv("DEBUG", "false").lower() == "true"

    # 1. Use same logo as header: logo1.jpg / logo1.png from static or web/public (bundled in Docker)
    primary_filename = company_settings.logo_filename or "logo1.jpg"
    base_dirs = [
        Path(__file__).parent.parent / "static",
        Path("static"),
        Path(__file__).parent.parent.parent / "web" / "public",
    ]
    for fn in [primary_filename, "logo1.png", "logo1.jpg", "logo.png"]:
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
        if os.path.exists(fn):
            return (str(fn), None)

    # 2. Fallback: company logo_url (Cloudinary or /static/)
    logo_url = (company_settings.logo_url or "").strip()
    if logo_url:
        if logo_url.startswith("http://") or logo_url.startswith("https://"):
            # Try f_png URL first for Cloudinary (often returns WebP by default)
            urls_to_try = (
                [_force_cloudinary_format(logo_url, "png"), logo_url]
                if "res.cloudinary.com" in logo_url
                else [logo_url]
            )
            seen = set()
            for fetch_url in urls_to_try:
                if fetch_url in seen:
                    continue
                seen.add(fetch_url)
                try:
                    req = urllib.request.Request(
                        fetch_url,
                        headers={"User-Agent": "LeadLock-API/1.0 (Quote PDF)"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as response:
                        data = response.read()
                    if not data or len(data) < 50:
                        continue
                    if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                        return (None, data)
                    # Cloudinary often returns WebP; convert to PNG for ReportLab
                    converted = _ensure_png_or_jpeg_bytes(data)
                    if converted:
                        return (None, converted)
                except Exception:
                    pass
        elif logo_url.startswith("/static/"):
            static_base = Path(__file__).parent.parent
            local_path = static_base / logo_url.lstrip("/")
            if local_path.exists():
                try:
                    with open(local_path, "rb") as f:
                        return (None, f.read())
                except Exception:
                    pass

    # 3. URL fallback (frontend serves logo1.jpg like header)
    filenames_to_try = ["logo1.jpg", "logo1.png", "logo.png"]
    # Set LOGO_URL on the API service to the full image URL (e.g. https://your-frontend.up.railway.app/logo1.jpg)
    # or FRONTEND_URL to the frontend origin (e.g. https://your-frontend.up.railway.app).
    DEFAULT_LOGO_BASE = "https://leadlock-frontend-production.up.railway.app"
    url_candidates = []
    env_logo_url = (os.getenv("LOGO_URL") or "").strip()
    env_logo_base = os.getenv("LOGO_BASE_URL")
    env_frontend_url = (
        os.getenv("FRONTEND_BASE_URL")
        or os.getenv("FRONTEND_URL")
        or os.getenv("PUBLIC_FRONTEND_URL")
        or ""
    ).strip()
    if not env_frontend_url:
        env_frontend_url = DEFAULT_LOGO_BASE
    cors_origins = os.getenv("CORS_ORIGINS", "")
    # If company logo_url is a path (e.g. /logo1.jpg), try frontend base + path first
    if logo_url and logo_url.startswith("/") and not logo_url.startswith("/static/"):
        url_candidates.append(env_frontend_url.rstrip("/") + logo_url)
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
            if not data or len(data) < 50:
                continue
            if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                return (None, data)
        except Exception:
            continue
    import sys
    print("PDF logo: showing placeholder (logo1.jpg not found locally or via URL)", file=sys.stderr, flush=True)
    return (None, None)


def _resolve_footer_logo(company_settings: CompanySettings) -> Tuple[Optional[str], Optional[bytes]]:
    """Resolve footer logo: use footer_logo_url if set, otherwise fall back to header logo."""
    footer_url = (getattr(company_settings, "footer_logo_url", None) or "").strip()
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    if footer_url:
        if footer_url.startswith("http://") or footer_url.startswith("https://"):
            urls_to_try = (
                [_force_cloudinary_format(footer_url, "png"), footer_url]
                if "res.cloudinary.com" in footer_url
                else [footer_url]
            )
            seen = set()
            for fetch_url in urls_to_try:
                if fetch_url in seen:
                    continue
                seen.add(fetch_url)
                try:
                    req = urllib.request.Request(
                        fetch_url,
                        headers={"User-Agent": "LeadLock-API/1.0 (Quote PDF)"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as response:
                        data = response.read()
                    if not data or len(data) < 50:
                        continue
                    if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                        return (None, data)
                    converted = _ensure_png_or_jpeg_bytes(data)
                    if converted:
                        return (None, converted)
                except Exception:
                    pass
        elif footer_url.startswith("/static/"):
            static_base = Path(__file__).parent.parent
            local_path = static_base / footer_url.lstrip("/")
            if local_path.exists():
                try:
                    with open(local_path, "rb") as f:
                        return (None, f.read())
                except Exception:
                    pass

    return _resolve_logo(company_settings)


def generate_quote_pdf(
    quote: Quote,
    customer: Customer,
    quote_items: list[QuoteItem],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
    include_spec_sheets: bool = True,
) -> BytesIO:
    """
    Generate a PDF document for a quote.
    
    Args:
        quote: Quote object
        customer: Customer object
        quote_items: List of QuoteItem objects
        company_settings: Optional CompanySettings for header/footer
        session: Optional database session to fetch company settings
        include_spec_sheets: If True, append product spec sheets for products in the quote
    
    Returns:
        BytesIO buffer containing PDF data
    """
    # Fetch company settings if not provided
    if not company_settings and session:
        statement = select(CompanySettings).limit(1)
        company_settings = session.exec(statement).first()
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=10 * mm,
        bottomMargin=FOOTER_BOTTOM_MARGIN,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0e4a38")
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

    # Header - Company Info with Logo; Footer - separate logo if footer_logo_url set
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    footer_logo_path: Optional[str] = None
    footer_logo_bytes: Optional[bytes] = None
    if company_settings:
        logo_path, logo_bytes = _resolve_logo(company_settings)
        footer_logo_path, footer_logo_bytes = _resolve_footer_logo(company_settings)
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
    
    # Add totals (label spans cols 0-2, value in col 3). All amounts Ex VAT.
    subtotal_row_index = len(table_data)
    table_data.append(["Subtotal (Ex VAT):", "", "", format_currency(quote.subtotal, quote.currency)])
    discount_row_index = None
    if quote.discount_total > 0:
        discount_row_index = len(table_data)
        table_data.append(["Discount:", "", "", format_currency(quote.discount_total, quote.currency)])
    total_ex_vat_row_index = len(table_data)
    table_data.append(["Total (Ex VAT):", "", "", format_currency(quote.total_amount, quote.currency)])
    vat_amount = quote.total_amount * VAT_RATE_DECIMAL
    total_inc_vat = quote.total_amount + vat_amount
    vat_row_index = len(table_data)
    table_data.append(["VAT @ 20%:", "", "", format_currency(vat_amount, quote.currency)])
    total_row_index = len(table_data)
    table_data.append(["Total (inc VAT):", "", "", format_currency(total_inc_vat, quote.currency)])

    # Add deposit and balance rows (always show if total > 0) — inc VAT
    deposit_row_index = None
    balance_row_index = None
    if quote.total_amount > 0:
        deposit_row_index = len(table_data)
        table_data.append(["Deposit (on order, inc VAT):", "", "", format_currency(quote.deposit_amount, quote.currency)])
        balance_row_index = len(table_data)
        table_data.append(["Balance (inc VAT):", "", "", format_currency(quote.balance_amount, quote.currency)])
    
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
        ("SPAN", (0, subtotal_row_index), (2, subtotal_row_index)),
        ("ALIGN", (0, subtotal_row_index), (2, subtotal_row_index), "RIGHT"),
        ("FONTNAME", (0, subtotal_row_index), (3, subtotal_row_index), "Helvetica-Bold"),
        ("FONTNAME", (0, vat_row_index), (3, vat_row_index), "Helvetica-Bold"),
        ("FONTNAME", (0, total_row_index), (3, total_row_index), "Helvetica-Bold"),
    ]
    if discount_row_index is not None:
        table_style_list.append(("SPAN", (0, discount_row_index), (2, discount_row_index)))
        table_style_list.append(("ALIGN", (0, discount_row_index), (2, discount_row_index), "RIGHT"))
        table_style_list.append(("TEXTCOLOR", (0, discount_row_index), (3, discount_row_index), colors.red))
        table_style_list.append(("FONTNAME", (0, discount_row_index), (3, discount_row_index), "Helvetica-Bold"))
    table_style_list.append(("SPAN", (0, total_ex_vat_row_index), (2, total_ex_vat_row_index)))
    table_style_list.append(("ALIGN", (0, total_ex_vat_row_index), (2, total_ex_vat_row_index), "RIGHT"))
    table_style_list.append(("SPAN", (0, vat_row_index), (2, vat_row_index)))
    table_style_list.append(("ALIGN", (0, vat_row_index), (2, vat_row_index), "RIGHT"))
    table_style_list.append(("SPAN", (0, total_row_index), (2, total_row_index)))
    table_style_list.append(("ALIGN", (0, total_row_index), (2, total_row_index), "RIGHT"))
    if deposit_row_index is not None:
        table_style_list.append(("SPAN", (0, deposit_row_index), (2, deposit_row_index)))
        table_style_list.append(("ALIGN", (0, deposit_row_index), (2, deposit_row_index), "RIGHT"))
        table_style_list.append(("FONTNAME", (0, deposit_row_index), (3, deposit_row_index), "Helvetica-Bold"))
    if balance_row_index is not None:
        table_style_list.append(("SPAN", (0, balance_row_index), (2, balance_row_index)))
        table_style_list.append(("ALIGN", (0, balance_row_index), (2, balance_row_index), "RIGHT"))
        table_style_list.append(("FONTNAME", (0, balance_row_index), (3, balance_row_index), "Helvetica-Bold"))
    
    items_table = Table(table_data, colWidths=[90*mm, 25*mm, 30*mm, 35*mm])
    items_table.setStyle(TableStyle(table_style_list))
    elements.append(items_table)
    elements.append(Spacer(1, 8))

    # Footer drawn on every page via onFirstPage/onLaterPages (not flowables)
    footer_drawer = (
        _make_footer_canvas_drawer(company_settings, footer_style, footer_logo_path, footer_logo_bytes)
        if company_settings
        else None
    )

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
    
    # Notes (Internal - typically not shown to customer, but included for completeness)
    # Note: In a real scenario, you might want to exclude this from customer-facing PDFs
    # if quote.notes:
    #     elements.append(Spacer(1, 10))
    #     elements.append(Paragraph("Internal Notes:", heading_style))
    #     elements.append(Paragraph(quote.notes, normal_style))
    
    # Build PDF (footer drawn on every page by canvas callback)
    if footer_drawer:
        doc.build(elements, onFirstPage=footer_drawer, onLaterPages=footer_drawer)
    else:
        doc.build(elements)
    buffer.seek(0)

    # Optionally append product spec sheets for main products only (exclude optional extras)
    if include_spec_sheets and session and len(quote_items) > 0:
        ordered_product_ids = []
        main_items = [i for i in quote_items if getattr(i, "parent_quote_item_id", None) is None]
        main_items.sort(key=lambda i: getattr(i, "sort_order", 0) or 0)
        for main_item in main_items:
            line_type = getattr(main_item, "line_type", None)
            if line_type in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION):
                continue
            pid = getattr(main_item, "product_id", None)
            if pid is not None and pid not in ordered_product_ids:
                ordered_product_ids.append(pid)
        if ordered_product_ids:
            try:
                products_stmt = select(Product).where(
                    Product.id.in_(ordered_product_ids),
                    Product.is_active == True,
                )
                products_by_id = {p.id: p for p in session.exec(products_stmt).all()}
                products = [products_by_id[pid] for pid in ordered_product_ids if pid in products_by_id]
                if products:
                    from app.product_spec_pdf_service import generate_products_spec_sheets_pdf
                    from pypdf import PdfWriter, PdfReader

                    spec_buffer = generate_products_spec_sheets_pdf(
                        products,
                        company_settings=company_settings,
                        session=session,
                    )
                    writer = PdfWriter()
                    writer.append(PdfReader(buffer))
                    writer.append(PdfReader(spec_buffer))
                    merged = BytesIO()
                    writer.write(merged)
                    merged.seek(0)
                    return merged
            except Exception as e:
                print(f"Could not append product spec sheets: {e}", file=sys.stderr, flush=True)

    buffer.seek(0)
    return buffer
