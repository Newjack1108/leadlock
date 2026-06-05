"""
Service for rendering SMS templates with customer, user, and company data.
"""
from typing import Dict, Optional
from sqlmodel import Session, select
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
    extra_context: Optional[Dict] = None,
) -> str:
    """Render SMS template body with customer, user, and company data."""
    t = Template(template.body_template)
    context: Dict = {}
    context.update(_customer_context(customer))
    context.update(_user_context(user))
    context.update(_company_context(company_settings))
    if extra_context:
        context.update(extra_context)
    return t.render(**context)


def get_sample_sms_context() -> Dict:
    """Get full sample context for SMS template preview (no customer)."""
    context = get_sample_customer_data()
    context["user"] = {"name": "Sample User"}
    context["company"] = {"company_name": "Cheshire Stables", "trading_name": "Cheshire Stables"}
    context["order"] = {"order_number": "ORD-2025-001"}
    context["review"] = {
        "google_url": "https://example.com/google-review",
        "facebook_url": "https://example.com/facebook-review",
        "trustpilot_url": "https://example.com/trustpilot-review",
    }
    return context


def get_duplicate_sms_template(
    session: Session,
    company_settings: Optional[CompanySettings] = None,
) -> Optional[SmsTemplate]:
    """
    Resolve duplicate/repeat-lead SMS template in priority order:
    1) Company setting `duplicate_sms_template_id`
    2) Template named exactly `Duplicate Lead Notice`
    """
    if company_settings and company_settings.duplicate_sms_template_id:
        template = session.get(SmsTemplate, int(company_settings.duplicate_sms_template_id))
        if template:
            return template
    statement = select(SmsTemplate).where(SmsTemplate.name == "Duplicate Lead Notice")
    return session.exec(statement).first()
