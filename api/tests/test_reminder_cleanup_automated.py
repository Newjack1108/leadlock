"""Bulk automated reminder cleanup deletes eligible reminders and suppresses regeneration."""
import os
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    AutomatedReminderCleanupSuppression,
    Customer,
    CustomerOutreachSend,
    Lead,
    Quote,
    QuoteStatus,
    Reminder,
    ReminderCleanupTargetKind,
    ReminderPriority,
    ReminderRule,
    ReminderType,
    SuggestedAction,
    User,
    UserRole,
)
from app.reminder_service import generate_reminders
from app.routers import reminders as reminders_router


def _make_test_app(engine, user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_cleanup_automated_reminders_respects_filters_and_only_deletes_badged_rows():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="dir-cleanup@example.com",
            hashed_password="dummy",
            full_name="Director Cleanup",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(
            customer_number="C-CLEAN-001",
            name="Cleanup Customer",
            email="cleanup@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead_rule = ReminderRule(
            rule_name="LEAD_CLEANUP_RULE",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=60,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.HIGH,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        quote_rule = ReminderRule(
            rule_name="QUOTE_CLEANUP_RULE",
            entity_type="QUOTE",
            status="SENT",
            threshold_minutes=60,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.CONTACT_CUSTOMER,
        )
        session.add(lead_rule)
        session.add(quote_rule)
        session.commit()
        session.refresh(lead_rule)
        session.refresh(quote_rule)

        lead_sent = Lead(
            name="Lead Sent",
            status="NEW",
            customer_id=customer.id,
            assigned_to_id=director.id,
        )
        lead_quote = Lead(
            name="Lead Quote Failed",
            status="NEW",
            customer_id=customer.id,
            assigned_to_id=director.id,
        )
        lead_unbadged = Lead(
            name="Lead Untouched",
            status="NEW",
            customer_id=customer.id,
            assigned_to_id=director.id,
        )
        session.add(lead_sent)
        session.add(lead_quote)
        session.add(lead_unbadged)
        session.commit()
        session.refresh(lead_sent)
        session.refresh(lead_quote)
        session.refresh(lead_unbadged)

        quote_failed = Quote(
            customer_id=customer.id,
            lead_id=lead_quote.id,
            quote_number="QT-CLEAN-001",
            status=QuoteStatus.SENT,
            subtotal=100,
            total_amount=100,
            created_by_id=director.id,
        )
        session.add(quote_failed)
        session.commit()
        session.refresh(quote_failed)

        reminder_sent_high = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=lead_sent.id,
            customer_id=customer.id,
            assigned_to_id=director.id,
            priority=ReminderPriority.HIGH,
            title="Lead sent",
            message="Auto outreach sent",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=5,
        )
        reminder_failed_medium = Reminder(
            reminder_type=ReminderType.QUOTE_STALE,
            lead_id=lead_quote.id,
            quote_id=quote_failed.id,
            customer_id=customer.id,
            assigned_to_id=director.id,
            priority=ReminderPriority.MEDIUM,
            title="Quote failed",
            message="Auto outreach failed",
            suggested_action=SuggestedAction.CONTACT_CUSTOMER,
            days_stale=3,
        )
        reminder_unbadged_high = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=lead_unbadged.id,
            customer_id=customer.id,
            assigned_to_id=director.id,
            priority=ReminderPriority.HIGH,
            title="Untouched",
            message="No auto outreach badge",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=2,
        )
        session.add(reminder_sent_high)
        session.add(reminder_failed_medium)
        session.add(reminder_unbadged_high)
        session.commit()
        session.refresh(reminder_sent_high)
        session.refresh(reminder_failed_medium)
        session.refresh(reminder_unbadged_high)

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=lead_rule.id,
                customer_id=customer.id,
                channel="SMS",
                lead_id=lead_sent.id,
                status="SENT",
                sent_at=datetime.utcnow(),
            )
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=quote_rule.id,
                customer_id=customer.id,
                channel="EMAIL",
                lead_id=lead_quote.id,
                quote_id=quote_failed.id,
                status="FAILED",
                failure_reason="Simulated failure",
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()

        sent_id = reminder_sent_high.id
        failed_id = reminder_failed_medium.id
        untouched_id = reminder_unbadged_high.id
        lead_sent_id = lead_sent.id
        quote_failed_id = quote_failed.id
        user_ctx = SimpleNamespace(id=director.id, role=director.role, full_name=director.full_name)

    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post("/api/reminders/cleanup-automated", json={"priority": "HIGH"})
    assert res.status_code == 200
    assert res.json() == {"deleted_count": 1, "deleted_ids": [sent_id]}

    with Session(engine) as session:
        remaining_ids = {row.id for row in session.exec(select(Reminder)).all()}
        assert sent_id not in remaining_ids
        assert failed_id in remaining_ids
        assert untouched_id in remaining_ids

    res = client.post("/api/reminders/cleanup-automated", json={})
    assert res.status_code == 200
    assert res.json() == {"deleted_count": 1, "deleted_ids": [failed_id]}

    with Session(engine) as session:
        remaining_ids = {row.id for row in session.exec(select(Reminder)).all()}
        assert remaining_ids == {untouched_id}

        suppressions = session.exec(select(AutomatedReminderCleanupSuppression)).all()
        assert len(suppressions) == 2
        assert {
            (row.target_kind, row.target_id, row.reminder_type, row.last_auto_outreach_status)
            for row in suppressions
        } == {
            (ReminderCleanupTargetKind.LEAD, lead_sent_id, ReminderType.LEAD_STALE, "SENT"),
            (ReminderCleanupTargetKind.QUOTE, quote_failed_id, ReminderType.QUOTE_STALE, "FAILED"),
        }


def test_cleanup_automated_reminders_suppresses_future_regeneration():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="dir-cleanup-regen@example.com",
            hashed_password="dummy",
            full_name="Director Regen",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(
            customer_number="C-CLEAN-REGEN-001",
            name="Cleanup Regen Customer",
            email="regen@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Lead Regen",
            status="NEW",
            customer_id=customer.id,
            assigned_to_id=director.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        rule = ReminderRule(
            rule_name="LEAD_REGEN_RULE",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=0,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        created = generate_reminders(session, director.id)
        assert created == 1

        reminder = session.exec(select(Reminder).where(Reminder.lead_id == lead.id)).first()
        assert reminder is not None

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel="SMS",
                lead_id=lead.id,
                status="SENT",
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()
        lead_id = lead.id
        user_ctx = SimpleNamespace(id=director.id, role=director.role, full_name=director.full_name)

    client = TestClient(_make_test_app(engine, user_ctx))
    res = client.post("/api/reminders/cleanup-automated", json={})
    assert res.status_code == 200
    assert res.json()["deleted_count"] == 1

    with Session(engine) as session:
        assert session.exec(select(Reminder)).all() == []
        suppressions = session.exec(select(AutomatedReminderCleanupSuppression)).all()
        assert len(suppressions) == 1
        assert suppressions[0].target_kind == ReminderCleanupTargetKind.LEAD
        assert suppressions[0].target_id == lead_id
        assert suppressions[0].reminder_type == ReminderType.LEAD_STALE

        regenerated = generate_reminders(session, director.id)
        assert regenerated == 0
        assert session.exec(select(Reminder)).all() == []
