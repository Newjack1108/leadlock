"""Resolve optional extras linked to quoted products that are not yet on the quote."""
from decimal import Decimal
from typing import Any, List

from sqlmodel import Session, select

from app.models import Product, ProductOptionalExtra, QuoteItemLineType


def get_available_optional_extras_for_quote(quote_items: list, session: Session) -> List[dict[str, Any]]:
    """
    Get optional extras linked to main products in the quote that are not already in the quote.
    Each item is a dict with keys name, base_price (compatible with PDF and public API).
    """
    main_items = [
        i
        for i in quote_items
        if getattr(i, "parent_quote_item_id", None) is None
        and getattr(i, "line_type", None) not in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION)
        and getattr(i, "product_id", None) is not None
    ]
    already_in_quote = {getattr(i, "product_id", None) for i in quote_items if getattr(i, "product_id", None) is not None}

    result = []
    seen = set()  # (optional_extra_id, product_id) to deduplicate

    for main_item in main_items:
        pid = getattr(main_item, "product_id", None)
        if not pid:
            continue

        stmt = (
            select(ProductOptionalExtra, Product)
            .join(Product, ProductOptionalExtra.optional_extra_id == Product.id)
            .where(
                ProductOptionalExtra.product_id == pid,
                Product.is_active == True,
            )
        )
        for link, extra_product in session.exec(stmt).all():
            if extra_product.id in already_in_quote:
                continue
            key = (extra_product.id, pid)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    "name": extra_product.name,
                    "base_price": extra_product.base_price or Decimal(0),
                }
            )
    return result
