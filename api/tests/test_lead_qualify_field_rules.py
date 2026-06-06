"""Lead source/type required before QUALIFIED; customer lead create is NEW until qualified."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token
from app.routers import customers as customers_router
from app.routers import leads as leads_router
from app.models import (
    Customer,
    LeadSource,
    LeadStatus,
    LeadType,
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
    app.include_router(customers_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _add_director(session: Session) -> User:
    user = User(
        email="director-qualify-fields@example.com",
        hashed_password="x",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_closer(session: Session) -> User:
    user = User(
        email="closer-qualify-fields@example.com",
        hashed_password="x",
        full_name="Closer",
        role=UserRole.CLOSER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_lead(session: Session, *, lead_source: LeadSource, lead_type: LeadType) -> int:
    from app.models import Lead

    lead = Lead(
        name="Test Lead",
        email="test@example.com",
        phone="+447700900100",
        postcode="CW1 1AA",
        status=LeadStatus.ENGAGED,
        lead_source=lead_source,
        lead_type=lead_type,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return int(lead.id)


def test_transition_to_qualified_blocked_for_other_source(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        lead_id = _seed_lead(session, lead_source=LeadSource.OTHER, lead_type=LeadType.STABLES)

    r = api_client.post(
        f"/api/leads/{lead_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_status": LeadStatus.QUALIFIED.value},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "LEAD_FIELDS_REQUIRED_FOR_QUALIFY"


def test_transition_to_qualified_blocked_for_unknown_type(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        lead_id = _seed_lead(session, lead_source=LeadSource.REFERRAL, lead_type=LeadType.UNKNOWN)

    r = api_client.post(
        f"/api/leads/{lead_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_status": LeadStatus.QUALIFIED.value},
    )
    assert r.status_code == 400


def test_transition_to_qualified_allowed(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        lead_id = _seed_lead(session, lead_source=LeadSource.REFERRAL, lead_type=LeadType.CABINS)

    r = api_client.post(
        f"/api/leads/{lead_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_status": LeadStatus.QUALIFIED.value},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == LeadStatus.QUALIFIED.value


def test_director_create_manual_entry_stays_new(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Walk-in",
            "lead_source": LeadSource.MANUAL_ENTRY.value,
            "lead_type": LeadType.STABLES.value,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == LeadStatus.NEW.value


def test_closer_create_with_valid_fields_is_qualified(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_closer(session)
        token = create_access_token(data={"sub": closer.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Walk-in",
            "lead_source": LeadSource.REFERRAL.value,
            "lead_type": LeadType.SHEDS.value,
            "phone": "+447700900101",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == LeadStatus.QUALIFIED.value


def test_closer_create_without_type_stays_new(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_closer(session)
        token = create_access_token(data={"sub": closer.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Walk-in",
            "lead_source": LeadSource.REFERRAL.value,
            "phone": "+447700900102",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == LeadStatus.NEW.value


def test_customer_lead_create_requires_source_and_type(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})
        customer = Customer(
            customer_number="CUST-001",
            name="Existing Customer",
            email="cust@example.com",
            phone="+447700900200",
            postcode="CW1 2AB",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        customer_id = customer.id

    r = api_client.post(
        f"/api/customers/{customer_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 400

    r2 = api_client.post(
        f"/api/customers/{customer_id}/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "lead_source": LeadSource.PAST_CUSTOMER.value,
            "lead_type": LeadType.STABLES.value,
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == LeadStatus.NEW.value
    assert r2.json()["lead_source"] == LeadSource.PAST_CUSTOMER.value
    assert r2.json()["lead_type"] == LeadType.STABLES.value


def test_director_manual_create_ui_payload(api_client, sqlite_engine):
    """Matches Create Lead dialog: name, source, type, contact fields."""
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Manual Test",
            "email": "manual@example.com",
            "wrong_email_address": False,
            "phone": "+447700900300",
            "postcode": "CW1 2AB",
            "description": "Walk-in enquiry",
            "lead_source": LeadSource.PHONE.value,
            "lead_type": LeadType.CABINS.value,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == LeadStatus.NEW.value
    assert data["lead_source"] == LeadSource.PHONE.value
    assert data["lead_type"] == LeadType.CABINS.value
    assert data["name"] == "Manual Test"


def test_manual_create_with_alias_fields(api_client, sqlite_engine):
    """Webhook/Make-style aliases must not break in-app create path."""
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        token = create_access_token(data={"sub": director.email})

    r = api_client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "first_name": "Jane",
            "last_name": "Smith",
            "phone_number": "+447700900301",
            "lead_source": LeadSource.REFERRAL.value,
            "lead_type": LeadType.STABLES.value,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "Jane Smith"
    assert data["phone"] == "+447700900301"
    assert data["lead_source"] == LeadSource.REFERRAL.value
    assert data["lead_type"] == LeadType.STABLES.value
