"""GET /api/reminders enriches each card with latest CustomerOutreachSend for lead/quote."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    CustomerOutreachSend,
    Lead,
    Quote,
    QuoteStatus,
    Reminder,
    ReminderPriority,
    ReminderRule,
    ReminderType,
    SuggestedAction,
    User,
    UserRole,
)
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


def test_get_reminders_auto_outreach_latest_failed_wins_over_sent():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="dir-auto-outreach@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(customer_number="C-AO-001", name="Auto Outreach Customer", email="ao@example.com")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(name="Lead Auto", status="NEW", customer_id=customer.id, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        rule = ReminderRule(
            rule_name="LEAD_STALE_AUTO_TEST",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=60,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        reminder = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=lead.id,
            quote_id=None,
            customer_id=customer.id,
            assigned_to_id=director.id,
            priority=ReminderPriority.HIGH,
            title="Stale lead",
            message="Follow up",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=5,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        t_old = datetime.utcnow() - timedelta(hours=2)
        t_new = datetime.utcnow() - timedelta(minutes=5)
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel="SMS",
                lead_id=lead.id,
                quote_id=None,
                external_message_id="SM111",
                status="SENT",
                sent_at=t_old,
            )
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel="SMS",
                lead_id=lead.id,
                quote_id=None,
                external_message_id=None,
                status="FAILED",
                failure_reason="Twilio timeout simulation",
                sent_at=t_new,
            )
        )
        session.commit()

        reminder_id = reminder.id
        user_ctx = SimpleNamespace(id=director.id, role=director.role, full_name=director.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)
    res = client.get("/api/reminders")
    assert res.status_code == 200
    items = res.json()
    row = next((x for x in items if x["id"] == reminder_id), None)
    assert row is not None
    assert row["auto_outreach_status"] == "FAILED"
    assert row["auto_outreach_channel"] == "SMS"
    assert row["auto_outreach_failure_reason"] == "Twilio timeout simulation"
    assert row["auto_outreach_rule_name"] == "LEAD_STALE_AUTO_TEST"


def test_get_reminders_auto_outreach_quote_target_matches_by_quote_id():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="dir-quote-ao@example.com",
            hashed_password="dummy",
            full_name="Director Q",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(customer_number="C-AO-Q-001", name="Q Customer", email="q@example.com")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(name="Lead Q", status="NEW", customer_id=customer.id, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead.id,
            quote_number="QT-AO-001",
            status=QuoteStatus.SENT,
            subtotal=100,
            total_amount=100,
            created_by_id=director.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        rule = ReminderRule(
            rule_name="QUOTE_STALE_AUTO_TEST",
            entity_type="QUOTE",
            status="SENT",
            threshold_minutes=60,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        reminder = Reminder(
            reminder_type=ReminderType.QUOTE_STALE,
            lead_id=lead.id,
            quote_id=quote.id,
            customer_id=customer.id,
            assigned_to_id=director.id,
            priority=ReminderPriority.MEDIUM,
            title="Stale quote",
            message="Ping customer",
            suggested_action=SuggestedAction.CONTACT_CUSTOMER,
            days_stale=3,
        )
        session.add(reminder)
        session.commit()
        session.refresh(reminder)

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer.id,
                channel="EMAIL",
                lead_id=lead.id,
                quote_id=quote.id,
                external_message_id="mid-1",
                status="SENT",
                sent_at=datetime.utcnow() - timedelta(hours=1),
            )
        )
        session.commit()

        reminder_id = reminder.id
        user_ctx = SimpleNamespace(id=director.id, role=director.role, full_name=director.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)
    res = client.get("/api/reminders")
    assert res.status_code == 200
    row = next((x for x in res.json() if x["id"] == reminder_id), None)
    assert row is not None
    assert row["auto_outreach_status"] == "SENT"
    assert row["auto_outreach_channel"] == "EMAIL"
    assert row["auto_outreach_failure_reason"] is None
    assert row["auto_outreach_rule_name"] == "QUOTE_STALE_AUTO_TEST"
