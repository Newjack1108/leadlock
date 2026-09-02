"""Tests for quote custom_message HTML layout preservation."""
from decimal import Decimal
from types import SimpleNamespace

from jinja2 import Template

from app.quote_email_service import (
    format_custom_message_for_email_html,
    render_email_template,
)


def test_format_empty_and_none():
    assert format_custom_message_for_email_html(None) is None
    assert format_custom_message_for_email_html("") == ""


def test_format_paragraphs_and_blank_lines():
    raw = "Line one\n\nLine three"
    assert format_custom_message_for_email_html(raw) == "Line one<br>\n<br>\nLine three"


def test_format_crlf_and_bare_cr():
    assert format_custom_message_for_email_html("A\r\nB") == "A<br>\nB"
    assert format_custom_message_for_email_html("A\rB") == "A<br>\nB"


def test_format_consecutive_spaces_and_tabs():
    assert format_custom_message_for_email_html("hello  world") == "hello &nbsp;world"
    assert format_custom_message_for_email_html("a\tb") == "a &nbsp; &nbsp;b"


def test_format_html_characters_escaped():
    raw = 'See <b>bold</b> & "quotes"'
    result = format_custom_message_for_email_html(raw)
    assert "<b>" not in result
    assert "&lt;b&gt;bold&lt;/b&gt;" in result
    assert "&amp;" in result
    assert "&quot;quotes&quot;" in result


def test_body_render_preserves_breaks_subject_does_not():
    quote = SimpleNamespace(currency="GBP", total_amount=Decimal("100.00"))
    customer = SimpleNamespace(
        name="Jane",
        email="jane@example.com",
        phone=None,
        customer_number="C1",
        address_line1=None,
        address_line2=None,
        city=None,
        county=None,
        postcode=None,
        country=None,
    )
    raw = "Hello\nWorld <test>"
    subject_tmpl = Template("Re: {{ custom_message }}")
    body_tmpl = Template("{% if custom_message %}<p>{{ custom_message }}</p>{% endif %}")

    subject = render_email_template(subject_tmpl, quote, customer, None, raw)
    body = render_email_template(
        body_tmpl,
        quote,
        customer,
        None,
        format_custom_message_for_email_html(raw),
    )

    assert "Hello\nWorld" in subject
    assert "<br>" not in subject
    assert "Hello<br>\nWorld" in body
    assert "&lt;test&gt;" in body
    assert "<test>" not in body
