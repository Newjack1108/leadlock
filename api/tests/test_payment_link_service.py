"""Payment link URL helpers."""
from app.models import CompanySettings
from app.payment_link_service import (
    DEFAULT_PAYPAL_PAYMENT_LINK,
    company_default_payment_url,
    validate_payment_url,
)


def test_validate_paypal_payment_url():
    assert validate_payment_url(DEFAULT_PAYPAL_PAYMENT_LINK) == DEFAULT_PAYPAL_PAYMENT_LINK


def test_company_default_payment_url_empty_when_unset():
    settings = CompanySettings(company_name="Test Co", updated_by_id=1)
    assert company_default_payment_url(settings) == ""
    assert company_default_payment_url(None) == ""


def test_company_default_payment_url_uses_paypal():
    settings = CompanySettings(
        company_name="Test Co",
        default_payment_link_url=f"  {DEFAULT_PAYPAL_PAYMENT_LINK}  ",
        updated_by_id=1,
    )
    assert company_default_payment_url(settings) == DEFAULT_PAYPAL_PAYMENT_LINK
