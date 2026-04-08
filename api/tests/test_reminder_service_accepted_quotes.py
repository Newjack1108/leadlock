"""Stale-quote reminder detection must ignore won/accepted quotes."""
from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine

from app.models import (
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
            threshold_days=1,
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
