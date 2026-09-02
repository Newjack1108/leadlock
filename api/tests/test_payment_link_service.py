"""Payment link URL helpers."""
from app.models import CompanySettings
from app.payment_link_service import (
    DEFAULT_PAYPAL_PAYMENT_LINK,
    company_default_payment_url,
    resolve_payment_url,
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


def test_resolve_payment_url_prefers_requested_then_saved_then_company_then_paypal():
    custom = "https://pay.example.com/custom"
    saved = "https://pay.example.com/saved"
    company = "https://pay.example.com/company"
    settings = CompanySettings(
        company_name="Test Co",
        default_payment_link_url=company,
        updated_by_id=1,
    )
    assert resolve_payment_url(custom, saved, settings) == custom
    assert resolve_payment_url("  ", saved, settings) == saved
    assert resolve_payment_url(None, None, settings) == company
    assert resolve_payment_url(None, None, None) == DEFAULT_PAYPAL_PAYMENT_LINK
    assert resolve_payment_url(None, None, CompanySettings(company_name="Test Co", updated_by_id=1)) == (
        DEFAULT_PAYPAL_PAYMENT_LINK
    )
