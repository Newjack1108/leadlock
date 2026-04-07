"""Resolve optional extras linked to quoted products that are not yet on the quote."""
from decimal import Decimal
from typing import Any, List

from sqlmodel import Session, select

from app.models import Product, ProductOptionalExtra, QuoteItemLineType


def get_available_optional_extras_for_quote(quote_items: list, session: Session) -> List[dict[str, Any]]:
    """
    Get optional extras for the quote that are not already line items.

    Includes:
    - Extras linked via ProductOptionalExtra to a main product line on the quote (sales UI / catalogue links).
    - Unlinked optional extras (is_extra, active, no ProductOptionalExtra row), e.g. pushed from production
      without parent links — only when the quote has at least one main product line.
    """
    main_items = [
        i
        for i in quote_items
        if getattr(i, "parent_quote_item_id", None) is None
        and getattr(i, "line_type", None) not in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION)
        and getattr(i, "product_id", None) is not None
    ]
    already_in_quote = {getattr(i, "product_id", None) for i in quote_items if getattr(i, "product_id", None) is not None}

    linked_optional_extra_ids = set(
        session.exec(select(ProductOptionalExtra.optional_extra_id).distinct()).all()
    )

    result = []
    seen = set()  # (optional_extra_id, product_id) to deduplicate
    seen_extra_ids = set()

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
        for _, extra_product in session.exec(stmt).all():
            if extra_product.id in already_in_quote:
                continue
            key = (extra_product.id, pid)
            if key in seen:
                continue
            seen.add(key)
            seen_extra_ids.add(extra_product.id)
            result.append(
                {
                    "name": extra_product.name,
                    "base_price": extra_product.base_price or Decimal(0),
                }
            )

    if main_items:
        orphan_stmt = select(Product).where(
            Product.is_extra == True,
            Product.is_active == True,
        )
        for extra_product in session.exec(orphan_stmt).all():
            if extra_product.id in already_in_quote:
                continue
            if extra_product.id in linked_optional_extra_ids:
                continue
            if extra_product.id in seen_extra_ids:
                continue
            seen_extra_ids.add(extra_product.id)
            result.append(
                {
                    "name": extra_product.name,
                    "base_price": extra_product.base_price or Decimal(0),
                }
            )

    result.sort(key=lambda row: (row["name"] or "").lower())
    return result
