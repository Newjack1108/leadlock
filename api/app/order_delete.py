"""Shared logic to remove an order and dependent rows (does not commit)."""

from sqlmodel import Session, select

from app.models import AccessSheetRequest, Order, OrderFile, OrderItem
from app.order_file_service import delete_order_file_from_cloudinary


def delete_order_cascade(session: Session, order_id: int) -> None:
    """Delete access sheet requests, line items, attached files and the order row."""
    for asr in session.exec(select(AccessSheetRequest).where(AccessSheetRequest.order_id == order_id)).all():
        session.delete(asr)
    session.flush()
    for of in session.exec(select(OrderFile).where(OrderFile.order_id == order_id)).all():
        # Best effort - never let a Cloudinary failure block order deletion.
        delete_order_file_from_cloudinary(of.cloudinary_public_id, of.cloudinary_resource_type)
        session.delete(of)
    session.flush()
    for oi in session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all():
        session.delete(oi)
    session.flush()
    order = session.get(Order, order_id)
    if order:
        session.delete(order)
    session.flush()
