"""
Service for rendering email templates with customer data.
"""
from typing import Optional, Tuple, Dict
from jinja2 import Template
from app.models import EmailTemplate, Customer


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
    
    # Build context with customer data
    context = {
        'customer': {
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
    }
    
    # Add custom variables if provided
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
