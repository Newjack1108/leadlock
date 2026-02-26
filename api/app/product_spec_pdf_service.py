"""
Service for generating product spec sheet PDF documents.
Used to attach product specifications to quotes (description, specs, size, height, floor plan, price).
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
from typing import Optional, List, Any
from io import BytesIO
from decimal import Decimal
from app.models import Product, CompanySettings
from sqlmodel import Session, select
import os
import sys
import tempfile
import urllib.request

# Reuse helpers from quote PDF service
from app.quote_pdf_service import (
    format_currency,
    _image_from_bytes,
    _build_header_flowables,
    _resolve_logo,
    _force_cloudinary_format,
    _ensure_png_or_jpeg_bytes,
)

FOOTER_BOTTOM_MARGIN = 35 * mm


def _fetch_image_from_url(url: str) -> Optional[bytes]:
    """Fetch image bytes from URL. Converts WebP to PNG if needed."""
    if not url or not url.strip().startswith(("http://", "https://")):
        return None
    url = url.strip()
    JPEG_MAGIC = b"\xff\xd8\xff"
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    urls_to_try = (
        [_force_cloudinary_format(url, "png"), url]
        if "res.cloudinary.com" in url
        else [url]
    )
    for fetch_url in urls_to_try:
        try:
            req = urllib.request.Request(
                fetch_url,
                headers={"User-Agent": "LeadLock-API/1.0 (Product Spec PDF)"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = response.read()
            if not data or len(data) < 50:
                continue
            if data.startswith(JPEG_MAGIC) or data.startswith(PNG_MAGIC):
                return data
            converted = _ensure_png_or_jpeg_bytes(data)
            if converted:
                return converted
        except Exception:
            continue
    return None


def _make_footer_drawer(company_settings: CompanySettings) -> Any:
    """Return canvas drawer for footer. Simplified version from quote_pdf_service."""
    from reportlab.lib.styles import ParagraphStyle

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
    if company_settings.phone or company_settings.email:
        contact = []
        if company_settings.phone:
            contact.append(f"Tel: {company_settings.phone}")
        if company_settings.email:
            contact.append(f"Email: {company_settings.email}")
        footer_lines.append(" | ".join(contact))

    styles = getSampleStyleSheet()
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        alignment=1,
    )
    footer_text = "<br/>".join(footer_lines) if footer_lines else ""
    footer_para = Paragraph(footer_text, footer_style) if footer_text else None

    def drawer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        y = 5 * mm
        if footer_para:
            try:
                pw, ph = footer_para.wrap(doc.width, 20 * mm)
                footer_para.drawOn(canvas, doc.leftMargin, y)
            except Exception:
                pass
        canvas.restoreState()

    return drawer


def _build_product_spec_flowables(
    product: Product,
    brand_color: Any,
    heading_style: ParagraphStyle,
    normal_style: ParagraphStyle,
) -> List[Any]:
    """Build flowables for a single product spec sheet."""
    elements: List[Any] = []

    # Product name
    elements.append(Paragraph(f"<b>{product.name}</b>", heading_style))
    elements.append(Spacer(1, 4))

    # Two-column layout: image left, details right
    left_col: List[Any] = []
    right_col: List[Any] = []

    # Product image or floor plan
    img_flowable = None
    if product.image_url:
        img_data = _fetch_image_from_url(product.image_url)
        if img_data:
            img_flowable = _image_from_bytes(img_data, width=70 * mm, max_height=50 * mm)

    if img_flowable:
        left_col.append(img_flowable)
        left_col.append(Spacer(1, 4))

    # Details
    detail_lines = []
    if product.description:
        detail_lines.append(Paragraph(product.description, normal_style))
    if product.size:
        detail_lines.append(Paragraph(f"<b>Size:</b> {product.size}", normal_style))
    if product.height:
        detail_lines.append(Paragraph(f"<b>Height:</b> {product.height}", normal_style))
    if product.width is not None or product.length is not None:
        dims = []
        if product.width is not None:
            dims.append(f"{product.width}m")
        if product.length is not None:
            dims.append(f"{product.length}m")
        if dims:
            detail_lines.append(Paragraph(f"<b>Dimensions (W x L):</b> {' x '.join(dims)}", normal_style))
    detail_lines.append(Paragraph(f"<b>Price:</b> {format_currency(product.base_price, 'GBP')} (Ex VAT)", normal_style))
    detail_lines.append(Paragraph(f"<b>Unit:</b> {product.unit}", normal_style))

    for line in detail_lines:
        right_col.append(line)
        right_col.append(Spacer(1, 2))

    # Build table: left column (image) | right column (details)
    left_content = left_col if left_col else [Paragraph("<i>No image</i>", normal_style)]
    right_content = right_col if right_col else [Spacer(1, 1)]
    layout_table = Table(
        [[left_content, right_content]],
        colWidths=[75 * mm, 105 * mm],
    )
    layout_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(layout_table)
    elements.append(Spacer(1, 6))

    # Specifications
    if product.specifications and product.specifications.strip():
        elements.append(Paragraph("<b>Technical Specifications</b>", heading_style))
        elements.append(Spacer(1, 2))
        for line in product.specifications.strip().split("\n"):
            if line.strip():
                elements.append(Paragraph(line.strip(), normal_style))
        elements.append(Spacer(1, 6))

    # Floor plan (if different from main image)
    if product.floor_plan_url and product.floor_plan_url != product.image_url:
        elements.append(Paragraph("<b>Floor Plan</b>", heading_style))
        elements.append(Spacer(1, 2))
        fp_data = _fetch_image_from_url(product.floor_plan_url)
        if fp_data:
            fp_img = _image_from_bytes(fp_data, width=140 * mm, max_height=80 * mm)
            if fp_img:
                elements.append(fp_img)
        else:
            elements.append(Paragraph("<i>Floor plan image unavailable</i>", normal_style))

    return elements


def generate_product_spec_pdf(
    product: Product,
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
) -> BytesIO:
    """
    Generate a PDF spec sheet for a single product.

    Returns:
        BytesIO buffer containing PDF data
    """
    return generate_products_spec_sheets_pdf(
        [product],
        company_settings=company_settings,
        session=session,
    )


def generate_products_spec_sheets_pdf(
    products: List[Product],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
) -> BytesIO:
    """
    Generate a combined PDF with spec sheets for multiple products.
    One page per product (or more if content overflows).

    Args:
        products: List of Product objects
        company_settings: Optional CompanySettings for header
        session: Optional database session to fetch company settings

    Returns:
        BytesIO buffer containing PDF data
    """
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

    elements: List[Any] = []
    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0b3d2e")
    heading_style = ParagraphStyle(
        "SpecHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=brand_color,
        spaceAfter=3,
        spaceBefore=6,
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "SpecNormal",
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

    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    if company_settings:
        logo_path, logo_bytes = _resolve_logo(company_settings)
        elements.extend(
            _build_header_flowables(
                company_settings,
                logo_path,
                logo_bytes,
                normal_style,
                company_name_style,
                customer_number=None,
            )
        )
        elements.append(Spacer(1, 4))

    # Title
    elements.append(Paragraph("<b>Product Specifications</b>", heading_style))
    elements.append(Spacer(1, 8))

    for i, product in enumerate(products):
        if i > 0:
            elements.append(PageBreak())
            if company_settings:
                elements.extend(
                    _build_header_flowables(
                        company_settings,
                        logo_path,
                        logo_bytes,
                        normal_style,
                        company_name_style,
                        customer_number=None,
                    )
                )
                elements.append(Spacer(1, 4))

        product_flowables = _build_product_spec_flowables(
            product,
            brand_color,
            heading_style,
            normal_style,
        )
        elements.extend(product_flowables)

    footer_drawer = _make_footer_drawer(company_settings) if company_settings else None
    if footer_drawer:
        doc.build(elements, onFirstPage=footer_drawer, onLaterPages=footer_drawer)
    else:
        doc.build(elements)

    buffer.seek(0)
    return buffer
