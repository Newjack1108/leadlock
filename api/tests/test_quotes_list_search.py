"""GET /api/quotes search by customer name, dealer name, quote #."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token, get_current_user
from app.database import get_session
from app.models import Customer, Quote, QuoteStatus, User, UserRole
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
            email="quotes-search@example.com",
            hashed_password="x",
            full_name="Test",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-SEARCH-001",
            name="Alice Smith",
            phone="+447700900001",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        # ACCEPTED — excluded from lifecycle=live without search
        session.add(
            Quote(
                quote_number="QT-SEARCH-ACCEPTED",
                status=QuoteStatus.ACCEPTED,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                customer_id=customer.id,
                accepted_at=datetime.utcnow(),
            )
        )
        # SENT but past valid_until — also excluded from live
        session.add(
            Quote(
                quote_number="QT-SEARCH-EXPIRED-VALID",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                customer_id=customer.id,
                sent_at=datetime.utcnow() - timedelta(days=40),
                valid_until=datetime.utcnow() - timedelta(days=1),
            )
        )
        # Dealer quote with no Customer row — name only on dealer_customer_name
        session.add(
            Quote(
                quote_number="QT-SEARCH-DEALER",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                dealer_customer_name="Bob DealerClient",
                sent_at=datetime.utcnow(),
            )
        )
        # Unrelated quote
        session.add(
            Quote(
                quote_number="QT-SEARCH-OTHER",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "quotes-search@example.com")).first()
            assert u is not None
            return u

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "quotes-search@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_search_customer_name_finds_quotes_excluded_from_live(api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)

    live = api_client.get(
        "/api/quotes",
        params={"lifecycle": "live"},
        headers=headers,
    )
    assert live.status_code == 200
    live_numbers = {q["quote_number"] for q in live.json()["items"]}
    assert "QT-SEARCH-ACCEPTED" not in live_numbers
    assert "QT-SEARCH-EXPIRED-VALID" not in live_numbers

    r = api_client.get(
        "/api/quotes",
        params={"lifecycle": "live", "search": "Smith"},
        headers=headers,
    )
    assert r.status_code == 200
    numbers = {q["quote_number"] for q in r.json()["items"]}
    assert "QT-SEARCH-ACCEPTED" in numbers
    assert "QT-SEARCH-EXPIRED-VALID" in numbers
    assert "QT-SEARCH-OTHER" not in numbers


def test_search_dealer_customer_name(api_client, sqlite_engine):
    r = api_client.get(
        "/api/quotes",
        params={"search": "DealerClient"},
        headers=_auth_headers(sqlite_engine),
    )
    assert r.status_code == 200
    numbers = {q["quote_number"] for q in r.json()["items"]}
    assert numbers == {"QT-SEARCH-DEALER"}


def test_search_quote_number_still_works(api_client, sqlite_engine):
    r = api_client.get(
        "/api/quotes",
        params={"search": "QT-SEARCH-OTHER"},
        headers=_auth_headers(sqlite_engine),
    )
    assert r.status_code == 200
    numbers = {q["quote_number"] for q in r.json()["items"]}
    assert numbers == {"QT-SEARCH-OTHER"}
