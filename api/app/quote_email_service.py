"""
Service for sending quote emails (online view link; optional file attachments).
"""
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime
from jinja2 import Template
from sqlmodel import Session, select
from app.models import Quote, QuoteTemplate, Customer, CompanySettings, Order
from app.customer_view_links import customer_view_path_segment
from app.email_service import send_email, EMAIL_TRACKED_LINK_STYLE
from app.constants import VAT_RATE_DECIMAL
from decimal import Decimal


def get_sample_quote_preview_data() -> Dict[str, Any]:
    """Get sample quote, customer, company data for template preview."""
    # Use simple objects for template rendering (Jinja2 accesses attributes)
    class SampleQuote:
        quote_number = "QT-2024-001"
        total_amount = Decimal("1500.00")
        currency = "GBP"
        valid_until = datetime(2025, 3, 15, 12, 0, 0)

    class SampleCustomer:
        name = "John Doe"
        email = "john.doe@example.com"
        phone = "+44 1234 567890"

    class SampleCompany:
        company_name = "LeadLock CRM"

    currency_symbol = "£"
    vat_amount = Decimal("300.00")
    total_amount_inc_vat = Decimal("1800.00")

    return {
        "quote": SampleQuote(),
        "customer": SampleCustomer(),
        "company_settings": SampleCompany(),
        "custom_message": "Thank you for your interest. Please review the quote at your convenience.",
        "currency_symbol": currency_symbol,
        "vat_amount": vat_amount,
        "total_amount_inc_vat": total_amount_inc_vat,
    }


def render_email_template(
    template: Template,
    quote: Quote,
    customer: Customer,
    company_settings: Optional[CompanySettings] = None,
    custom_message: Optional[str] = None
) -> str:
    """Render email template with quote data."""
    currency_symbol = "£" if quote.currency == "GBP" else quote.currency + " "
    vat_amount = (quote.total_amount or Decimal(0)) * VAT_RATE_DECIMAL
    total_amount_inc_vat = (quote.total_amount or Decimal(0)) + vat_amount

    return template.render(
        quote=quote,
        customer=customer,
        company_settings=company_settings,
        custom_message=custom_message,
        currency_symbol=currency_symbol,
        vat_amount=vat_amount,
        total_amount_inc_vat=total_amount_inc_vat
    )


def send_quote_email(
    quote: Quote,
    customer: Customer,
    to_email: str,
    session: Session,
    template_id: int,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    custom_message: Optional[str] = None,
    user_id: Optional[int] = None,
    view_token: Optional[str] = None,
    frontend_base_url: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[str], Optional[str], None, Optional[str], Optional[str]]:
    """
    Send a quote email with a tracked "View your quote online" link and optional file attachments.
    Customer opens the tracked view and can Print or Download PDF from there.
    
    Args:
        quote: Quote object
        customer: Customer object
        to_email: Recipient email address
        session: Database session
        template_id: QuoteTemplate ID (must exist)
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        custom_message: Optional custom message to append
        user_id: Optional user ID for email sending
        view_token: Token for public quote view link
        frontend_base_url: Base URL for view link
        attachments: Optional list of dicts with keys filename (str) and content (bytes)

    Returns:
        Tuple of (success, message_id, error_message, None, subject, body_html)
    """
    try:
        # Get company settings
        statement = select(CompanySettings).limit(1)
        company_settings = session.exec(statement).first()
        
        statement = select(QuoteTemplate).where(QuoteTemplate.id == template_id)
        quote_template = session.exec(statement).first()
        if not quote_template:
            return False, None, "Quote template not found", None, None, None

        subject_template = Template(quote_template.email_subject_template)
        body_template = Template(quote_template.email_body_template)
        
        # Render email templates
        subject = render_email_template(subject_template, quote, customer, company_settings, custom_message)
        body_html = render_email_template(body_template, quote, customer, company_settings, custom_message)

        has_order = session.exec(select(Order).where(Order.quote_id == quote.id)).first() is not None
        link_label = "View your order online" if has_order else "View your quote online"
        header_tagline = "Your order" if has_order else "Your quotation"

        # Append tracked view link (URL-based open tracking)
        if view_token and frontend_base_url:
            base = frontend_base_url.rstrip("/")
            path_seg = customer_view_path_segment(session, quote.id, view_token)
            link_style = EMAIL_TRACKED_LINK_STYLE
            view_link = f'<p style="margin-top:1.5em;"><a href="{base}/{path_seg}" style="{link_style}">{link_label}</a></p>'
            body_html = (body_html or "") + view_link

        success, message_id, error = send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments if attachments else None,
            user_id=user_id,
            customer_number=customer.customer_number,
            header_tagline=header_tagline,
            include_quote_highlight=True,
        )

        if success:
            return True, message_id, None, None, subject, body_html
        else:
            return False, None, error, None, subject, body_html

    except Exception as e:
        return False, None, str(e), None, None, None
