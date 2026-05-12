import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Activity,
    ActivityType,
    Customer,
    CustomerOutreachChannel,
    CustomerOutreachSend,
    Email,
    EmailDirection,
    Lead,
    LeadSource,
    LeadStatus,
    ReminderPriority,
    ReminderRule,
    SmsDirection,
    SmsMessage,
    StatusHistory,
    SuggestedAction,
    User,
    UserRole,
)
from app.routers import customers as customers_router
from app.routers import users as users_router
from app.system_user_service import get_system_user_id, system_user_email


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _app(engine, director_id: int, *, include_customers: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(users_router.router)
    if include_customers:
        app.include_router(customers_router.router)

    def session_override():
        with Session(engine) as session:
            yield session

    def current_user_override():
        with Session(engine) as session:
            user = session.get(User, director_id)
            assert user is not None
            return user

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = current_user_override
    return app


def test_users_api_hides_and_protects_internal_system_account():
    engine = _engine()
    with Session(engine) as session:
        director = User(
            email="director@example.com",
            hashed_password="x",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)
        director_id = director.id
        system_id = get_system_user_id(session)

    client = TestClient(_app(engine, director_id))

    list_res = client.get("/api/users")
    assert list_res.status_code == 200
    emails = [row["email"] for row in list_res.json()]
    assert "director@example.com" in emails
    assert system_user_email() not in emails

    reserved_name_res = client.post(
        "/api/users",
        json={
            "email": "reserved-name@example.com",
            "full_name": "System",
            "password": "secret123",
            "role": "CLOSER",
        },
    )
    assert reserved_name_res.status_code == 400
    assert "reserved" in reserved_name_res.json()["detail"].lower()

    reserved_email_res = client.post(
        "/api/users",
        json={
            "email": system_user_email(),
            "full_name": "Automation Account",
            "password": "secret123",
            "role": "CLOSER",
        },
    )
    assert reserved_email_res.status_code == 400
    assert system_user_email() in reserved_email_res.json()["detail"]

    update_res = client.put(f"/api/users/{system_id}", json={"full_name": "Changed"})
    assert update_res.status_code == 400
    assert "managed automatically" in update_res.json()["detail"]


def test_system_attribution_backfill_reassigns_only_automated_rows():
    engine = _engine()
    now = datetime.utcnow()

    with Session(engine) as session:
        director = User(
            email="director@example.com",
            hashed_password="x",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        brian = User(
            email="brian@example.com",
            hashed_password="x",
            full_name="Brian Dawson",
            role=UserRole.CLOSER,
        )
        session.add(director)
        session.add(brian)
        session.commit()
        session.refresh(director)
        session.refresh(brian)
        director_id = director.id
        brian_id = brian.id
        system_id = get_system_user_id(session)

        customer = Customer(
            customer_number="CUST-TEST-001",
            name="Pat Customer",
            email="pat@example.com",
            phone="+447700900999",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        customer_id = customer.id

        lead = Lead(
            name="Pat Lead",
            email="pat@example.com",
            phone="+447700900999",
            customer_id=customer_id,
            lead_source=LeadSource.FACEBOOK,
            status=LeadStatus.NEW,
            created_at=now,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lead_id = lead.id

        rule = ReminderRule(
            rule_name="SYSTEM_ATTRIBUTION_TEST",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=30,
            check_type="LAST_ACTIVITY",
            priority=ReminderPriority.HIGH,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        automated_sms_activity = Activity(
            customer_id=customer.id,
            activity_type=ActivityType.SMS_SENT,
            notes="Automated SMS (rule SYSTEM_ATTRIBUTION_TEST) to +447700900999\nHello from automation",
            created_by_id=brian_id,
        )
        automated_email_activity = Activity(
            customer_id=customer_id,
            activity_type=ActivityType.EMAIL_SENT,
            notes="Automated email (rule SYSTEM_ATTRIBUTION_TEST) to pat@example.com\nSubject: Automated hello",
            created_by_id=brian_id,
        )
        inbound_email_activity = Activity(
            customer_id=customer_id,
            activity_type=ActivityType.EMAIL_RECEIVED,
            notes="Email received from pat@example.com\nSubject: Re: Automated hello",
            created_by_id=brian_id,
        )
        facebook_note_activity = Activity(
            customer_id=customer_id,
            activity_type=ActivityType.NOTE,
            notes="Lead from Facebook Lead Ad form",
            created_by_id=brian_id,
            created_at=now,
        )
        manual_activity = Activity(
            customer_id=customer_id,
            activity_type=ActivityType.NOTE,
            notes="Manual note by Brian",
            created_by_id=brian_id,
        )
        session.add(automated_sms_activity)
        session.add(automated_email_activity)
        session.add(inbound_email_activity)
        session.add(facebook_note_activity)
        session.add(manual_activity)

        sms = SmsMessage(
            customer_id=customer_id,
            lead_id=lead_id,
            direction=SmsDirection.SENT,
            from_phone="+441234567890",
            to_phone="+447700900999",
            body="Hello from automation",
            twilio_sid="SM-system-attribution",
            sent_at=now,
            created_by_id=brian_id,
        )
        email = Email(
            customer_id=customer_id,
            message_id="MSG-system-attribution",
            direction=EmailDirection.SENT,
            from_email="brian@example.com",
            to_email="pat@example.com",
            subject="Automated hello",
            body_text="Automated body",
            sent_at=now,
            created_by_id=brian_id,
        )
        session.add(sms)
        session.add(email)

        status_history = StatusHistory(
            lead_id=lead_id,
            new_status=LeadStatus.NEW,
            changed_by_id=brian_id,
            created_at=now,
        )
        session.add(status_history)

        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer_id,
                channel=CustomerOutreachChannel.SMS.value,
                lead_id=lead_id,
                external_message_id="SM-system-attribution",
                status="SENT",
                sent_at=now,
            )
        )
        session.add(
            CustomerOutreachSend(
                reminder_rule_id=rule.id,
                customer_id=customer_id,
                channel=CustomerOutreachChannel.EMAIL.value,
                lead_id=lead_id,
                external_message_id="MSG-system-attribution",
                status="SENT",
                sent_at=now,
            )
        )
        session.commit()

    client = TestClient(_app(engine, director_id))
    res = client.post(
        "/api/users/system-attribution/backfill",
        json={"user_id": brian_id, "dry_run": False},
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["source_user_id"] == brian_id
    assert payload["system_user_id"] == system_id
    assert payload["activities_updated"] == 4
    assert payload["emails_updated"] == 1
    assert payload["sms_messages_updated"] == 1
    assert payload["status_history_updated"] == 1
    assert payload["total_updated"] == 7

    with Session(engine) as session:
        rows = list(session.exec(select(Activity).where(Activity.created_by_id == system_id)).all())
        automated_notes = {row.notes for row in rows}
        assert "Automated SMS (rule SYSTEM_ATTRIBUTION_TEST) to +447700900999\nHello from automation" in automated_notes
        assert "Automated email (rule SYSTEM_ATTRIBUTION_TEST) to pat@example.com\nSubject: Automated hello" in automated_notes
        assert "Email received from pat@example.com\nSubject: Re: Automated hello" in automated_notes
        assert "Lead from Facebook Lead Ad form" in automated_notes

        manual = session.exec(select(Activity).where(Activity.notes == "Manual note by Brian")).one()
        assert manual.created_by_id == brian_id

        updated_sms = session.exec(select(SmsMessage).where(SmsMessage.twilio_sid == "SM-system-attribution")).one()
        assert updated_sms.created_by_id == system_id

        updated_email = session.exec(select(Email).where(Email.message_id == "MSG-system-attribution")).one()
        assert updated_email.created_by_id == system_id

        updated_status = session.exec(select(StatusHistory).where(StatusHistory.lead_id == lead_id)).one()
        assert updated_status.changed_by_id == system_id

    history_client = TestClient(_app(engine, director_id, include_customers=True))
    history_res = history_client.get(f"/api/customers/{customer_id}/history")
    assert history_res.status_code == 200
    events = history_res.json()["events"]
    sms_event = next(
        event
        for event in events
        if event["description"] == "Automated SMS (rule SYSTEM_ATTRIBUTION_TEST) to +447700900999\nHello from automation"
    )
    assert sms_event["created_by_name"] == "System"
