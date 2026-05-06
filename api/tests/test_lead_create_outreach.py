"""Immediate customer outreach when a lead is created (customer_outreach_on_lead_create)."""

import uuid
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.customer_outreach_service import (
    QUIET_HOURS_AUDIT_PREFIX,
    try_customer_outreach_for_new_lead,
)
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


def test_try_customer_outreach_for_new_lead_suppressed_during_quiet_hours(monkeypatch):
    engine = _engine()
    calls = {"n": 0}

    def fake_deliver(session, *, company, lead, rule):
        calls["n"] += 1
        return True

    monkeypatch.setattr(
        "app.customer_outreach_service._deliver_lead_customer_outreach_once",
        fake_deliver,
    )
    monkeypatch.setattr(
        "app.customer_outreach_service._is_within_outreach_quiet_hours",
        lambda company: True,
    )

    with Session(engine) as session:
        user = User(
            email=f"u-quiet-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        tmpl = SmsTemplate(
            name="Quiet",
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
            rule_name=f"ON_CREATE_QUIET_{int(datetime.utcnow().timestamp() * 1000)}",
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

        audit_rows = list(session.exec(select(CustomerOutreachSend)).all())
        assert len(audit_rows) == 1
        assert audit_rows[0].status == "FAILED"
        assert audit_rows[0].failure_reason.startswith(QUIET_HOURS_AUDIT_PREFIX)

    assert n == 0
    assert calls["n"] == 0


def test_try_customer_outreach_new_lead_resolves_actor_when_unassigned(monkeypatch):
    """Webhook-style lead with no assignee: actor falls back to System user."""
    monkeypatch.setenv("CUSTOMER_OUTREACH_ACTOR_USER_ID", "")
    monkeypatch.setenv("WEBHOOK_DEFAULT_USER_ID", "")
    monkeypatch.setattr(
        "app.customer_outreach_service._is_within_outreach_quiet_hours",
        lambda company: False,
    )

    send_calls = {"n": 0}

    def fake_send_sms(_to, _body):
        send_calls["n"] += 1
        return True, "SMok_sid", None

    monkeypatch.setattr("app.customer_outreach_service.send_sms", fake_send_sms)
    monkeypatch.setattr(
        "app.customer_outreach_service.get_twilio_config",
        lambda: ("sid", "token", "+441234567890"),
    )

    engine = _engine()
    with Session(engine) as session:
        director = User(
            email=f"dir-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        tmpl = SmsTemplate(
            name="Webhook style welcome",
            body_template="Hi {{ customer.name }}",
            created_by_id=director.id,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)

        customer = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Sam",
            phone="+447700900777",
            email=None,
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        rule = ReminderRule(
            rule_name=f"WEBHOOK_STYLE_{int(datetime.utcnow().timestamp() * 1000)}",
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
            name="Sam",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=None,
            phone="+447700900777",
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        n = try_customer_outreach_for_new_lead(session, lead)
        rows = list(session.exec(select(CustomerOutreachSend)).all())

    assert n == 1
    assert send_calls["n"] == 1
    assert len(rows) == 1
    assert rows[0].status == "SENT"


def test_try_customer_outreach_quiet_hours_audit_does_not_block_retry(monkeypatch):
    monkeypatch.setenv("CUSTOMER_OUTREACH_ACTOR_USER_ID", "")
    monkeypatch.setenv("WEBHOOK_DEFAULT_USER_ID", "")
    qh = {"on": True}

    def fake_send_sms(_to, _body):
        return True, "SM_retry_ok", None

    monkeypatch.setattr("app.customer_outreach_service.send_sms", fake_send_sms)
    monkeypatch.setattr(
        "app.customer_outreach_service.get_twilio_config",
        lambda: ("sid", "token", "+441234567890"),
    )
    monkeypatch.setattr(
        "app.customer_outreach_service._is_within_outreach_quiet_hours",
        lambda company: qh["on"],
    )

    engine = _engine()
    with Session(engine) as session:
        director = User(
            email=f"dirqh-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        tmpl = SmsTemplate(
            name="Retry after quiet",
            body_template="Hi {{ customer.name }}",
            created_by_id=director.id,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)

        customer = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Bo",
            phone="+447700900888",
            email=None,
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        rule = ReminderRule(
            rule_name=f"QUIET_RETRY_{int(datetime.utcnow().timestamp() * 1000)}",
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
            name="Bo",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=None,
            phone="+447700900888",
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        n1 = try_customer_outreach_for_new_lead(session, lead)
        stubs = list(session.exec(select(CustomerOutreachSend)).all())

        qh["on"] = False
        n2 = try_customer_outreach_for_new_lead(session, lead)
        all_rows = list(session.exec(select(CustomerOutreachSend)).all())

    assert n1 == 0
    assert len(stubs) == 1
    assert stubs[0].failure_reason.startswith(QUIET_HOURS_AUDIT_PREFIX)

    assert n2 == 1
    assert len(all_rows) == 2
    assert sum(1 for r in all_rows if r.status == "SENT") == 1


def test_try_customer_outreach_for_new_lead_blocks_when_opt_out_flips_before_dispatch(monkeypatch):
    engine = _engine()
    send_calls = {"count": 0}
    opt_out_checks = {"count": 0}

    def fake_send_sms(*args, **kwargs):
        send_calls["count"] += 1
        return True, "SM_SHOULD_NOT_SEND", None

    def fake_opt_out_check(_session, _customer_id):
        opt_out_checks["count"] += 1
        # First pre-check false, second dispatch-time check true.
        return opt_out_checks["count"] >= 2

    monkeypatch.setattr("app.customer_outreach_service.send_sms", fake_send_sms)
    monkeypatch.setattr(
        "app.customer_outreach_service._customer_opted_out_of_rule_outreach",
        fake_opt_out_check,
    )

    with Session(engine) as session:
        user = User(
            email=f"u-flip-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        tmpl = SmsTemplate(
            name="Flip",
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
            rule_name=f"ON_CREATE_FLIP_{int(datetime.utcnow().timestamp() * 1000)}",
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
        sends = list(session.exec(select(CustomerOutreachSend)).all())

    assert n == 0
    assert send_calls["count"] == 0
    assert len(sends) == 0
