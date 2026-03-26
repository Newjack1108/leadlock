"""Shared logic to remove an order and dependent rows (does not commit)."""

from sqlmodel import Session, select

from app.models import AccessSheetRequest, Order, OrderItem


def delete_order_cascade(session: Session, order_id: int) -> None:
    """Delete access sheet requests, line items, and the order row."""
    for asr in session.exec(select(AccessSheetRequest).where(AccessSheetRequest.order_id == order_id)).all():
        session.delete(asr)
    session.flush()
    for oi in session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all():
        session.delete(oi)
    session.flush()
    order = session.get(Order, order_id)
    if order:
        session.delete(order)
    session.flush()
