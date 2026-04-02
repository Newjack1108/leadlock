"""
Service for rendering email templates with customer data.
"""
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Optional, Tuple, Dict
from jinja2 import Template
from app.models import EmailTemplate, Customer


def _customer_dict_for_template(customer: Customer) -> Dict[str, str]:
    return {
        'name': customer.name or '',
        'email': customer.email or '',
        'phone': customer.phone or '',
        'customer_number': customer.customer_number or '',
        'address_line1': customer.address_line1 or '',
        'address_line2': customer.address_line2 or '',
        'city': customer.city or '',
        'county': customer.county or '',
        'postcode': customer.postcode or '',
        'country': customer.country or '',
    }


def render_email_template(
    template: EmailTemplate,
    customer: Customer,
    custom_variables: Optional[Dict] = None
) -> Tuple[str, str]:
    """
    Render email template with customer data.
    Returns (subject, body_html).
    """
    subject_template = Template(template.subject_template)
    body_template = Template(template.body_template)

    context: Dict[str, Any] = {
        'customer': _customer_dict_for_template(customer),
    }

    if custom_variables:
        context.update(custom_variables)

    subject = subject_template.render(**context)
    body_html = body_template.render(**context)

    return subject, body_html


def get_sample_customer_data() -> Dict:
    """Get sample customer data for template preview."""
    return {
        'customer': {
            'name': 'John Doe',
            'email': 'john.doe@example.com',
            'phone': '+44 1234 567890',
            'customer_number': 'CUST-2024-001',
            'address_line1': '123 Sample Street',
            'address_line2': 'Apt 4B',
            'city': 'London',
            'county': 'Greater London',
            'postcode': 'SW1A 1AA',
            'country': 'United Kingdom',
        }
    }


def get_email_template_preview_context(customer: Optional[Customer] = None) -> Dict[str, Any]:
    """
    Full Jinja context for Email Templates preview (Settings → Email Templates).

    Includes sample quote / company / VAT fields so previews match variables often copied from
    quote email templates. Sending mail from Compose still uses render_email_template() with
    only customer data unless custom_variables are added later.
    """
    if customer:
        cust: Dict[str, str] = _customer_dict_for_template(customer)
    else:
        cust = dict(get_sample_customer_data()['customer'])

    sample_quote = SimpleNamespace(
        quote_number='QT-2024-001',
        total_amount=Decimal('1500.00'),
        currency='GBP',
        valid_until=datetime(2026, 6, 15, 12, 0, 0),
        subtotal=Decimal('1500.00'),
        discount_total=Decimal('0.00'),
    )

    return {
        'customer': cust,
        'quote': sample_quote,
        'company_settings': {
            'company_name': 'Sample Company Ltd',
            'trading_name': 'Sample Co',
        },
        'custom_message': 'Thank you for your interest. Please review the quote at your convenience.',
        'currency_symbol': '£',
        'vat_amount': Decimal('300.00'),
        'total_amount_inc_vat': Decimal('1800.00'),
    }
