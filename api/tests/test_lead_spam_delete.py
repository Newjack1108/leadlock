"""Spam lead delete: cascade helper and DELETE /api/leads/{id} guards."""
import os
from decimal import Decimal

# Avoid importing app.database before a SQLite URL exists (no Postgres in CI / local pytest).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.routers import leads as leads_router
from app.lead_delete import delete_lead_cascade
from app.models import (
    Customer,
    Lead,
    LeadStatus,
    Order,
    Quote,
    QuoteStatus,
    StatusHistory,
    User,
    UserRole,
)


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401 — register all SQLModel tables before create_all

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def api_client(sqlite_engine):
    """Mini app: only leads router (avoids importing full app.main → reportlab, etc.)."""
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


def _add_director(session: Session) -> User:
    user = User(
        email="director-spam-del@example.com",
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
        email="closer-spam-del@example.com",
        hashed_password="x",
        full_name="Closer",
        role=UserRole.CLOSER,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_delete_lead_cascade_removes_draft_quote_and_history(sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        lead = Lead(name="Spam", status=LeadStatus.NEW, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        session.add(
            StatusHistory(
                lead_id=lead.id,
                new_status=LeadStatus.NEW,
                changed_by_id=director.id,
            )
        )
        quote = Quote(
            quote_number="QT-SPAM-1",
            lead_id=lead.id,
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("1.00"),
            total_amount=Decimal("1.00"),
            created_by_id=director.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        delete_lead_cascade(session, lead.id)
        session.commit()

        assert session.get(Lead, lead.id) is None
        assert session.get(Quote, quote.id) is None
        assert session.exec(select(StatusHistory).where(StatusHistory.lead_id == lead.id)).first() is None


def test_delete_spam_lead_204_for_eligible_lead(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        lead = Lead(name="Junk", status=LeadStatus.NEW, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is None


def test_delete_spam_lead_403_for_closer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_closer(session)
        director = _add_director(session)
        lead = Lead(name="X", status=LeadStatus.NEW, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        token = create_access_token(data={"sub": closer.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is not None


def test_delete_spam_lead_400_when_qualified(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        customer = Customer(
            customer_number="CUST-DEL-1",
            name="C",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="X",
            status=LeadStatus.QUALIFIED,
            assigned_to_id=director.id,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        cid = customer.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "engaged" in r.json()["detail"].lower() or "qualified" in r.json()["detail"].lower()

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is not None
        assert session.get(Customer, cid) is not None


def test_delete_spam_lead_204_new_lead_with_outreach_customer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        customer = Customer(
            customer_number="CUST-SPAM-ORPHAN",
            name="Spam Inbound",
            email="spam@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Spam Inbound",
            status=LeadStatus.NEW,
            assigned_to_id=director.id,
            customer_id=customer.id,
            email="spam@example.com",
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        cid = customer.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is None
        assert session.get(Customer, cid) is None


def test_delete_spam_lead_204_engaged_with_customer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        customer = Customer(customer_number="CUST-SPAM-ENG", name="Engaged Spam")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Engaged Spam",
            status=LeadStatus.ENGAGED,
            assigned_to_id=director.id,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lid = lead.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is None


def test_delete_spam_lead_keeps_customer_when_other_leads_remain(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        customer = Customer(customer_number="CUST-SPAM-SHARED", name="Shared")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead_a = Lead(
            name="Spam A",
            status=LeadStatus.NEW,
            assigned_to_id=director.id,
            customer_id=customer.id,
        )
        lead_b = Lead(
            name="Real B",
            status=LeadStatus.ENGAGED,
            assigned_to_id=director.id,
            customer_id=customer.id,
        )
        session.add(lead_a)
        session.add(lead_b)
        session.commit()
        session.refresh(lead_a)
        session.refresh(lead_b)
        lid_a = lead_a.id
        cid = customer.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid_a) is None
        assert session.get(Customer, cid) is not None
        remaining = session.exec(select(Lead).where(Lead.customer_id == cid)).all()
        assert len(remaining) == 1
        assert remaining[0].name == "Real B"


def test_delete_spam_lead_400_when_non_draft_quote(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        lead = Lead(name="X", status=LeadStatus.ENGAGED, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            quote_number="QT-SPAM-2",
            lead_id=lead.id,
            status=QuoteStatus.SENT,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("10.00"),
            created_by_id=director.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(lead)

        lid = lead.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "draft" in r.json()["detail"].lower()

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is not None


def test_delete_spam_lead_400_when_order_on_draft_quote(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_director(session)
        lead = Lead(name="X", status=LeadStatus.NEW, assigned_to_id=director.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            quote_number="QT-SPAM-3",
            lead_id=lead.id,
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("10.00"),
            total_amount=Decimal("10.00"),
            created_by_id=director.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            order_number="ORD-SPAM-1",
            subtotal=Decimal("10.00"),
            total_amount=Decimal("10.00"),
            created_by_id=director.id,
        )
        session.add(order)
        session.commit()

        lid = lead.id
        token = create_access_token(data={"sub": director.email})

    r = api_client.delete(
        f"/api/leads/{lid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "order" in r.json()["detail"].lower()

    with Session(sqlite_engine) as session:
        assert session.get(Lead, lid) is not None
