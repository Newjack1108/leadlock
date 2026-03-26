"""Shared logic to remove a quote and dependent rows (does not commit)."""

from sqlmodel import Session, select

from app.models import (
    DiscountRequest,
    Quote,
    QuoteDiscount,
    QuoteEmail,
    QuoteItem,
)


def delete_quote_cascade(session: Session, quote_id: int) -> None:
    """Delete a quote and dependents. Caller must delete orders referencing this quote first."""
    for dr in session.exec(select(DiscountRequest).where(DiscountRequest.quote_id == quote_id)).all():
        session.delete(dr)
    session.flush()
    for discount in session.exec(select(QuoteDiscount).where(QuoteDiscount.quote_id == quote_id)).all():
        session.delete(discount)
    session.flush()
    existing_items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
    for item in existing_items:
        if item.parent_quote_item_id is not None:
            item.parent_quote_item_id = None
            session.add(item)
    session.flush()
    for item in existing_items:
        session.delete(item)
    session.flush()
    for qe in session.exec(select(QuoteEmail).where(QuoteEmail.quote_id == quote_id)).all():
        session.delete(qe)
    session.flush()
    quote = session.get(Quote, quote_id)
    if quote:
        session.delete(quote)
    session.flush()
