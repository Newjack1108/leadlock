from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlmodel import Session

from app.models import Order, OrderAuditEvent


def record_order_audit_event(
    session: Session,
    *,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    order: Optional[Order] = None,
    customer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    order_number: Optional[str] = None,
    quote_id: Optional[int] = None,
    metadata: Optional[dict[str, Any]] = None,
    created_by_id: Optional[int] = None,
    created_at: Optional[datetime] = None,
) -> Optional[OrderAuditEvent]:
    resolved_customer_id = customer_id if customer_id is not None else getattr(order, "customer_id", None)
    if resolved_customer_id is None:
        return None

    resolved_order_id = order_id if order_id is not None else getattr(order, "id", None)
    resolved_order_number = order_number if order_number is not None else getattr(order, "order_number", None)
    resolved_quote_id = quote_id if quote_id is not None else getattr(order, "quote_id", None)

    event_metadata = dict(metadata or {})
    if resolved_order_id is not None:
        event_metadata.setdefault("order_id", resolved_order_id)
    if resolved_order_number:
        event_metadata.setdefault("order_number", resolved_order_number)
    if resolved_quote_id is not None:
        event_metadata.setdefault("quote_id", resolved_quote_id)

    audit_event = OrderAuditEvent(
        customer_id=resolved_customer_id,
        order_id=resolved_order_id,
        event_type=event_type,
        title=title,
        description=description,
        details=event_metadata or None,
        created_by_id=created_by_id,
        created_at=created_at or datetime.utcnow(),
    )
    session.add(audit_event)
    return audit_event
