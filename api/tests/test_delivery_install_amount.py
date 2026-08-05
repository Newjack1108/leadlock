"""Tests for delivery/install Ex VAT sum helper."""
from decimal import Decimal
from types import SimpleNamespace

from app.delivery_install_amount import is_delivery_or_install_line, sum_delivery_install_ex_vat
from app.models import QuoteItemLineType


def test_sum_by_line_type():
    items = [
        SimpleNamespace(
            description="Cabin",
            line_type=None,
            final_line_total=Decimal("5000"),
            quantity=1,
            unit_price=Decimal("5000"),
        ),
        SimpleNamespace(
            description="Delivery & Installation",
            line_type=QuoteItemLineType.DELIVERY,
            final_line_total=Decimal("850.50"),
            quantity=1,
            unit_price=Decimal("850.50"),
        ),
    ]
    amount, label = sum_delivery_install_ex_vat(items)
    assert amount == Decimal("850.50")
    assert label == "Delivery & Installation"


def test_sum_by_description_fallback():
    items = [
        SimpleNamespace(
            description="Delivery only",
            line_type=None,
            final_line_total=Decimal("120"),
            quantity=1,
            unit_price=Decimal("120"),
        ),
    ]
    assert is_delivery_or_install_line(items[0]) is True
    amount, label = sum_delivery_install_ex_vat(items)
    assert amount == Decimal("120.00")
    assert label == "Delivery only"


def test_sum_none_when_no_delivery_lines():
    items = [
        SimpleNamespace(
            description="Cabin",
            line_type=None,
            final_line_total=Decimal("1000"),
            quantity=1,
            unit_price=Decimal("1000"),
        ),
    ]
    amount, label = sum_delivery_install_ex_vat(items)
    assert amount is None
    assert label is None
