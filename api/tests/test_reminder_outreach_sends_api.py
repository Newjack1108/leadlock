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
    ReminderPriority,
    ReminderRule,
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


def test_outreach_sends_list_filters_channel_and_target_type():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-outreach@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(customer_number="CUST-OUTREACH-001", name="Outreach Customer", email="outreach@example.com")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(name="Lead A", status="NEW", customer_id=customer.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead.id,
            quote_number="QT-OUTREACH-001",
            status=QuoteStatus.SENT,
            subtotal=100,
            total_amount=100,
            created_by_id=director.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        lead_rule = ReminderRule(
            rule_name="LEAD_STALE_SMS",
            entity_type="LEAD",
            status="NEW",
            threshold_minutes=60,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        quote_rule = ReminderRule(
            rule_name="QUOTE_STALE_EMAIL",
            entity_type="QUOTE",
            status="SENT",
            threshold_minutes=60,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(lead_rule)
        session.add(quote_rule)
        session.commit()
        session.refresh(lead_rule)
        session.refresh(quote_rule)

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=lead_rule.id,
                customer_id=customer.id,
                channel="SMS",
                lead_id=lead.id,
                quote_id=None,
                external_message_id="SM123",
                sent_at=datetime.utcnow() - timedelta(minutes=30),
            )
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=quote_rule.id,
                customer_id=customer.id,
                channel="EMAIL",
                lead_id=lead.id,
                quote_id=quote.id,
                external_message_id="MSG123",
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()

        user_ctx = SimpleNamespace(id=director.id, role=director.role, full_name=director.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)

    res_all = client.get("/api/reminders/outreach-sends")
    assert res_all.status_code == 200
    payload_all = res_all.json()
    assert payload_all["total"] == 2
    assert len(payload_all["items"]) == 2

    res_sms = client.get("/api/reminders/outreach-sends?channel=SMS")
    assert res_sms.status_code == 200
    payload_sms = res_sms.json()
    assert payload_sms["total"] == 1
    assert payload_sms["items"][0]["channel"] == "SMS"
    assert payload_sms["items"][0]["target_type"] == "LEAD"

    res_quote = client.get("/api/reminders/outreach-sends?target_type=QUOTE")
    assert res_quote.status_code == 200
    payload_quote = res_quote.json()
    assert payload_quote["total"] == 1
    assert payload_quote["items"][0]["channel"] == "EMAIL"
    assert payload_quote["items"][0]["target_type"] == "QUOTE"
    assert payload_quote["items"][0]["quote_number"] == "QT-OUTREACH-001"


def test_outreach_sends_list_requires_director_role():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    user_ctx = SimpleNamespace(id=1, role=UserRole.CLOSER, full_name="Closer")
    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)

    res = client.get("/api/reminders/outreach-sends")
    assert res.status_code == 403
    assert "Only directors" in res.json()["detail"]
