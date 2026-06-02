"""Persist and load optional extras shown on quote PDF/view without being quote line items."""
from typing import List, Optional

from fastapi import HTTPException
from sqlmodel import Session, delete, select

from app.models import Product, QuoteDisplayedOptionalExtra


def get_displayed_optional_extra_ids(session: Session, quote_id: int) -> List[int]:
    rows = session.exec(
        select(QuoteDisplayedOptionalExtra.product_id)
        .where(QuoteDisplayedOptionalExtra.quote_id == quote_id)
        .order_by(QuoteDisplayedOptionalExtra.sort_order, QuoteDisplayedOptionalExtra.id)
    ).all()
    return list(rows)


def quote_has_displayed_optional_extras(session: Session, quote_id: int) -> bool:
    row = session.exec(
        select(QuoteDisplayedOptionalExtra.id)
        .where(QuoteDisplayedOptionalExtra.quote_id == quote_id)
        .limit(1)
    ).first()
    return row is not None


def sync_quote_displayed_optional_extras(
    session: Session,
    quote_id: int,
    product_ids: Optional[List[int]],
) -> None:
    """Replace displayed optional extras for a quote. Pass [] to clear."""
    if product_ids is None:
        return
    session.exec(
        delete(QuoteDisplayedOptionalExtra).where(QuoteDisplayedOptionalExtra.quote_id == quote_id)
    )
    seen: set[int] = set()
    for sort_order, raw_id in enumerate(product_ids):
        if raw_id in seen:
            continue
        seen.add(raw_id)
        product = session.get(Product, raw_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=400, detail=f"Optional extra product {raw_id} not found")
        if not getattr(product, "is_extra", False):
            raise HTTPException(
                status_code=400,
                detail=f"Product {raw_id} is not an optional extra",
            )
        session.add(
            QuoteDisplayedOptionalExtra(
                quote_id=quote_id,
                product_id=raw_id,
                sort_order=sort_order,
            )
        )
