"""Tests for quote delivery box counting."""
from decimal import Decimal

from app.delivery_box_count import dealer_quote_delivery_box_count
from app.models import Product, QuoteItem, QuoteItemLineType


def test_dealer_quote_delivery_box_count_sums_main_lines():
    product = Product(
        id=1,
        name="Stable",
        base_price=Decimal("1000"),
        boxes_per_product=2,
    )
    items = [
        QuoteItem(
            quote_id=1,
            product_id=1,
            description="Stable",
            quantity=Decimal("2"),
            unit_price=Decimal("1000"),
            line_total=Decimal("2000"),
            sort_order=0,
        ),
        QuoteItem(
            quote_id=1,
            product_id=2,
            description="Extra",
            quantity=Decimal("2"),
            unit_price=Decimal("50"),
            line_total=Decimal("100"),
            sort_order=1001,
        ),
    ]
    assert dealer_quote_delivery_box_count(items, {1: product}) == 4
