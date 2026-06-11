"""SQL filters and helpers to exclude sandbox customers from aggregates and automation."""
from typing import Optional, Type

from sqlalchemy import or_
from sqlmodel import Session, SQLModel, select

from app.models import Customer, Lead, Quote


def test_customer_ids_subquery():
    return select(Customer.id).where(Customer.exclude_from_stats.is_(True))


def lead_counts_toward_stats():
    """Leads without a customer, or not linked to a stats-excluded customer, count toward stats."""
    return or_(
        Lead.customer_id.is_(None),
        Lead.customer_id.notin_(test_customer_ids_subquery()),
    )


def quote_counts_toward_stats():
    return Quote.customer_id.notin_(test_customer_ids_subquery())


def customer_communication_counts_toward_stats(model: Type[SQLModel]):
    """Email, SmsMessage, MessengerMessage, Activity rows tied to sandbox customers are excluded."""
    return or_(
        model.customer_id.is_(None),
        model.customer_id.notin_(test_customer_ids_subquery()),
    )


def is_stats_excluded_customer_id(session: Session, customer_id: Optional[int]) -> bool:
    if not customer_id:
        return False
    customer = session.get(Customer, customer_id)
    return bool(customer and getattr(customer, "exclude_from_stats", False))
