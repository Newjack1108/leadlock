"""POST /api/quotes/opportunities/{id}/reopen restores closed/lost quotes."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import (
    Lead,
    LeadStatus,
    LossCategory,
    OpportunityStage,
    Quote,
    QuoteStatus,
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


@pytest.fixture()
def api_client(sqlite_engine):
    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="quote-reopen@example.com",
            hashed_password="x",
            full_name="Test",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "quote-reopen@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client, sqlite_engine


def _user_id(engine) -> int:
    with Session(engine) as session:
        u = session.exec(select(User).where(User.email == "quote-reopen@example.com")).first()
        assert u is not None
        return u.id


def test_reopen_closed_quote(api_client):
    client, engine = api_client
    uid = _user_id(engine)
    with Session(engine) as session:
        quote = Quote(
            quote_number="QT-REOPEN-CLOSED",
            status=QuoteStatus.REJECTED,
            opportunity_stage=OpportunityStage.LOST,
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            created_by_id=uid,
            sent_at=datetime.utcnow(),
            rejected_by_id=uid,
            loss_reason="Another quote won",
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        quote_id = quote.id

    res = client.post(f"/api/quotes/opportunities/{quote_id}/reopen")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "SENT"
    assert body["opportunity_stage"] == "QUOTE_SENT"
    assert body["loss_reason"] is None
    assert body["loss_category"] is None

    with Session(engine) as session:
        q = session.get(Quote, quote_id)
        assert q is not None
        assert q.status == QuoteStatus.SENT
        assert q.rejected_by_id is None
        assert q.opportunity_stage == OpportunityStage.QUOTE_SENT


def test_reopen_lost_quote_restores_lead(api_client):
    from app.models import Customer

    client, engine = api_client
    uid = _user_id(engine)
    with Session(engine) as session:
        customer = Customer(
            customer_number="C-REOPEN-1",
            name="Reopen Customer",
            email="reopen@example.com",
            phone="07700900000",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        lead = Lead(name="Reopen Lead", status=LeadStatus.LOST, customer_id=customer.id)
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-REOPEN-LOST",
            status=QuoteStatus.REJECTED,
            opportunity_stage=OpportunityStage.LOST,
            subtotal=Decimal("200"),
            total_amount=Decimal("200"),
            created_by_id=uid,
            customer_id=customer.id,
            lead_id=lead.id,
            sent_at=datetime.utcnow(),
            viewed_at=datetime.utcnow(),
            loss_category=LossCategory.PRICE,
            loss_reason="Too expensive",
            rejected_by_id=uid,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        quote_id = quote.id
        lead_id = lead.id

    res = client.post(f"/api/quotes/opportunities/{quote_id}/reopen")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "VIEWED"
    assert body["loss_category"] is None

    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        assert lead is not None
        assert lead.status == LeadStatus.QUOTED


def test_reopen_rejects_non_rejected(api_client):
    client, engine = api_client
    uid = _user_id(engine)
    with Session(engine) as session:
        quote = Quote(
            quote_number="QT-REOPEN-SENT",
            status=QuoteStatus.SENT,
            subtotal=Decimal("50"),
            total_amount=Decimal("50"),
            created_by_id=uid,
            sent_at=datetime.utcnow(),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        quote_id = quote.id

    res = client.post(f"/api/quotes/opportunities/{quote_id}/reopen")
    assert res.status_code == 400
