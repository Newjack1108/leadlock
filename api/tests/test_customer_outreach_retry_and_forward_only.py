import os
from datetime import datetime, timedelta
import uuid

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.customer_outreach_service import run_customer_outreach_cycle
from app.models import (
    Customer,
    CustomerOutreachSend,
    CustomerOutreachChannel,
    Lead,
    LeadStatus,
    ReminderPriority,
    ReminderRule,
    SuggestedAction,
    User,
    UserRole,
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_lead_sms_rule(session: Session, *, enabled_from: datetime | None, lead_updated_at: datetime) -> tuple[ReminderRule, Lead]:
    user = User(
        email=f"director-{datetime.utcnow().timestamp()}@example.com",
        hashed_password="dummy",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    customer = Customer(
        customer_number=f"CUST-{uuid.uuid4().hex[:10]}",
        name="Retry Customer",
        phone="+447700900123",
        email="retry@example.com",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    lead = Lead(
        name="Retry Lead",
        status=LeadStatus.NEW,
        customer_id=customer.id,
        assigned_to_id=user.id,
        updated_at=lead_updated_at,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    rule = ReminderRule(
        rule_name=f"RULE_{int(datetime.utcnow().timestamp() * 1000)}",
        entity_type="LEAD",
        status=LeadStatus.NEW.value,
        threshold_minutes=0,
        check_type="STATUS_DURATION",
        is_active=True,
        priority=ReminderPriority.MEDIUM,
        suggested_action=SuggestedAction.FOLLOW_UP,
        customer_outreach_channel=CustomerOutreachChannel.SMS.value,
        customer_outreach_sms_template_id=1,
        customer_outreach_cooldown_days=14,
        outreach_enabled_from_utc=enabled_from,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule, lead


def test_failed_outreach_is_recorded_once_and_not_retried(monkeypatch):
    engine = _engine()
    now = datetime.utcnow()

    calls = {"count": 0}

    def fake_send_sms(*args, **kwargs):
        calls["count"] += 1
        return False, None, "Twilio error 30003: unreachable handset"

    monkeypatch.setattr("app.customer_outreach_service._send_outreach_sms", fake_send_sms)

    with Session(engine) as session:
        _seed_lead_sms_rule(session, enabled_from=None, lead_updated_at=now)
        sent_count_1 = run_customer_outreach_cycle(session)
        sent_count_2 = run_customer_outreach_cycle(session)

        sends = list(session.exec(select(CustomerOutreachSend)).all())

    assert sent_count_1 == 0
    assert sent_count_2 == 0
    assert calls["count"] == 1
    assert len(sends) == 1
    assert sends[0].status == "FAILED"
    assert "unreachable handset" in (sends[0].failure_reason or "")


def test_forward_only_rule_skips_backfilled_stale_item(monkeypatch):
    engine = _engine()
    now = datetime.utcnow()
    called = {"value": False}

    def fake_send_sms(*args, **kwargs):
        called["value"] = True
        return True, "SM1", None

    monkeypatch.setattr("app.customer_outreach_service._send_outreach_sms", fake_send_sms)

    with Session(engine) as session:
        _seed_lead_sms_rule(
            session,
            enabled_from=now,
            lead_updated_at=now - timedelta(days=3),
        )
        sent_count = run_customer_outreach_cycle(session)
        sends = list(session.exec(select(CustomerOutreachSend)).all())

    assert sent_count == 0
    assert called["value"] is False
    assert len(sends) == 0


def test_forward_only_rule_allows_future_match_once(monkeypatch):
    engine = _engine()
    now = datetime.utcnow()
    calls = {"count": 0}

    def fake_send_sms(*args, **kwargs):
        calls["count"] += 1
        return True, "SM_SUCCESS", None

    monkeypatch.setattr("app.customer_outreach_service._send_outreach_sms", fake_send_sms)

    with Session(engine) as session:
        _seed_lead_sms_rule(
            session,
            enabled_from=now - timedelta(minutes=1),
            lead_updated_at=now,
        )
        sent_count_1 = run_customer_outreach_cycle(session)
        sent_count_2 = run_customer_outreach_cycle(session)
        sends = list(session.exec(select(CustomerOutreachSend)).all())

    assert sent_count_1 == 1
    assert sent_count_2 == 0
    assert calls["count"] == 1
    assert len(sends) == 1
    assert sends[0].status == "SENT"
    assert sends[0].failure_reason is None
