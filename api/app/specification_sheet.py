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


def resolve_specification_sheet_image_url(
    company_settings: Optional["CompanySettings"],
) -> str:
    if company_settings is None:
        return ""
    return (getattr(company_settings, "default_specification_sheet_url", None) or "").strip()


def has_specification_sheet_content(
    quote: "Quote",
    company_settings: Optional["CompanySettings"],
) -> bool:
    return bool(resolve_specification_sheet_text(quote, company_settings)) or bool(
        resolve_specification_sheet_image_url(company_settings)
    )


def is_specification_sheet_pdf_url(url: str) -> bool:
    path = (url or "").strip().lower().split("?")[0]
    return path.endswith(".pdf")


def fetch_specification_sheet_file_bytes(url: str) -> Optional[bytes]:
    """Fetch specification sheet file bytes from a URL or local static path."""
    url = (url or "").strip()
    if not url:
        return None

    if url.startswith("/static/"):
        from pathlib import Path

        static_path = Path(__file__).parent.parent / url.lstrip("/")
        if static_path.is_file():
            return static_path.read_bytes()
        return None

    if not url.startswith(("http://", "https://")):
        return None

    import urllib.request

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LeadLock-API/1.0 (Specification Sheet)"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read()
        return data if data else None
    except Exception:
        return None
