"""Shared logic to remove an order and dependent rows (does not commit)."""

from sqlmodel import Session, select

from app.models import AccessSheetRequest, CustomerFile, Order, OrderItem
from app.customer_file_service import delete_customer_file_from_cloudinary


def delete_order_cascade(session: Session, order_id: int) -> None:
    """Delete access sheet requests, line items and the order row.

    For attached files: if a file is also linked to the quote, just clear the
    ``order_id`` so it remains visible on the quote. Otherwise the file has no
    other home, so delete the row and best-effort remove the Cloudinary asset.
    """
    for asr in session.exec(select(AccessSheetRequest).where(AccessSheetRequest.order_id == order_id)).all():
        session.delete(asr)
    session.flush()
    for cf in session.exec(select(CustomerFile).where(CustomerFile.order_id == order_id)).all():
        if cf.quote_id is None:
            delete_customer_file_from_cloudinary(cf.cloudinary_public_id, cf.cloudinary_resource_type)
            session.delete(cf)
        else:
            cf.order_id = None
            session.add(cf)
    session.flush()
    for oi in session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all():
        session.delete(oi)
    session.flush()
    order = session.get(Order, order_id)
    if order:
        session.delete(order)
    session.flush()
