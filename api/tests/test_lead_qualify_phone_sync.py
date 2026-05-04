"""When a lead becomes qualified, copy corrected lead phone to the linked customer (e.g. Facebook import)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Customer, Lead, LeadSource, LeadStatus, LeadType, User, UserRole
from app.workflow import auto_transition_lead_status, sync_customer_phone_from_lead_on_qualify


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


def test_sync_customer_phone_from_lead_on_qualify_overwrites_customer_phone(sqlite_engine):
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

        sync_customer_phone_from_lead_on_qualify(session, lead)
        session.commit()
        session.refresh(customer)

        assert customer.phone == "+449999888877"


def test_sync_skips_when_lead_phone_empty(sqlite_engine):
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
            name="John",
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

        sync_customer_phone_from_lead_on_qualify(session, lead)
        session.commit()
        session.refresh(customer)

        assert customer.phone == "+441234567890"


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
