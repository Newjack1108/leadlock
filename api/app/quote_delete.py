"""Shared logic to remove a quote and dependent rows (does not commit)."""

from sqlmodel import Session, select

from app.models import (
    CustomerFile,
    CustomerOutreachSend,
    DiscountRequest,
    Quote,
    QuoteDiscount,
    QuoteEmail,
    QuoteItem,
    Reminder,
)
from app.customer_file_service import delete_customer_file_from_cloudinary


def delete_quote_cascade(session: Session, quote_id: int) -> None:
    """Delete a quote and dependents. Caller must delete orders referencing this quote first."""
    for rem in session.exec(select(Reminder).where(Reminder.quote_id == quote_id)).all():
        session.delete(rem)
    session.flush()
    for cos in session.exec(select(CustomerOutreachSend).where(CustomerOutreachSend.quote_id == quote_id)).all():
        session.delete(cos)
    session.flush()
    for dr in session.exec(select(DiscountRequest).where(DiscountRequest.quote_id == quote_id)).all():
        session.delete(dr)
    session.flush()
    for discount in session.exec(select(QuoteDiscount).where(QuoteDiscount.quote_id == quote_id)).all():
        session.delete(discount)
    session.flush()
    for cf in session.exec(select(CustomerFile).where(CustomerFile.quote_id == quote_id)).all():
        # If the file is also linked to an order, leave it attached to the
        # order; otherwise delete it (and best-effort remove the Cloudinary asset).
        if cf.order_id is None:
            delete_customer_file_from_cloudinary(cf.cloudinary_public_id, cf.cloudinary_resource_type)
            session.delete(cf)
        else:
            cf.quote_id = None
            session.add(cf)
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
