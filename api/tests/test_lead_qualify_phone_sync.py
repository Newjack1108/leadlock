"""When a lead becomes qualified, copy lead contact fields to the linked customer (e.g. Facebook import)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token
from app.models import Customer, Lead, LeadSource, LeadStatus, LeadType, User, UserRole
from app.routers import leads as leads_router
from app.workflow import auto_transition_lead_status, sync_customer_contact_from_lead_on_qualify


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401 — register SQLModel tables

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def leads_api_client(sqlite_engine):
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


def test_sync_contact_overwrites_customer_phone(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = User(
            email="u-qphone@example.com",
            hashed_password="x",
            full_name="Sales",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-2026-901",
            name="Jane Smith",
            email="jane@example.com",
            phone="+441111111111",
            postcode="CH1 1AA",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Jane Smith",
            email="jane@example.com",
            phone="+449999888877",
            postcode="CH1 1AA",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            assigned_to_id=user.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.FACEBOOK,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        sync_customer_contact_from_lead_on_qualify(session, lead)
        session.commit()
        session.refresh(customer)

        assert customer.phone == "+449999888877"


def test_sync_full_contact_name_email_postcode_from_lead(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = User(
            email="u-full@example.com",
            hashed_password="x",
            full_name="Sales",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-2026-904",
            name="Old Name",
            email="old@example.com",
            phone="+441111111111",
            postcode="AA1 1AA",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Corrected Name",
            email="corrected@example.com",
            phone="+449998887766",
            postcode="ZZ9 9ZZ",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            assigned_to_id=user.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.FACEBOOK,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        sync_customer_contact_from_lead_on_qualify(session, lead)
        session.commit()
        session.refresh(customer)

        assert customer.name == "Corrected Name"
        assert customer.email == "corrected@example.com"
        assert customer.phone == "+449998887766"
        assert customer.postcode == "ZZ9 9ZZ"


def test_sync_skips_phone_when_lead_phone_empty_but_updates_other_fields(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = User(
            email="u-qphone2@example.com",
            hashed_password="x",
            full_name="Sales",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-2026-902",
            name="John",
            email="j@example.com",
            phone="+441234567890",
            postcode="WA1 1AA",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="John Updated",
            email="j@example.com",
            phone=None,
            postcode="WA1 1AA",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            assigned_to_id=user.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.FACEBOOK,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        sync_customer_contact_from_lead_on_qualify(session, lead)
        session.commit()
        session.refresh(customer)

        assert customer.phone == "+441234567890"
        assert customer.name == "John Updated"


def test_auto_transition_to_qualified_syncs_customer_phone(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = User(
            email="u-qphone3@example.com",
            hashed_password="x",
            full_name="Sales",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-2026-903",
            name="Alex",
            email="alex@example.com",
            phone="+441111000000",
            postcode="M1 1AE",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Alex",
            email="alex@example.com",
            phone="+447700900123",
            postcode="M1 1AE",
            status=LeadStatus.ENGAGED,
            customer_id=customer.id,
            assigned_to_id=user.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.FACEBOOK,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        ok = auto_transition_lead_status(
            lead.id, LeadStatus.QUALIFIED, session, user.id, "Test qualify"
        )
        assert ok is True

        session.refresh(lead)
        session.refresh(customer)
        assert lead.status == LeadStatus.QUALIFIED
        assert customer.phone == "+447700900123"


def test_patch_qualified_lead_email_syncs_customer(leads_api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = User(
            email="dir-patch-lead@example.com",
            hashed_password="x",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)

        customer = Customer(
            customer_number="CUST-PATCH-1",
            name="Pat",
            email="pat-old@example.com",
            phone="+441200000001",
            postcode="B1 1AA",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Pat",
            email="pat-old@example.com",
            phone="+441200000001",
            postcode="B1 1AA",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            assigned_to_id=director.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.FACEBOOK,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        cid = customer.id
        token = create_access_token(data={"sub": director.email})

    r = leads_api_client.patch(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "pat-synced@example.com"},
    )
    assert r.status_code == 200

    with Session(sqlite_engine) as session:
        c = session.get(Customer, cid)
        assert c is not None
        assert c.email == "pat-synced@example.com"
