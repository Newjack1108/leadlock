"""Payment link URL helpers."""
from types import SimpleNamespace

import pytest

from app.models import CompanySettings
from app.payment_link_service import (
    DEFAULT_PAYPAL_PAYMENT_LINK,
    assert_payment_message_links,
    company_default_payment_url,
    default_payment_email_html,
    default_payment_sms_body,
    resolve_payment_url,
    validate_company_paypal_url,
    validate_payment_url,
)

TRUST_LINK = "https://paybylink.trustpayments.com/order-123"


def test_validate_paypal_payment_url():
    assert validate_payment_url(DEFAULT_PAYPAL_PAYMENT_LINK) == DEFAULT_PAYPAL_PAYMENT_LINK
    assert validate_payment_url(DEFAULT_PAYPAL_PAYMENT_LINK + "/") == DEFAULT_PAYPAL_PAYMENT_LINK


def test_validate_trust_payment_url():
    assert validate_payment_url(TRUST_LINK) == TRUST_LINK
    assert (
        validate_payment_url("https://paybylink.trustpayments.com/order-123/")
        == TRUST_LINK
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://pay.example.com/custom",
        "https://www.paypal.com/ncp/payment/OTHER",
        "https://paypal.com.evil.com/ncp/payment/HM6Y7ZSG5SYQ6",
        "https://paybylink.trustpayments.com",
        "https://paybylink.trustpayments.com/",
        "https://paybylink.trustpayments.com.evil.com/order-123",
        "https://user@paybylink.trustpayments.com/order-123",
        "http://paybylink.trustpayments.com/order-123",
    ],
)
def test_validate_payment_url_rejects_other_addresses(url):
    with pytest.raises(ValueError):
        validate_payment_url(url)


def test_company_paypal_url_rejects_trust_link():
    with pytest.raises(ValueError):
        validate_company_paypal_url(TRUST_LINK)
    assert validate_company_paypal_url(DEFAULT_PAYPAL_PAYMENT_LINK) == DEFAULT_PAYPAL_PAYMENT_LINK
    assert validate_company_paypal_url("  ") is None


def test_message_must_contain_only_the_link_being_sent():
    assert_payment_message_links(f"Pay here: {TRUST_LINK}", TRUST_LINK)
    order = SimpleNamespace(order_number="SO-1", deposit_amount=10, balance_amount=0, total_amount=10)
    assert_payment_message_links(default_payment_sms_body(order, TRUST_LINK), TRUST_LINK)
    assert_payment_message_links(default_payment_email_html(order, DEFAULT_PAYPAL_PAYMENT_LINK), DEFAULT_PAYPAL_PAYMENT_LINK)
    with pytest.raises(ValueError):
        assert_payment_message_links(f"Pay {TRUST_LINK} or https://evil.example/pay", TRUST_LINK)
    with pytest.raises(ValueError):
        assert_payment_message_links("Please call the office", TRUST_LINK)


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


def test_resolve_payment_url_prefers_requested_then_saved():
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
    assert resolve_payment_url(None, None, settings) == ""
    assert resolve_payment_url(None, None, None) == ""
    assert resolve_payment_url(None, None, CompanySettings(company_name="Test Co", updated_by_id=1)) == ""
    assert resolve_payment_url(None, saved, settings) == saved
