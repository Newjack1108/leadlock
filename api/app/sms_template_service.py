"""
Service for rendering SMS templates with customer data.
"""
from typing import Dict
from jinja2 import Template
from app.models import SmsTemplate, Customer
from app.email_template_service import get_sample_customer_data


def _customer_context(customer: Customer) -> Dict:
    return {
        "customer": {
            "name": customer.name or "",
            "email": customer.email or "",
            "phone": customer.phone or "",
            "customer_number": customer.customer_number or "",
            "address_line1": customer.address_line1 or "",
            "address_line2": customer.address_line2 or "",
            "city": customer.city or "",
            "county": customer.county or "",
            "postcode": customer.postcode or "",
            "country": customer.country or "",
        }
    }


def render_sms_template(template: SmsTemplate, customer: Customer) -> str:
    """Render SMS template body with customer data."""
    t = Template(template.body_template)
    context = _customer_context(customer)
    return t.render(**context)
