"""POST /api/quotes/{id}/ensure-order recreates a missing order for accepted quotes."""
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
from app.models import Customer, Order, OrderItem, Quote, QuoteItem, QuoteStatus, User, UserRole
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
            email="quote-order-repair@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-TEST-ORDER",
            name="Repair Test Customer",
            email="repair@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-REPAIR-001",
            status=QuoteStatus.ACCEPTED,
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
                description="Test building",
                quantity=Decimal("1.00"),
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
                discount_amount=Decimal("0.00"),
                final_line_total=Decimal("100.00"),
                sort_order=0,
                is_custom=True,
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            user = session.exec(select(User).where(User.email == "quote-order-repair@example.com")).first()
            assert user is not None
            return user

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "quote-order-repair@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_ensure_order_recreates_missing_order_for_accepted_quote(api_client, sqlite_engine):
    response = api_client.post("/api/quotes/1/ensure-order", headers=_auth_headers(sqlite_engine))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ACCEPTED"
    assert payload["order_id"] is not None

    with Session(sqlite_engine) as session:
        order = session.exec(select(Order).where(Order.quote_id == 1)).first()
        assert order is not None
        assert order.customer_id == 1

        order_items = session.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all()
        assert len(order_items) == 1
        assert order_items[0].description == "Test building"
