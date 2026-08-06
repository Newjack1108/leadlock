import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from app.models import QuoteFulfillmentMethod
from app.quote_pdf_service import generate_dealer_quote_pdf, generate_quote_pdf


def _quote_fixture():
    quote = SimpleNamespace(
        id=7,
        quote_number="DQ-100",
        currency="GBP",
        subtotal=Decimal("1000.00"),
        discount_total=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        deposit_amount=Decimal("120.00"),
        balance_amount=Decimal("1080.00"),
        created_at=datetime(2026, 8, 6, 10, 0, 0),
        valid_until=None,
        version=1,
        terms_and_conditions=None,
        include_spec_sheets=True,
        include_specification_sheet=True,
        include_delivery_installation_contact_note=False,
        fulfillment_method=QuoteFulfillmentMethod.DELIVERY,
        use_alternate_delivery_address=False,
    )
    customer = SimpleNamespace(
        customer_number="DEALER-7",
        name="In Person Customer",
        email="customer@example.com",
        phone="07000 000000",
        address_line1="1 Stable Lane",
        address_line2=None,
        city=None,
        county=None,
        postcode="CW1 1AA",
    )
    item = SimpleNamespace(
        id=1,
        description="Stable box",
        quantity=Decimal("1"),
        unit_price=Decimal("1000.00"),
        final_line_total=Decimal("1000.00"),
        parent_quote_item_id=None,
        sort_order=0,
    )
    return quote, customer, [item]


def test_generate_dealer_quote_pdf_is_slim_takeaway(monkeypatch):
    quote, customer, items = _quote_fixture()
    called = {"company_header": False, "company_footer": False, "layout": False}

    def _fail_header(*_args, **_kwargs):
        called["company_header"] = True
        return []

    def _fail_footer(*_args, **_kwargs):
        called["company_footer"] = True

        def _drawer(*_a, **_k):
            return None

        return _drawer

    monkeypatch.setattr("app.quote_pdf_service._build_header_flowables", _fail_header)
    monkeypatch.setattr("app.quote_pdf_service._make_footer_canvas_drawer", _fail_footer)

    def _fake_layout(session, quote_id):
        called["layout"] = True
        return None

    monkeypatch.setattr(
        "app.configurator_layout_public.build_layout_for_public_view",
        _fake_layout,
    )

    pdf = generate_dealer_quote_pdf(
        quote=quote,
        customer=customer,
        quote_items=items,
        dealer_profile={
            "company_name": "Equine Saddlery",
            "email": "shop@example.com",
            "phone": "01234 567890",
            "vat_number": "GB123",
        },
        trader_logo_url=None,
        session=SimpleNamespace(),
    )

    assert isinstance(pdf, BytesIO)
    data = pdf.getvalue()
    assert data.startswith(b"%PDF")
    assert called["company_header"] is False
    assert called["company_footer"] is False
    # Layout lookup is allowed; company header/footer must not be used
    assert called["layout"] is True


def test_sales_generate_quote_pdf_still_uses_company_chrome(monkeypatch):
    quote, customer, items = _quote_fixture()
    called = {"header": False, "footer": False}

    def _header(*_args, **_kwargs):
        called["header"] = True
        return []

    def _footer(*_args, **_kwargs):
        called["footer"] = True

        def _drawer(*_a, **_k):
            return None

        return _drawer

    monkeypatch.setattr("app.quote_pdf_service._build_header_flowables", _header)
    monkeypatch.setattr("app.quote_pdf_service._make_footer_canvas_drawer", _footer)
    monkeypatch.setattr("app.quote_pdf_service._resolve_logo", lambda *_a, **_k: (None, None))
    monkeypatch.setattr("app.quote_pdf_service._resolve_footer_logo", lambda *_a, **_k: (None, None))
    monkeypatch.setattr(
        "app.quote_pdf_service._resolve_header_trading_name",
        lambda *_a, **_k: "Cheshire Stables",
    )
    monkeypatch.setattr(
        "app.configurator_layout_public.build_layout_for_public_view",
        lambda *_a, **_k: None,
    )

    company = SimpleNamespace(
        trading_name="Cheshire Stables",
        default_terms_and_conditions="",
        installation_lead_time=None,
    )

    pdf = generate_quote_pdf(
        quote=quote,
        customer=customer,
        quote_items=items,
        company_settings=company,
        session=None,
        include_spec_sheets=False,
        include_specification_sheet=False,
    )
    assert pdf.getvalue().startswith(b"%PDF")
    assert called["header"] is True
    assert called["footer"] is True
