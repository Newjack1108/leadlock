"""Accepting a quote promotes QUALIFIED (deferred) and QUOTED leads to WON."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.database import get_session
from app.models import (
    Customer,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    OpportunityStage,
    Quote,
    QuoteItem,
    QuoteStatus,
    StatusHistory,
    User,
    UserRole,
)
from app.routers import quotes as quotes_router


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


def _seed(engine, *, lead_status: LeadStatus, opportunity: bool = False):
    with Session(engine) as session:
        user = User(
            email="quote-accept-won@example.com",
            hashed_password="x",
            full_name="Accept Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-ACCEPT-WON",
            name="Accept Won Customer",
            email="accept-won@example.com",
            phone="+441234567890",
            postcode="AB1 2CD",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Accept Won Lead",
            email="accept-won@example.com",
            phone="+441234567890",
            postcode="AB1 2CD",
            status=lead_status,
            customer_id=customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.UNKNOWN,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead.id,
            quote_number="QT-ACCEPT-WON-001",
            status=QuoteStatus.DRAFT,
            opportunity_stage=OpportunityStage.CONCEPT if opportunity else None,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("60.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteItem(
                quote_id=quote.id,
                description="Gate",
                quantity=1,
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
                discount_amount=Decimal("0.00"),
                final_line_total=Decimal("100.00"),
                sort_order=0,
                is_custom=True,
            )
        )
        session.commit()
        return user.id, customer.id, lead.id, quote.id


@pytest.fixture()
def api_client(sqlite_engine):
    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(
                select(User).where(User.email == "quote-accept-won@example.com")
            ).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client, sqlite_engine
    app.dependency_overrides.clear()


def _auth_headers(engine):
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.email == "quote-accept-won@example.com")
        ).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _lead_status(engine, lead_id: int) -> LeadStatus:
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        assert lead is not None
        return lead.status


def _status_history(engine, lead_id: int):
    with Session(engine) as session:
        rows = session.exec(
            select(StatusHistory)
            .where(StatusHistory.lead_id == lead_id)
            .order_by(StatusHistory.id)
        ).all()
        return [(r.old_status, r.new_status) for r in rows]


def test_accept_draft_promotes_qualified_lead_to_won(api_client):
    """Deferred create-from-lead leave lead QUALIFIED; accept must still win it."""
    client, engine = api_client
    _user_id, _customer_id, lead_id, quote_id = _seed(engine, lead_status=LeadStatus.QUALIFIED)
    headers = _auth_headers(engine)

    res = client.patch(
        f"/api/quotes/{quote_id}",
        headers=headers,
        json={"status": "ACCEPTED"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ACCEPTED"
    assert res.json()["order_id"] is not None
    assert _lead_status(engine, lead_id) == LeadStatus.WON
    assert _status_history(engine, lead_id) == [
        (LeadStatus.QUALIFIED, LeadStatus.QUOTED),
        (LeadStatus.QUOTED, LeadStatus.WON),
    ]


def test_accept_promotes_quoted_lead_to_won(api_client):
    client, engine = api_client
    _user_id, _customer_id, lead_id, quote_id = _seed(engine, lead_status=LeadStatus.QUOTED)
    headers = _auth_headers(engine)

    res = client.patch(
        f"/api/quotes/{quote_id}",
        headers=headers,
        json={"status": "ACCEPTED"},
    )
    assert res.status_code == 200, res.text
    assert _lead_status(engine, lead_id) == LeadStatus.WON
    assert _status_history(engine, lead_id) == [
        (LeadStatus.QUOTED, LeadStatus.WON),
    ]


def test_mark_opportunity_won_promotes_qualified_lead(api_client):
    client, engine = api_client
    _user_id, _customer_id, lead_id, quote_id = _seed(
        engine, lead_status=LeadStatus.QUALIFIED, opportunity=True
    )
    headers = _auth_headers(engine)

    res = client.post(
        f"/api/quotes/opportunities/{quote_id}/won",
        headers=headers,
        json={},
    )
    assert res.status_code == 200, res.text
    assert _lead_status(engine, lead_id) == LeadStatus.WON
