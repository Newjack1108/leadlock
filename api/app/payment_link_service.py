"""Validation and template context for external payment links."""
import html
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from app.models import CompanySettings, Order, Quote

MAX_PAYMENT_URL_LENGTH = 2048
DEFAULT_PAYPAL_PAYMENT_LINK = "https://www.paypal.com/ncp/payment/HM6Y7ZSG5SYQ6"
PAYPAL_PAYMENT_HOST = "www.paypal.com"
PAYPAL_PAYMENT_PATH = "/ncp/payment/HM6Y7ZSG5SYQ6"
TRUST_PAYMENT_LINK_HOST = "paybylink.trustpayments.com"

_TRAILING_URL_PUNCTUATION = ".,;:)>]}\"'`"
_MESSAGE_URL_RE = re.compile(
    r"(?i)(?:https?://[^\s<>\"']+"
    r"|www\.[^\s<>\"']+"
    r"|(?:paybylink\.trustpayments\.com|paypal\.com)/[^\s<>\"']+)"
)
_PAYMENT_URL_ERROR = (
    "Payment URL must be the company PayPal page or a Trust Payments card link "
    "(https://paybylink.trustpayments.com/)"
)


def validate_payment_url(url: str) -> str:
    """Return the canonical payment URL, or raise ValueError.

    Allowed: the company PayPal page, or a Trust Payments pay-by-link with a code.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Payment URL is required")
    if len(cleaned) > MAX_PAYMENT_URL_LENGTH:
        raise ValueError("Payment URL is too long")
    if cleaned.lower().startswith("www.") or cleaned.lower().startswith("paybylink.") or cleaned.lower().startswith("paypal.com/"):
        cleaned = "https://" + cleaned
    if "\\" in cleaned or "@" in cleaned:
        raise ValueError(_PAYMENT_URL_ERROR)
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() != "https":
        raise ValueError("Payment URL must use https://")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError(_PAYMENT_URL_ERROR)
    paypal = _canonical_paypal(parsed)
    if paypal:
        return paypal
    trust = _canonical_trust(parsed, cleaned)
    if trust:
        return trust
    raise ValueError(_PAYMENT_URL_ERROR)


def validate_company_paypal_url(url: Optional[str]) -> Optional[str]:
    """Company settings may store only the company PayPal page."""
    if url is None:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    try:
        canonical = validate_payment_url(cleaned)
    except ValueError as exc:
        raise ValueError("Company payment link must be the company PayPal page") from exc
    if canonical != DEFAULT_PAYPAL_PAYMENT_LINK:
        raise ValueError("Company payment link must be the company PayPal page")
    return canonical


def extract_message_urls(message: str) -> List[str]:
    """Web addresses in a payment SMS or email, before the signature is added."""
    text = html.unescape(message or "")
    found: List[str] = []
    for match in _MESSAGE_URL_RE.findall(text):
        candidate = match.rstrip(_TRAILING_URL_PUNCTUATION)
        lowered = candidate.lower()
        if not lowered.startswith("http://") and not lowered.startswith("https://"):
            candidate = "https://" + candidate
        found.append(candidate)
    return found


def assert_payment_message_links(message: str, payment_url: str) -> None:
    """The customer message may contain the approved payment link and no other address."""
    expected = validate_payment_url(payment_url)
    found = extract_message_urls(message)
    if not found:
        raise ValueError("The message must include the payment link")
    for raw in found:
        try:
            canonical = validate_payment_url(raw)
        except ValueError as exc:
            raise ValueError(
                "The message can only include the company PayPal page or a Trust Payments card link"
            ) from exc
        if canonical != expected:
            raise ValueError("The message can only include the payment link you are sending")


def _canonical_paypal(parsed) -> Optional[str]:
    host = (parsed.hostname or "").rstrip(".").lower()
    if host != PAYPAL_PAYMENT_HOST:
        return None
    if parsed.query or parsed.fragment:
        return None
    path = (parsed.path or "").rstrip("/")
    if path != PAYPAL_PAYMENT_PATH:
        return None
    return DEFAULT_PAYPAL_PAYMENT_LINK


def _canonical_trust(parsed, raw: str) -> Optional[str]:
    host = (parsed.hostname or "").rstrip(".").lower()
    if host != TRUST_PAYMENT_LINK_HOST:
        return None
    if parsed.fragment or ".." in (parsed.path or ""):
        return None
    if raw.lower().count("https://") != 1 or "http://" in raw.lower():
        return None
    path = parsed.path or ""
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    if path in ("", "/"):
        return None
    return urlunparse(("https", TRUST_PAYMENT_LINK_HOST, path, "", parsed.query, ""))


def company_default_payment_url(company_settings: Optional[CompanySettings]) -> str:
    """Company PayPal/pay-by-link URL, if configured."""
    if company_settings is None:
        return ""
    return (getattr(company_settings, "default_payment_link_url", None) or "").strip()


def resolve_payment_url(
    requested: Optional[str],
    saved: Optional[str],
    company_settings: Optional[CompanySettings] = None,
) -> str:
    """Requested URL, else saved on the order/quote. Does not invent a default.

    company_settings is accepted for call-site compatibility but is not used.
    """
    _ = company_settings
    return (requested or "").strip() or (saved or "").strip()


def payment_link_template_context(order: Order, payment_url: str) -> Dict:
    """Jinja context for payment-link SMS/email templates."""
    return {
        "payment_link": payment_url,
        "order": {
            "order_number": order.order_number or "",
            "deposit_amount": str(order.deposit_amount),
            "balance_amount": str(order.balance_amount),
            "total_amount": str(order.total_amount),
        },
    }


def default_payment_sms_body(order: Order, payment_url: str) -> str:
    return f"Pay online for order {order.order_number}: {payment_url}"


def default_payment_email_subject(order: Order) -> str:
    return f"Payment for order {order.order_number}"


def default_payment_email_html(order: Order, payment_url: str) -> str:
    return (
        f"<p>Please pay online for order {order.order_number}:</p>"
        f'<p><a href="{payment_url}">{payment_url}</a></p>'
    )


def quote_payment_link_template_context(quote: Quote, payment_url: str) -> Dict:
    """Jinja context for payment-link SMS/email templates on quotes."""
    amounts = {
        "deposit_amount": str(quote.deposit_amount),
        "balance_amount": str(quote.balance_amount),
        "total_amount": str(quote.total_amount),
    }
    return {
        "payment_link": payment_url,
        "quote": {
            "quote_number": quote.quote_number or "",
            **amounts,
        },
        # Reuse order payment templates that reference {{ order.* }} at quote stage.
        "order": {
            "order_number": quote.quote_number or "",
            **amounts,
        },
    }


def default_quote_payment_sms_body(quote: Quote, payment_url: str) -> str:
    return f"Pay deposit for quote {quote.quote_number}: {payment_url}"


def default_quote_payment_email_subject(quote: Quote) -> str:
    return f"Payment for quote {quote.quote_number}"


def default_quote_payment_email_html(quote: Quote, payment_url: str) -> str:
    return (
        f"<p>Please pay your deposit for quote {quote.quote_number}:</p>"
        f'<p><a href="{payment_url}">{payment_url}</a></p>'
    )
