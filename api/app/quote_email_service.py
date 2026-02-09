"""
Service for sending quote emails (link only; customer downloads/prints from tracked view).
"""
from typing import Optional, Tuple
from jinja2 import Template
from sqlmodel import Session, select
from app.models import Quote, QuoteTemplate, Customer, CompanySettings
from app.email_service import send_email
from app.constants import VAT_RATE_DECIMAL
from decimal import Decimal


def get_default_email_template() -> Tuple[str, str]:
    """Get default email subject and body templates."""
    subject = "Quote {{ quote.quote_number }}"
    body = """
    <p>Dear {{ customer.name }},</p>
    
    <p>Please view your quote {{ quote.quote_number }} using the link below.</p>
    
    <p>Quote Summary (all prices Ex VAT @ 20%):</p>
    <ul>
        <li>Total (Ex VAT): {{ currency_symbol }}{{ quote.total_amount|round(2) }}</li>
        <li>VAT @ 20%: {{ currency_symbol }}{{ vat_amount|round(2) }}</li>
        <li>Total (inc VAT): {{ currency_symbol }}{{ total_amount_inc_vat|round(2) }}</li>
        <li>Valid Until: {{ quote.valid_until.strftime('%d %B %Y') if quote.valid_until else 'N/A' }}</li>
    </ul>
    
    {% if custom_message %}
    <p>{{ custom_message }}</p>
    {% endif %}
    
    <p>If you have any questions, please don't hesitate to contact us.</p>
    
    <p>Best regards,<br>
    {{ company_settings.company_name if company_settings else 'LeadLock CRM' }}</p>
    """
    return subject, body


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
    template_id: Optional[int] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    custom_message: Optional[str] = None,
    user_id: Optional[int] = None,
    view_token: Optional[str] = None,
    frontend_base_url: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str], None, Optional[str], Optional[str]]:
    """
    Send a quote as an email with "View your quote online" link only (no PDF attachment).
    Customer opens the tracked view and can Print or Download PDF from there.
    
    Args:
        quote: Quote object
        customer: Customer object
        to_email: Recipient email address
        session: Database session
        template_id: Optional QuoteTemplate ID
        cc: Optional CC recipients
        bcc: Optional BCC recipients
        custom_message: Optional custom message to append
        user_id: Optional user ID for email sending
        view_token: Token for public quote view link
        frontend_base_url: Base URL for view link
    
    Returns:
        Tuple of (success, message_id, error_message, None, subject, body_html)
    """
    try:
        # Get company settings
        statement = select(CompanySettings).limit(1)
        company_settings = session.exec(statement).first()
        
        # Get email template
        if template_id:
            statement = select(QuoteTemplate).where(QuoteTemplate.id == template_id)
            quote_template = session.exec(statement).first()
            if quote_template:
                subject_template = Template(quote_template.email_subject_template)
                body_template = Template(quote_template.email_body_template)
            else:
                # Fallback to default
                subject_template = Template(get_default_email_template()[0])
                body_template = Template(get_default_email_template()[1])
        else:
            # Use default template
            subject_template = Template(get_default_email_template()[0])
            body_template = Template(get_default_email_template()[1])
        
        # Render email templates
        subject = render_email_template(subject_template, quote, customer, company_settings, custom_message)
        body_html = render_email_template(body_template, quote, customer, company_settings, custom_message)

        # Append "View your quote online" link for open tracking (URL-based)
        if view_token and frontend_base_url:
            base = frontend_base_url.rstrip("/")
            view_link = f'<p style="margin-top:1.5em;"><a href="{base}/quotes/view/{view_token}" style="font-weight:bold;">View your quote online</a></p>'
            body_html = (body_html or "") + view_link

        # Send email (no PDF attachment; customer uses Print/Download PDF on the tracked view)
        success, message_id, error = send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=None,
            user_id=user_id
        )

        if success:
            return True, message_id, None, None, subject, body_html
        else:
            return False, None, error, None, subject, body_html

    except Exception as e:
        return False, None, str(e), None, None, None
