"""Shared quote brand / product-line resolution (stables, sheds, cabins)."""
from typing import List, Optional, Sequence

from sqlmodel import Session, select

from app.models import (
    CompanySettings,
    InstallationLeadTime,
    Lead,
    LeadType,
    Product,
    ProductCategory,
    Quote,
    QuoteItem,
)


def resolve_quote_brand_lead_type(
    quote: Quote,
    quote_items: Sequence[QuoteItem],
    session: Optional[Session],
) -> Optional[LeadType]:
    """Product line (stables / sheds / cabins) for branding, lead time, and commission."""
    lead_type: Optional[LeadType] = None
    if session and quote.lead_id:
        lead = session.get(Lead, quote.lead_id)
        if lead and lead.lead_type in (LeadType.STABLES, LeadType.SHEDS, LeadType.CABINS):
            lead_type = lead.lead_type
    if lead_type is None and session:
        product_ids = [item.product_id for item in quote_items if item.product_id]
        if product_ids:
            product_stmt = select(Product).where(Product.id.in_(product_ids))
            products = session.exec(product_stmt).all()
            categories = {p.category for p in products if p and p.category}
            if ProductCategory.CABINS in categories:
                lead_type = LeadType.CABINS
            elif ProductCategory.SHEDS in categories:
                lead_type = LeadType.SHEDS
            elif ProductCategory.STABLES in categories:
                lead_type = LeadType.STABLES
    return lead_type


def installation_lead_time_for_settings(
    company_settings: Optional[CompanySettings],
    lead_type: Optional[LeadType],
) -> Optional[InstallationLeadTime]:
    """Per-type installation lead time, falling back to legacy installation_lead_time."""
    if not company_settings:
        return None
    per_type: Optional[InstallationLeadTime] = None
    if lead_type == LeadType.STABLES:
        per_type = company_settings.installation_lead_time_stables
    elif lead_type == LeadType.SHEDS:
        per_type = company_settings.installation_lead_time_sheds
    elif lead_type == LeadType.CABINS:
        per_type = company_settings.installation_lead_time_cabins
    return per_type or company_settings.installation_lead_time


# Backwards-compatible aliases used by quote_pdf_service and existing tests
def _resolve_quote_brand_lead_type(
    quote: Quote,
    quote_items: List[QuoteItem],
    session: Optional[Session],
) -> Optional[LeadType]:
    return resolve_quote_brand_lead_type(quote, quote_items, session)


def _installation_lead_time_for_settings(
    company_settings: Optional[CompanySettings],
    lead_type: Optional[LeadType],
) -> Optional[InstallationLeadTime]:
    return installation_lead_time_for_settings(company_settings, lead_type)
