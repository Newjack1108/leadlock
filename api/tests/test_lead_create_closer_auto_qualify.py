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
