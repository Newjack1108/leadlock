"""Validation and template context for external payment links."""
from typing import Dict
from urllib.parse import urlparse

from app.models import Order, Quote

MAX_PAYMENT_URL_LENGTH = 2048


def validate_payment_url(url: str) -> str:
    """Return stripped https URL or raise ValueError."""
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Payment URL is required")
    if len(cleaned) > MAX_PAYMENT_URL_LENGTH:
        raise ValueError("Payment URL is too long")
    parsed = urlparse(cleaned)
    if parsed.scheme != "https":
        raise ValueError("Payment URL must use https://")
    if not parsed.netloc:
        raise ValueError("Payment URL is not valid")
    return cleaned


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
