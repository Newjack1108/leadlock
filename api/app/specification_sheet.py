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
    """Heuristic that a URL likely refers to a PDF (used for fetch fallbacks only)."""
    path = (url or "").strip().lower().split("?")[0]
    if path.endswith(".pdf"):
        return True
    lower = (url or "").strip().lower()
    return "/raw/upload/" in lower


def _cloudinary_fetch_urls(url: str) -> list[str]:
    url = url.strip()
    urls = [url]
    if "res.cloudinary.com" not in url:
        return urls
    if "/image/upload/" in url:
        urls.append(url.replace("/image/upload/", "/raw/upload/", 1))
    elif "/raw/upload/" in url:
        urls.append(url.replace("/raw/upload/", "/image/upload/", 1))
    return list(dict.fromkeys(urls))


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

    likely_pdf = is_specification_sheet_pdf_url(url)
    urls_to_try = _cloudinary_fetch_urls(url) if "res.cloudinary.com" in url else [url]
    for fetch_url in urls_to_try:
        data = _fetch_http_bytes(fetch_url)
        if not data:
            continue
        if data.startswith(b"%PDF-"):
            return data
        if not likely_pdf:
            return data
    return None


def _fetch_http_bytes(url: str) -> Optional[bytes]:
    try:
        import httpx

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                url,
                headers={"User-Agent": "LeadLock-API/1.0 (Specification Sheet)"},
            )
            response.raise_for_status()
            return response.content or None
    except Exception:
        pass

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
