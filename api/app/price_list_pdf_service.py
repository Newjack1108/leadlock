"""
Generate branded price list PDFs from catalogue products (ReportLab).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional, Tuple
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sqlmodel import Session, select

from app.constants import VAT_RATE_DECIMAL, VAT_RATE_PERCENT
from app.models import CompanySettings, Product, ProductCategory
from app.product_spec_pdf_service import _make_footer_drawer
from app.quote_pdf_service import (
    _build_header_flowables,
    _resolve_logo,
    format_currency,
)

FOOTER_BOTTOM_MARGIN = 35 * mm


def _trading_name_override_for_products(products: List[Product]) -> Optional[str]:
    """Single product line in the export → same trading names as quote PDF rules."""
    cats = {p.category for p in products if p and p.category}
    if len(cats) != 1:
        return None
    c = next(iter(cats))
    if c == ProductCategory.STABLES:
        return "Cheshire Stables"
    if c == ProductCategory.SHEDS:
        return "Cheshire Sheds"
    if c == ProductCategory.CABINS:
        return "Beaver Log Cabins"
    return None


def _sort_products(products: List[Product]) -> List[Product]:
    return sorted(
        products,
        key=lambda p: (
            p.category.value if p.category else "",
            (p.subcategory or "").casefold(),
            p.name.casefold(),
        ),
    )


def _group_key(p: Product) -> Tuple[str, str]:
    cat = p.category.value if p.category else ""
    sub = (p.subcategory or "").strip() or "—"
    return (cat, sub)


def _price_inc_vat(base_ex_vat: Decimal) -> Decimal:
    return (base_ex_vat * (Decimal("1") + VAT_RATE_DECIMAL)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def generate_price_list_pdf(
    products: List[Product],
    company_settings: Optional[CompanySettings] = None,
    session: Optional[Session] = None,
    filter_summary: str = "",
) -> BytesIO:
    """
    Build a price list PDF with company header/logo and footer.

    Args:
        products: Pre-filtered product rows (caller applies category / subcategory / etc.).
        company_settings: Optional; loaded from session if omitted and session given.
        session: Used to load CompanySettings when not passed explicitly.
        filter_summary: Human-readable description of active filters (subtitle).
    """
    if not company_settings and session:
        company_settings = session.exec(select(CompanySettings).limit(1)).first()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=10 * mm,
        bottomMargin=FOOTER_BOTTOM_MARGIN,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    brand_color = colors.HexColor("#0e4a38")
    title_style = ParagraphStyle(
        "PriceListTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=brand_color,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "PriceListHeading",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=brand_color,
        spaceAfter=4,
        spaceBefore=8,
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "PriceListNormal",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#333333"),
    )
    muted_style = ParagraphStyle(
        "PriceListMuted",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )
    company_name_style = ParagraphStyle(
        "PriceListCompany",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=brand_color,
        spaceAfter=2,
        fontName="Helvetica-Bold",
    )
    cell_style = ParagraphStyle(
        "PriceListCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333"),
    )
    cell_style_right = ParagraphStyle(
        "PriceListCellRight",
        parent=cell_style,
        alignment=TA_RIGHT,
    )
    header_cell_style = ParagraphStyle(
        "PriceListHeaderCell",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=brand_color,
    )
    header_cell_style_right = ParagraphStyle(
        "PriceListHeaderCellRight",
        parent=header_cell_style,
        alignment=TA_RIGHT,
    )

    elements: List[Any] = []
    logo_path: Optional[str] = None
    logo_bytes: Optional[bytes] = None
    trading_override = _trading_name_override_for_products(products)

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
                trading_name_override=trading_override,
            )
        )
        elements.append(Spacer(1, 6))

    elements.append(Paragraph("<b>Price list</b>", title_style))
    elements.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y')}",
            muted_style,
        )
    )
    if filter_summary.strip():
        elements.append(Paragraph(escape(filter_summary.strip()), muted_style))
    elements.append(Spacer(1, 4))
    elements.append(
        Paragraph(
            f"Ex VAT column excludes VAT; inc VAT includes VAT at {VAT_RATE_PERCENT}%.",
            muted_style,
        )
    )
    elements.append(Spacer(1, 10))

    sorted_products = _sort_products(products)
    if not sorted_products:
        elements.append(
            Paragraph("<i>No products match the selected filters.</i>", normal_style)
        )
    else:
        groups: dict[Tuple[str, str], List[Product]] = defaultdict(list)
        for p in sorted_products:
            groups[_group_key(p)].append(p)

        col_widths = [108 * mm, 36 * mm, 36 * mm]
        header_row = [
            Paragraph("<b>Product</b>", header_cell_style),
            Paragraph("<b>Ex VAT</b>", header_cell_style_right),
            Paragraph("<b>Inc VAT</b>", header_cell_style_right),
        ]

        for (cat_val, sub_val) in sorted(groups.keys()):
            section_products = groups[(cat_val, sub_val)]
            label = f"{cat_val}"
            if sub_val and sub_val != "—":
                label = f"{cat_val} — {sub_val}"
            elements.append(Paragraph(f"<b>{escape(label)}</b>", heading_style))

            data: List[List[Any]] = [header_row]
            for p in section_products:
                inc = _price_inc_vat(p.base_price)
                data.append(
                    [
                        Paragraph(escape(p.name or ""), cell_style),
                        Paragraph(
                            escape(format_currency(p.base_price, "GBP")),
                            cell_style_right,
                        ),
                        Paragraph(
                            escape(format_currency(inc, "GBP")),
                            cell_style_right,
                        ),
                    ]
                )

            table = Table(data, colWidths=col_widths, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0ec")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), brand_color),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            elements.append(table)
            elements.append(Spacer(1, 8))

    footer_drawer = _make_footer_drawer(company_settings) if company_settings else None
    if footer_drawer:
        doc.build(elements, onFirstPage=footer_drawer, onLaterPages=footer_drawer)
    else:
        doc.build(elements)

    buffer.seek(0)
    return buffer
