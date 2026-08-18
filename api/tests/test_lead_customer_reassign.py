"""POST /api/leads/{id}/reassign-customer unlinks or points the lead at another customer."""
import os
import uuid
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.models import (
    Activity,
    Customer,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import leads as leads_router


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


def _add_user(session: Session, role: UserRole = UserRole.DIRECTOR) -> User:
    user = User(
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="Staff",
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_customer(session: Session, **kwargs) -> Customer:
    customer = Customer(
        customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
        **kwargs,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def _token(user: User) -> str:
    return create_access_token(data={"sub": user.email})


def test_unlink_creates_new_customer_even_when_phone_matches(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _add_user(session)
        old = _add_customer(
            session,
            name="Old Customer",
            email="old@example.com",
            phone="+447700900456",
        )
        lead = Lead(
            name="New Person",
            email="new@example.com",
            phone="07700900456",
            status=LeadStatus.NEW,
            customer_id=old.id,
            assigned_to_id=user.id,
            lead_source=LeadSource.REFERRAL,
            lead_type=LeadType.STABLES,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lead_id = lead.id
        old_id = old.id
        token = _token(user)

    r = api_client.post(
        f"/api/leads/{lead_id}/reassign-customer",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_id"] != old_id
    assert data["customer"]["name"] == "New Person"
    assert data["customer"]["email"] == "new@example.com"

    with Session(sqlite_engine) as session:
        remaining_old = session.get(Customer, old_id)
        assert remaining_old is not None
        assert remaining_old.name == "Old Customer"
        notes = list(session.exec(select(Activity).where(Activity.customer_id == old_id)).all())
        assert any("unlinked" in (a.notes or "") for a in notes)


def test_reassign_moves_this_lead_quotes_only(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _add_user(session)
        old = _add_customer(session, name="Old", email="old@example.com", phone="+447700900111")
        target = _add_customer(session, name="Target", email="target@example.com", phone="+447700900222")
        lead = Lead(
            name="Pat",
            email="pat@example.com",
            phone="+447700900333",
            status=LeadStatus.QUALIFIED,
            customer_id=old.id,
            assigned_to_id=user.id,
            lead_source=LeadSource.REFERRAL,
            lead_type=LeadType.SHEDS,
        )
        other_lead = Lead(
            name="Other",
            status=LeadStatus.QUALIFIED,
            customer_id=old.id,
            assigned_to_id=user.id,
        )
        session.add(lead)
        session.add(other_lead)
        session.commit()
        session.refresh(lead)
        session.refresh(other_lead)

        this_quote = Quote(
            quote_number="QT-REASSIGN-1",
            customer_id=old.id,
            lead_id=lead.id,
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("10"),
            total_amount=Decimal("10"),
            created_by_id=user.id,
        )
        other_quote = Quote(
            quote_number="QT-REASSIGN-2",
            customer_id=old.id,
            lead_id=other_lead.id,
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("20"),
            total_amount=Decimal("20"),
            created_by_id=user.id,
        )
        session.add(this_quote)
        session.add(other_quote)
        session.commit()
        session.refresh(this_quote)
        session.refresh(other_quote)

        lead_id = lead.id
        target_id = target.id
        old_id = old.id
        this_quote_id = this_quote.id
        other_quote_id = other_quote.id
        token = _token(user)

    r = api_client.post(
        f"/api/leads/{lead_id}/reassign-customer",
        headers={"Authorization": f"Bearer {token}"},
        json={"customer_id": target_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["customer_id"] == target_id

    with Session(sqlite_engine) as session:
        moved = session.get(Quote, this_quote_id)
        stayed = session.get(Quote, other_quote_id)
        assert moved is not None and moved.customer_id == target_id
        assert stayed is not None and stayed.customer_id == old_id


def test_reassign_same_customer_rejected(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _add_user(session)
        customer = _add_customer(session, name="Same", email="same@example.com")
        lead = Lead(
            name="Same",
            email="same@example.com",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=user.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lead_id = lead.id
        customer_id = customer.id
        token = _token(user)

    r = api_client.post(
        f"/api/leads/{lead_id}/reassign-customer",
        headers={"Authorization": f"Bearer {token}"},
        json={"customer_id": customer_id},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "ALREADY_LINKED"


def test_closer_can_reassign(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_user(session, UserRole.CLOSER)
        old = _add_customer(session, name="Old", phone="+447700900001")
        lead = Lead(
            name="Walk-in",
            phone="+447700900002",
            status=LeadStatus.QUALIFIED,
            customer_id=old.id,
            assigned_to_id=closer.id,
            lead_source=LeadSource.REFERRAL,
            lead_type=LeadType.CABINS,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lead_id = lead.id
        old_id = old.id
        token = _token(closer)

    r = api_client.post(
        f"/api/leads/{lead_id}/reassign-customer",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["customer_id"] != old_id
