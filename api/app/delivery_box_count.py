"""Box counts for delivery-only trailer trip calculation."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, Optional

from app.models import Product, QuoteItem, QuoteItemLineType


def _boxes_per_product(product: Optional[Product]) -> int:
    if product is None:
        return 1
    bpp = product.boxes_per_product
    if bpp is None or bpp < 1:
        return 1
    return int(bpp)


def quote_delivery_box_count_from_items(
    items: Iterable[QuoteItem],
    products_by_id: Dict[int, Product],
    *,
    main_sort_order_max: int = 999,
) -> int:
    """
    Sum quantity × boxes_per_product for main catalog lines.
    Excludes delivery/install lines, optional extras (sort_order > main_sort_order_max), and is_extra products.
    """
    total = 0
    for item in items:
        if item.sort_order > main_sort_order_max:
            continue
        if item.line_type in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION):
            continue
        if item.product_id is None:
            continue
        product = products_by_id.get(item.product_id)
        if product and product.is_extra:
            continue
        qty = int(item.quantity) if item.quantity else 0
        if qty < 1:
            continue
        total += qty * _boxes_per_product(product)
    return total


def dealer_quote_delivery_box_count(items: Iterable[QuoteItem], products_by_id: Dict[int, Product]) -> int:
    """Dealer quotes: main lines use sort_order < 1000."""
    return quote_delivery_box_count_from_items(items, products_by_id, main_sort_order_max=999)
