"""SQL filters and helpers to exclude sandbox customers from aggregates and automation."""
from typing import Optional, Type

from sqlalchemy import and_, not_, or_
from sqlmodel import Session, SQLModel, select

from app.constants import TEST_CUSTOMER_EMAIL
from app.models import Customer, Lead, Quote


def test_customer_ids_subquery():
    return select(Customer.id).where(Customer.exclude_from_stats.is_(True))


def excluded_lead_ids_via_quotes_subquery():
    """Leads referenced by quotes on stats-excluded customers."""
    return select(Quote.lead_id).where(
        Quote.lead_id.isnot(None),
        Quote.customer_id.in_(test_customer_ids_subquery()),
    )


def _sandbox_customer_phones_subquery():
    return select(Customer.phone).where(
        Customer.exclude_from_stats.is_(True),
        Customer.phone.isnot(None),
        Customer.phone != "",
    )


def _orphan_sandbox_identity_lead_match():
    """Unlinked leads that match the canonical sandbox email or phone."""
    return or_(
        and_(
            Lead.customer_id.is_(None),
            Lead.email.isnot(None),
            Lead.email == TEST_CUSTOMER_EMAIL,
        ),
        and_(
            Lead.customer_id.is_(None),
            Lead.phone.isnot(None),
            Lead.phone != "",
            Lead.phone.in_(_sandbox_customer_phones_subquery()),
        ),
    )


def lead_counts_toward_stats():
    """Leads that should appear in dashboard/report lead aggregates."""
    excluded_customers = test_customer_ids_subquery()
    return and_(
        or_(
            Lead.customer_id.is_(None),
            Lead.customer_id.notin_(excluded_customers),
        ),
        Lead.id.notin_(excluded_lead_ids_via_quotes_subquery()),
        not_(_orphan_sandbox_identity_lead_match()),
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
