from io import BytesIO
import uuid

from app.quote_pdf_service import generate_quote_pdf_cached


def test_generate_quote_pdf_cached_hits_after_first_write(monkeypatch):
    calls = {"count": 0}

    def _fake_generator(**kwargs):
        calls["count"] += 1
        return BytesIO(b"%PDF-1.4 test")

    monkeypatch.setattr("app.quote_pdf_service.generate_quote_pdf", _fake_generator)

    payload = {
        "quote": object(),
        "customer": object(),
        "quote_items": [],
    }

    cache_key = f"unit-test-cache-key-{uuid.uuid4().hex}"
    data1, hit1 = generate_quote_pdf_cached(cache_key=cache_key, **payload)
    data2, hit2 = generate_quote_pdf_cached(cache_key=cache_key, **payload)

    assert data1 == data2
    assert hit1 is False
    assert hit2 is True
    assert calls["count"] == 1


def test_generate_quote_pdf_cached_forwards_dealer_branding_args(monkeypatch):
    captured = {}

    def _fake_generator(**kwargs):
        captured.update(kwargs)
        return BytesIO(b"%PDF-1.4 branded")

    monkeypatch.setattr("app.quote_pdf_service.generate_quote_pdf", _fake_generator)

    cache_key = f"unit-test-cache-key-brand-{uuid.uuid4().hex}"
    dealer_profile = {"company_name": "Trade Co", "email": "hello@example.com"}
    trader_logo_url = "https://example.com/logo.png"
    generate_quote_pdf_cached(
        cache_key=cache_key,
        quote=object(),
        customer=object(),
        quote_items=[],
        dealer_profile=dealer_profile,
        trader_logo_url=trader_logo_url,
    )

    assert captured["dealer_profile"] == dealer_profile
    assert captured["trader_logo_url"] == trader_logo_url
