"""Immediate customer outreach when a lead is created (customer_outreach_on_lead_create)."""

import uuid
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.customer_outreach_service import try_customer_outreach_for_new_lead
from app.models import (
    Customer,
    CustomerOutreachSend,
    CustomerOutreachChannel,
    Lead,
    LeadStatus,
    ReminderPriority,
    ReminderRule,
    SmsTemplate,
    SuggestedAction,
    User,
    UserRole,
)
from app.routers.leads import find_or_create_customer


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_try_customer_outreach_for_new_lead_sends_once(monkeypatch):
    engine = _engine()
    calls = {"n": 0}

    def fake_deliver(session, *, company, lead, rule):
        calls["n"] += 1
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=lead.customer_id,
                channel=CustomerOutreachChannel.SMS.value,
                lead_id=lead.id,
                quote_id=None,
                external_message_id="fake",
                status="SENT",
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()
        return True

    monkeypatch.setattr(
        "app.customer_outreach_service._deliver_lead_customer_outreach_once",
        fake_deliver,
    )

    with Session(engine) as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        tmpl = SmsTemplate(
            name="Welcome",
            body_template="Hi {{ customer.name }}",
            created_by_id=user.id,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)

        customer = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Pat",
            phone="+447700900321",
            email="pat@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        rule = ReminderRule(
            rule_name=f"ON_CREATE_{int(datetime.utcnow().timestamp() * 1000)}",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=999999,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.HIGH,
            suggested_action=SuggestedAction.FOLLOW_UP,
            customer_outreach_channel=CustomerOutreachChannel.SMS.value,
            customer_outreach_sms_template_id=tmpl.id,
            customer_outreach_cooldown_days=14,
            customer_outreach_on_lead_create=True,
        )
        session.add(rule)
        session.commit()

        lead = Lead(
            name="Pat",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=user.id,
            phone="+447700900321",
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        n = try_customer_outreach_for_new_lead(session, lead)
        n2 = try_customer_outreach_for_new_lead(session, lead)

    assert n == 1
    assert n2 == 0
    assert calls["n"] == 1


def test_find_or_create_matches_normalized_phone():
    engine = _engine()
    with Session(engine) as session:
        user = User(
            email=f"u2-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        existing = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Alex",
            phone="+447700900456",
            email=None,
        )
        session.add(existing)
        session.commit()

        lead = Lead(name="Alex", phone="07700900456", email=None, status=LeadStatus.NEW)
        customer = find_or_create_customer(lead, session)
        assert customer.id == existing.id
