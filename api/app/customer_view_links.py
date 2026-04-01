"""Customer-facing tracked view URLs: /orders/view vs /quotes/view by token."""
from sqlmodel import Session, select

from app.models import Order


def customer_view_path_segment(session: Session, quote_id: int, token: str) -> str:
    """Path after origin, e.g. orders/view/abc or quotes/view/abc (no leading slash)."""
    has_order = session.exec(select(Order).where(Order.quote_id == quote_id)).first() is not None
    return f"orders/view/{token}" if has_order else f"quotes/view/{token}"
