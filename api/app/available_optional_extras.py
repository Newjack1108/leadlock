"""Resolve optional extras for quote PDF/view (line items excluded)."""
from decimal import Decimal
from typing import Any, List, Optional

from sqlmodel import Session, select

from app.models import Product, ProductOptionalExtra, QuoteDisplayedOptionalExtra, QuoteItemLineType
from app.quote_displayed_optional_extras import quote_has_displayed_optional_extras


def should_show_available_optional_extras_on_quote(
    quote,
    quote_id: int,
    session: Session,
    *,
    quote_email=None,
) -> bool:
    """Whether customer PDF/view should include an 'Other Available Options' section."""
    if quote_email is not None and getattr(quote_email, "include_available_extras", False):
        return True
    if getattr(quote, "include_available_optional_extras", False):
        return True
    return quote_has_displayed_optional_extras(session, quote_id)


def _linked_optional_extras_for_quote_items(
    quote_items: list,
    session: Session,
    already_in_quote: set,
    seen_extra_ids: set,
) -> List[dict[str, Any]]:
    """Extras linked to main products on the quote via ProductOptionalExtra."""
    main_items = [
        i
        for i in quote_items
        if getattr(i, "parent_quote_item_id", None) is None
        and getattr(i, "line_type", None) not in (QuoteItemLineType.DELIVERY, QuoteItemLineType.INSTALLATION)
        and getattr(i, "product_id", None) is not None
    ]

    result: List[dict[str, Any]] = []
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
            if extra_product.id in already_in_quote or extra_product.id in seen_extra_ids:
                continue
            seen_extra_ids.add(extra_product.id)
            result.append(
                {
                    "name": extra_product.name,
                    "base_price": extra_product.base_price or Decimal(0),
                }
            )
    return result


def _manual_displayed_optional_extras(
    quote_id: int,
    quote_items: list,
    session: Session,
    already_in_quote: set,
    seen_extra_ids: set,
) -> List[dict[str, Any]]:
    """Extras explicitly chosen to display on the quote (not as line items)."""
    stmt = (
        select(QuoteDisplayedOptionalExtra, Product)
        .join(Product, QuoteDisplayedOptionalExtra.product_id == Product.id)
        .where(
            QuoteDisplayedOptionalExtra.quote_id == quote_id,
            Product.is_active == True,
        )
        .order_by(QuoteDisplayedOptionalExtra.sort_order, QuoteDisplayedOptionalExtra.id)
    )
    result: List[dict[str, Any]] = []
    for _, extra_product in session.exec(stmt).all():
        if extra_product.id in already_in_quote or extra_product.id in seen_extra_ids:
            continue
        seen_extra_ids.add(extra_product.id)
        result.append(
            {
                "name": extra_product.name,
                "base_price": extra_product.base_price or Decimal(0),
            }
        )
    return result


def get_available_optional_extras_for_quote(
    quote_items: list,
    session: Session,
    *,
    quote_id: Optional[int] = None,
    include_product_linked: bool = True,
) -> List[dict[str, Any]]:
    """
    Optional extras for PDF/customer view: not already on the quote as line items.
    Manual displayed extras (quote_id) are always included when set.
    Product-linked extras are included when include_product_linked is True.
    """
    already_in_quote = {
        getattr(i, "product_id", None)
        for i in quote_items
        if getattr(i, "product_id", None) is not None
    }
    seen_extra_ids: set[int] = set()
    result: List[dict[str, Any]] = []

    if quote_id is not None:
        result.extend(
            _manual_displayed_optional_extras(
                quote_id, quote_items, session, already_in_quote, seen_extra_ids
            )
        )

    if include_product_linked:
        result.extend(
            _linked_optional_extras_for_quote_items(
                quote_items, session, already_in_quote, seen_extra_ids
            )
        )

    result.sort(key=lambda row: (row["name"] or "").lower())
    return result
