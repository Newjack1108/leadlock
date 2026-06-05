"""Stale reference date/label resolution for reminders and weekly plan items."""
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    Customer,
    Lead,
    LeadStatus,
    Order,
    Quote,
    QuoteStatus,
    Reminder,
    ReminderPriority,
    ReminderRule,
    ReminderType,
    SuggestedAction,
    User,
    UserRole,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
)
from app.stale_reference_service import (
    enrich_reminder_stale_fields,
    enrich_weekly_plan_item_stale_fields,
    resolve_stale_reference_for_lead,
    resolve_stale_reference_for_opportunity,
    resolve_stale_reference_for_order,
    resolve_stale_reference_for_quote,
)


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_user(session: Session) -> User:
    user = User(
        email="stale@example.com",
        hashed_password="x",
        full_name="Stale Tester",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _rule(check_type: str) -> ReminderRule:
    return ReminderRule(
        rule_name=f"rule-{check_type}",
        entity_type="LEAD",
        check_type=check_type,
        threshold_minutes=7 * 24 * 60,
        priority=ReminderPriority.MEDIUM,
        suggested_action=SuggestedAction.FOLLOW_UP,
        is_active=True,
    )


def _seed_quote(session: Session, *, quote_number: str, sent_at: datetime | None = None) -> Quote:
    user = _seed_user(session)
    customer = Customer(
        customer_number=f"CUST-{quote_number}",
        name=f"Customer {quote_number}",
        email=f"{quote_number}@example.com",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        quote_number=quote_number,
        customer_id=customer.id,
        status=QuoteStatus.SENT if sent_at else QuoteStatus.DRAFT,
        subtotal=Decimal("1000"),
        discount_total=Decimal("0"),
        total_amount=Decimal("1000"),
        currency="GBP",
        created_by_id=user.id,
        sent_at=sent_at,
        created_at=datetime.utcnow() - timedelta(days=20),
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return quote


def _seed_order(session: Session, *, completed_at: datetime) -> Order:
    quote = _seed_quote(session, quote_number="Q-ORD", sent_at=datetime.utcnow() - timedelta(days=5))
    user = session.get(User, quote.created_by_id)
    assert user is not None
    order = Order(
        quote_id=quote.id,
        customer_id=quote.customer_id,
        order_number="ORD-1",
        subtotal=Decimal("1000"),
        discount_total=Decimal("0"),
        total_amount=Decimal("1000"),
        currency="GBP",
        created_by_id=user.id,
        installation_completed=True,
        installation_completed_at=completed_at,
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_resolve_stale_reference_for_lead_last_activity(sqlite_engine):
    ref_at = datetime(2026, 2, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        lead = Lead(
            name="Acme",
            status=LeadStatus.NEW,
            updated_at=datetime(2026, 3, 1),
            created_at=datetime(2026, 1, 1),
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        with patch("app.reminder_service.get_last_activity_date", return_value=ref_at):
            ref, label = resolve_stale_reference_for_lead(lead, _rule("LAST_ACTIVITY"), session)

        assert ref == ref_at
        assert label == "Last activity"


def test_resolve_stale_reference_for_quote_sent_date(sqlite_engine):
    sent_at = datetime(2026, 2, 10, 9, 0, 0)
    with Session(sqlite_engine) as session:
        quote = _seed_quote(session, quote_number="Q-100", sent_at=sent_at)
        ref, label = resolve_stale_reference_for_quote(quote, _rule("SENT_DATE"))
        assert ref == sent_at
        assert label == "Quote sent"


def test_resolve_stale_reference_for_opportunity_quote_sent(sqlite_engine):
    sent_at = datetime(2026, 1, 15, 10, 0, 0)
    with Session(sqlite_engine) as session:
        quote = _seed_quote(session, quote_number="Q-200", sent_at=sent_at)
        ref, label = resolve_stale_reference_for_opportunity(
            quote, "QUOTE_SENT_SOFT_NUDGE", session
        )
        assert ref == sent_at
        assert label == "Quote sent"


def test_resolve_stale_reference_for_order_installation(sqlite_engine):
    completed_at = datetime(2026, 3, 1, 14, 0, 0)
    with Session(sqlite_engine) as session:
        order = _seed_order(session, completed_at=completed_at)
        ref, label = resolve_stale_reference_for_order(order)
        assert ref == completed_at
        assert label == "Installation completed"


def test_enrich_reminder_uses_persisted_fields(sqlite_engine):
    ref_at = datetime(2026, 2, 20)
    with Session(sqlite_engine) as session:
        reminder = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            assigned_to_id=1,
            priority=ReminderPriority.MEDIUM,
            title="Stale lead",
            message="msg",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=5,
            stale_reference_at=ref_at,
            stale_source_label="Last activity",
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        ref, label = enrich_reminder_stale_fields(reminder, session)
        assert ref == ref_at
        assert label == "Last activity"


def test_enrich_reminder_request_review_from_order(sqlite_engine):
    completed_at = datetime.utcnow() - timedelta(days=3)
    with Session(sqlite_engine) as session:
        order = _seed_order(session, completed_at=completed_at)
        reminder = Reminder(
            reminder_type=ReminderType.REQUEST_REVIEW,
            order_id=order.id,
            assigned_to_id=order.created_by_id,
            priority=ReminderPriority.MEDIUM,
            title="Review",
            message="Please request review",
            suggested_action=SuggestedAction.REQUEST_REVIEW,
            days_stale=3,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        ref, label = enrich_reminder_stale_fields(reminder, session)
        assert ref == completed_at
        assert label == "Installation completed"


def test_enrich_weekly_plan_item_quote_with_reason_code(sqlite_engine):
    sent_at = datetime.utcnow() - timedelta(days=12)
    with Session(sqlite_engine) as session:
        quote = _seed_quote(session, quote_number="Q-300", sent_at=sent_at)
        run = WeeklyPlanRun(week_start=date.today())
        session.add(run)
        session.commit()
        session.refresh(run)

        item = WeeklyPlanItem(
            plan_run_id=run.id,
            quote_id=quote.id,
            priority_score=Decimal("50"),
            confidence=Decimal("0.8"),
            order_likelihood_score=Decimal("0.5"),
            order_likelihood_confidence=Decimal("0.5"),
            recommended_action=SuggestedAction.FOLLOW_UP,
            status=WeeklyPlanItemStatus.PENDING_REVIEW,
            auto_eligible=False,
            reason_codes=["reason:QUOTE_SENT_FIRM_FOLLOWUP"],
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        ref, label, days_stale = enrich_weekly_plan_item_stale_fields(item, session)
        assert ref == sent_at
        assert label == "Quote sent"
        assert days_stale == 12


def test_enrich_weekly_plan_item_lead_last_activity(sqlite_engine):
    activity_at = datetime.utcnow() - timedelta(days=8)
    with Session(sqlite_engine) as session:
        lead = Lead(
            name="Beta Ltd",
            status=LeadStatus.NEW,
            updated_at=datetime.utcnow() - timedelta(days=2),
            created_at=datetime.utcnow() - timedelta(days=30),
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        run = WeeklyPlanRun(week_start=date.today())
        session.add(run)
        session.commit()
        session.refresh(run)

        item = WeeklyPlanItem(
            plan_run_id=run.id,
            lead_id=lead.id,
            priority_score=Decimal("40"),
            confidence=Decimal("0.7"),
            order_likelihood_score=Decimal("0.4"),
            order_likelihood_confidence=Decimal("0.4"),
            recommended_action=SuggestedAction.FOLLOW_UP,
            status=WeeklyPlanItemStatus.PENDING_REVIEW,
            auto_eligible=False,
        )
        session.add(item)
        session.commit()
        session.refresh(item)

        with patch("app.reminder_service.get_last_activity_date", return_value=activity_at):
            ref, label, days_stale = enrich_weekly_plan_item_stale_fields(item, session)

        assert ref == activity_at
        assert label == "Last activity"
        assert days_stale == 8
