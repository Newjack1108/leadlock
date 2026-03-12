"""
Service for rendering SMS templates with customer, user, and company data.
"""
from typing import Dict, Optional
from jinja2 import Template
from app.models import SmsTemplate, Customer, User, CompanySettings
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


def _user_context(user: Optional[User]) -> Dict:
    if not user:
        return {"user": {"name": ""}}
    return {"user": {"name": user.full_name or ""}}


def _company_context(company_settings: Optional[CompanySettings]) -> Dict:
    if not company_settings:
        return {"company": {"company_name": "", "trading_name": ""}}
    return {
        "company": {
            "company_name": company_settings.company_name or "",
            "trading_name": company_settings.trading_name or "",
        }
    }


def render_sms_template(
    template: SmsTemplate,
    customer: Customer,
    user: Optional[User] = None,
    company_settings: Optional[CompanySettings] = None,
) -> str:
    """Render SMS template body with customer, user, and company data."""
    t = Template(template.body_template)
    context: Dict = {}
    context.update(_customer_context(customer))
    context.update(_user_context(user))
    context.update(_company_context(company_settings))
    return t.render(**context)


def get_sample_sms_context() -> Dict:
    """Get full sample context for SMS template preview (no customer)."""
    context = get_sample_customer_data()
    context["user"] = {"name": "Sample User"}
    context["company"] = {"company_name": "Cheshire Stables", "trading_name": "Cheshire Stables"}
    return context
