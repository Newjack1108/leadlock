"""Customer history shows quote rejection reason and actor when known."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import customers as customers_router
from app.sms_quote_keyword_service import CLOSE_LOSS_REASON


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
    app.include_router(customers_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        session.add(
            User(
                email="reject-history@example.com",
                hashed_password="x",
                full_name="Reject Staff",
                role=UserRole.DIRECTOR,
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(
                select(User).where(User.email == "reject-history@example.com")
            ).first()
            assert u is not None
            return u

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_rejected_quote(
    session: Session,
    *,
    user: User,
    loss_reason: str | None,
    rejected_by_id: int | None,
    quote_number: str,
    customer_number: str,
) -> int:
    customer = Customer(
        customer_number=customer_number,
        name="Reject History Customer",
        email=f"{customer_number.lower()}@example.com",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        customer_id=customer.id,
        quote_number=quote_number,
        version=1,
        status=QuoteStatus.REJECTED,
        subtotal=Decimal("100.00"),
        discount_total=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        deposit_amount=Decimal("50.00"),
        balance_amount=Decimal("50.00"),
        currency="GBP",
        created_by_id=user.id,
        loss_reason=loss_reason,
        rejected_by_id=rejected_by_id,
    )
    session.add(quote)
    session.commit()
    return customer.id


def _rejected_event(history_json: dict, quote_number: str) -> dict:
    events = [
        e
        for e in history_json["events"]
        if e["event_type"] == "QUOTE_REJECTED"
        and (e.get("metadata") or {}).get("quote_number") == quote_number
    ]
    assert len(events) == 1
    return events[0]


def test_history_rejected_shows_staff_and_loss_reason(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(User).where(User.email == "reject-history@example.com")
        ).first()
        assert user is not None
        customer_id = _seed_rejected_quote(
            session,
            user=user,
            loss_reason="Chose competitor",
            rejected_by_id=user.id,
            quote_number="QT-REJ-STAFF",
            customer_number="CUST-REJ-STAFF",
        )

    r = api_client.get(f"/api/customers/{customer_id}/history")
    assert r.status_code == 200
    event = _rejected_event(r.json(), "QT-REJ-STAFF")
    assert "Chose competitor" in event["description"]
    assert event["created_by_name"] == "Reject Staff"
    assert event["created_by_id"] is not None
    assert event["metadata"]["loss_reason"] == "Chose competitor"


def test_history_rejected_sms_shows_customer_via_sms(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(User).where(User.email == "reject-history@example.com")
        ).first()
        assert user is not None
        customer_id = _seed_rejected_quote(
            session,
            user=user,
            loss_reason=CLOSE_LOSS_REASON,
            rejected_by_id=None,
            quote_number="QT-REJ-SMS",
            customer_number="CUST-REJ-SMS",
        )

    r = api_client.get(f"/api/customers/{customer_id}/history")
    assert r.status_code == 200
    event = _rejected_event(r.json(), "QT-REJ-SMS")
    assert CLOSE_LOSS_REASON in event["description"]
    assert event["created_by_name"] == "Customer via SMS"
    assert event["metadata"]["loss_reason"] == CLOSE_LOSS_REASON


def test_history_rejected_without_reason_or_actor(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(User).where(User.email == "reject-history@example.com")
        ).first()
        assert user is not None
        customer_id = _seed_rejected_quote(
            session,
            user=user,
            loss_reason=None,
            rejected_by_id=None,
            quote_number="QT-REJ-BLANK",
            customer_number="CUST-REJ-BLANK",
        )

    r = api_client.get(f"/api/customers/{customer_id}/history")
    assert r.status_code == 200
    event = _rejected_event(r.json(), "QT-REJ-BLANK")
    assert event["description"] == "Quote QT-REJ-BLANK was rejected"
    assert event["created_by_name"] is None
    assert event["metadata"].get("loss_reason") is None
