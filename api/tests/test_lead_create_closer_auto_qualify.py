"""Closer POST /api/leads auto-qualifies regardless of lead_source (e.g. REFERRAL)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token
from app.routers import leads as leads_router
from app.models import (
    CompanySettings,
    CustomerOutreachChannel,
    LeadSource,
    LeadStatus,
    ReminderPriority,
    ReminderRule,
    SmsTemplate,
    SuggestedAction,
    User,
    UserRole,
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


@pytest.fixture()
def api_client(sqlite_engine):
    from app.database import get_session

    app = FastAPI()
    app.include_router(leads_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _add_closer(session: Session) -> User:
    user = User(
        email="closer-auto-qual@example.com",
        hashed_password="x",
        full_name="Closer",
        role=UserRole.CLOSER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_director(session: Session) -> User:
    user = User(
        email="director-auto-qual@example.com",
        hashed_password="x",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_closer_create_lead_referral_is_qualified_with_customer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_closer(session)
        token = create_access_token(data={"sub": closer.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Walk-in Pat",
            "lead_source": LeadSource.REFERRAL.value,
            "phone": "+447700900001",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == LeadStatus.QUALIFIED.value
    assert data["customer_id"] is not None
    assert data["lead_source"] == LeadSource.REFERRAL.value


def test_director_create_lead_referral_stays_new(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Inbound only",
            "lead_source": LeadSource.REFERRAL.value,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == LeadStatus.NEW.value
    assert data["customer_id"] is None


def test_director_create_new_lead_links_customer_when_on_create_outreach_rule_exists(
    api_client, sqlite_engine
):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        sms_template = SmsTemplate(
            name="On create",
            body_template="Hi {{ customer.name }}",
            created_by_id=director.id,
        )
        session.add(sms_template)
        session.commit()
        session.refresh(sms_template)
        rule = ReminderRule(
            rule_name="NEW_LEAD_ON_CREATE_SMS",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=1,
            check_type="STATUS_DURATION",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
            customer_outreach_channel=CustomerOutreachChannel.SMS.value,
            customer_outreach_sms_template_id=sms_template.id,
            customer_outreach_on_lead_create=True,
        )
        session.add(rule)
        session.commit()

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Inbound with phone",
            "lead_source": LeadSource.REFERRAL.value,
            "phone": "+447700900999",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == LeadStatus.NEW.value
    assert data["customer_id"] is not None


def test_duplicate_lead_auto_closes_and_sends_duplicate_sms(api_client, sqlite_engine, monkeypatch):
    sms_bodies: list[str] = []

    def fake_send_sms(_to_phone: str, body: str):
        sms_bodies.append(body)
        return True, f"SM_{len(sms_bodies)}", None

    monkeypatch.setattr("app.customer_outreach_service.send_sms", fake_send_sms)
    monkeypatch.setattr(
        "app.customer_outreach_service.get_twilio_config",
        lambda: ("sid", "token", "+441234567890"),
    )
    monkeypatch.setenv("LEAD_DEDUPE_ENABLED", "true")

    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        company = CompanySettings(
            company_name="CSGB",
            updated_by_id=director.id,
            duplicate_sms_cooldown_days=7,
            auto_close_duplicate_leads=True,
        )
        session.add(company)
        session.commit()
        session.refresh(company)

        welcome_template = SmsTemplate(
            name="On create",
            body_template="Welcome {{ customer.name }}",
            created_by_id=director.id,
        )
        duplicate_template = SmsTemplate(
            name="Duplicate Lead Notice",
            body_template=(
                "Thanks for your enquiry. We've linked it to your existing request "
                "(Lead #{{ duplicate.primary_lead_id }})."
            ),
            created_by_id=director.id,
        )
        session.add(welcome_template)
        session.add(duplicate_template)
        session.commit()
        session.refresh(welcome_template)
        session.refresh(duplicate_template)

        company.duplicate_sms_template_id = duplicate_template.id
        session.add(company)
        session.commit()

        rule = ReminderRule(
            rule_name="NEW_LEAD_ON_CREATE_SMS_DUPLICATE_TEST",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=1,
            check_type="STATUS_DURATION",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
            customer_outreach_channel=CustomerOutreachChannel.SMS.value,
            customer_outreach_sms_template_id=welcome_template.id,
            customer_outreach_on_lead_create=True,
        )
        session.add(rule)
        session.commit()

    first = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Repeat Person",
            "lead_source": LeadSource.WEBSITE.value,
            "email": "repeat@example.com",
            "phone": "+447700900111",
            "postcode": "CW1 1AA",
        },
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    first_id = first_data["id"]

    second = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Repeat Person",
            "lead_source": LeadSource.WEBSITE.value,
            "email": "repeat@example.com",
            "phone": "+447700900111",
            "postcode": "CW1 1AA",
        },
    )
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["is_duplicate"] is True
    assert second_data["primary_lead_id"] == first_id
    assert second_data["status"] == LeadStatus.CLOSED.value
    assert any("existing request" in body for body in sms_bodies)
