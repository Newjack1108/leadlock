"""Standard specification sheet inclusion and text resolution for quotes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models import CompanySettings, Quote, QuoteEmail


def should_include_specification_sheet(
    quote: "Quote",
    quote_email: Optional["QuoteEmail"] = None,
) -> bool:
    if quote_email is not None and getattr(quote_email, "include_specification_sheet", False):
        return True
    return getattr(quote, "include_specification_sheet", False)


def resolve_specification_sheet_text(
    quote: "Quote",
    company_settings: Optional["CompanySettings"],
) -> str:
    quote_text = (getattr(quote, "specification_sheet", None) or "").strip()
    if quote_text:
        return quote_text
    if company_settings is None:
        return ""
    return (getattr(company_settings, "default_specification_sheet", None) or "").strip()
