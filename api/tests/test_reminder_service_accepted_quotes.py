"""Stale-quote reminder detection must ignore won/accepted quotes."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    Customer,
    Quote,
    QuoteStatus,
    ReminderRule,
    ReminderPriority,
    SuggestedAction,
    User,
    UserRole,
)
from app.reminder_service import detect_stale_quotes


def test_detect_stale_quotes_skips_accepted_quote_with_unscoped_rule():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    old_sent = datetime.utcnow() - timedelta(days=30)

    with Session(engine) as session:
        user = User(
            email="reminder-test@example.com",
            hashed_password="x",
            full_name="Reminder Test",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        accepted = Quote(
            quote_number="QT-TEST-ACCEPTED",
            status=QuoteStatus.ACCEPTED,
            accepted_at=datetime.utcnow(),
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
            sent_at=old_sent,
        )
        sent = Quote(
            quote_number="QT-TEST-SENT",
            status=QuoteStatus.SENT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
            sent_at=old_sent,
        )
        session.add(accepted)
        session.add(sent)
        session.commit()
        session.refresh(accepted)
        session.refresh(sent)

        rule = ReminderRule(
            rule_name="TEST_UNSCOPED_SENT_DATE",
            entity_type="QUOTE",
            status=None,
            threshold_minutes=1440,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()

        stale = detect_stale_quotes(session)
        quote_ids = {q.id for q, _, _ in stale}
        assert accepted.id not in quote_ids
        assert sent.id in quote_ids


def test_detect_stale_quotes_only_returns_latest_quote_per_customer():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    now = datetime.utcnow()
    older_sent_at = now - timedelta(days=20)
    latest_sent_at = now - timedelta(days=5)

    with Session(engine) as session:
        user = User(
            email="reminder-test-latest@example.com",
            hashed_password="x",
            full_name="Reminder Test Latest",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-LATEST-001",
            name="Latest Quote Customer",
            email="latest@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        older_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-TEST-OLDER",
            status=QuoteStatus.SENT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
            sent_at=older_sent_at,
            created_at=older_sent_at - timedelta(days=1),
        )
        latest_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-TEST-LATEST",
            status=QuoteStatus.SENT,
            subtotal=Decimal("200.00"),
            total_amount=Decimal("200.00"),
            created_by_id=user.id,
            sent_at=latest_sent_at,
            created_at=latest_sent_at,
        )
        session.add(older_quote)
        session.add(latest_quote)
        session.commit()
        session.refresh(older_quote)
        session.refresh(latest_quote)

        rule = ReminderRule(
            rule_name="TEST_LATEST_PER_CUSTOMER",
            entity_type="QUOTE",
            status=QuoteStatus.SENT.value,
            threshold_minutes=1440,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()

        stale = detect_stale_quotes(session)
        stale_for_customer = [q.id for q, _, _ in stale if q.customer_id == customer.id]
        assert stale_for_customer == [latest_quote.id]
