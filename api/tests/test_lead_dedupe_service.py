"""Inbound duplicate detection: same contact, different product type, auto-close."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["WEBHOOK_API_KEY"] = "test-webhook-key"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.lead_dedupe_service import detect_duplicate_for_lead
from app.models import CompanySettings, Lead, LeadSource, LeadStatus, LeadType, User, UserRole
from app.routers import webhooks as webhooks_router


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


def _add_user(session: Session) -> User:
    user = User(
        email="dedupe-staff@example.com",
        hashed_password="x",
        full_name="Staff",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_same_contact_different_lead_type_is_not_duplicate(sqlite_engine):
    with Session(sqlite_engine) as session:
        existing = Lead(
            name="Pat Cabin",
            email="pat@example.com",
            phone="+447700900222",
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.FACEBOOK,
            status=LeadStatus.QUALIFIED,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

        incoming = Lead(
            name="Pat Cabin",
            email="pat@example.com",
            phone="+447700900222",
            lead_type=LeadType.CABINS,
            lead_source=LeadSource.BLC_WEBSITE,
            status=LeadStatus.NEW,
        )
        session.add(incoming)
        session.commit()
        session.refresh(incoming)

        match = detect_duplicate_for_lead(session, incoming)
        assert match.is_duplicate is False


def test_same_contact_same_lead_type_is_duplicate(sqlite_engine):
    with Session(sqlite_engine) as session:
        existing = Lead(
            name="Pat Cabin",
            email="pat@example.com",
            phone="+447700900333",
            lead_type=LeadType.CABINS,
            lead_source=LeadSource.BLC_WEBSITE,
            status=LeadStatus.NEW,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

        incoming = Lead(
            name="Pat Cabin",
            email="pat@example.com",
            phone="+447700900333",
            lead_type=LeadType.CABINS,
            lead_source=LeadSource.BLC_WEBSITE,
            status=LeadStatus.NEW,
        )
        session.add(incoming)
        session.commit()
        session.refresh(incoming)

        match = detect_duplicate_for_lead(session, incoming)
        assert match.is_duplicate is True
        assert match.primary_lead_id == existing.id


def test_webhook_duplicate_same_type_auto_closes(sqlite_engine, monkeypatch):
    monkeypatch.setenv("LEAD_DEDUPE_ENABLED", "true")
    monkeypatch.setenv("WEBHOOK_API_KEY", "test-webhook-key")

    from app.database import get_session

    app = FastAPI()
    app.include_router(webhooks_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = _add_user(session)
        monkeypatch.setenv("WEBHOOK_DEFAULT_USER_ID", str(user.id))
        session.add(
            CompanySettings(
                company_name="CSGB",
                updated_by_id=user.id,
                auto_close_duplicate_leads=True,
            )
        )
        session.commit()

    with TestClient(app) as client:
        payload = {
            "name": "Repeat Person",
            "lead_source": LeadSource.BLC_WEBSITE.value,
            "lead_type": LeadType.CABINS.value,
            "email": "repeat-web@example.com",
            "phone": "+447700900444",
        }
        first = client.post(
            "/api/webhooks/leads",
            headers={"X-API-Key": "test-webhook-key"},
            json=payload,
        )
        assert first.status_code == 200, first.text
        first_id = first.json()["id"]
        assert first.json()["status"] == LeadStatus.NEW.value

        second = client.post(
            "/api/webhooks/leads",
            headers={"X-API-Key": "test-webhook-key"},
            json=payload,
        )
        assert second.status_code == 200, second.text
        second_data = second.json()
        assert second_data["is_duplicate"] is True
        assert second_data["primary_lead_id"] == first_id
        assert second_data["status"] == LeadStatus.CLOSED.value

    app.dependency_overrides.clear()
