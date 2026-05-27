"""Tests for order travel_time_hours_one_way and production webhook round-trip payload."""
import os

# Must be set before app.database is imported (default URL is PostgreSQL).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    Order,
    OrderItem,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import orders as orders_router


@pytest.fixture(name="engine")
def fixture_engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(name="seeded_session")
def fixture_seeded_session(engine):
    with Session(engine) as session:
        user = User(
            email="test-orders@example.com",
            hashed_password="dummy",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-TT-001",
            name="Test Customer",
            address_line1="1 Test Street",
            city="Testville",
            postcode="TE1 1ST",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            lead_id=None,
            quote_number="QT-TT-001",
            version=1,
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-TT-001",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
            deposit_paid=True,
            travel_time_hours_one_way=Decimal("1.25"),
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        item = OrderItem(
            order_id=order.id,
            description="Test product",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
            discount_amount=Decimal("0"),
            final_line_total=Decimal("100.00"),
            sort_order=0,
            is_custom=True,
        )
        session.add(item)
        session.commit()

        yield session, user, order


def _make_test_app(engine, user: User):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(orders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_patch_order_sets_travel_time_hours_one_way(engine, seeded_session):
    session, user, order = seeded_session
    app = _make_test_app(engine, user)
    client = TestClient(app)

    res = client.patch(
        f"/api/orders/{order.id}",
        json={"travel_time_hours_one_way": "2.5"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["travel_time_hours_one_way"] is not None
    assert float(data["travel_time_hours_one_way"]) == 2.5

    with Session(engine) as s2:
        o = s2.get(Order, order.id)
        assert o is not None
        assert o.travel_time_hours_one_way == Decimal("2.5")


def test_send_to_production_includes_round_trip_when_travel_time_set(engine, seeded_session):
    session, user, order = seeded_session
    app = _make_test_app(engine, user)
    captured = {}

    class MockResponse:
        content = b"{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["payload"] = json
            return MockResponse()

    with patch.dict(
        os.environ,
        {
            "PRODUCTION_APP_API_URL": "https://production.example",
            "PRODUCTION_APP_API_KEY": "test-api-key",
        },
    ):
        with patch("app.routers.orders.httpx.AsyncClient", MockAsyncClient):
            client = TestClient(app)
            res = client.post(f"/api/orders/{order.id}/send-to-production")

    assert res.status_code == 200
    assert captured["payload"] is not None
    assert captured["payload"]["travel_time_hours_round_trip"] == pytest.approx(2.5)
    assert captured["payload"]["deposit_paid"] is True
    assert captured["payload"]["balance_paid"] is False
    assert captured["payload"]["paid_in_full"] is False
    assert captured["payload"]["deposit_amount"] == 50.0
    assert captured["payload"]["balance_amount"] == 50.0
    # one-way stored as 1.25 -> round trip 2.5
    assert float(order.travel_time_hours_one_way) == 1.25


def test_send_to_production_omits_round_trip_when_travel_time_null(engine, seeded_session):
    session, user, order = seeded_session
    order.travel_time_hours_one_way = None
    session.add(order)
    session.commit()

    app = _make_test_app(engine, user)
    captured = {}

    class MockResponse:
        content = b"{}"

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["payload"] = json
            return MockResponse()

    with patch.dict(
        os.environ,
        {
            "PRODUCTION_APP_API_URL": "https://production.example",
            "PRODUCTION_APP_API_KEY": "test-api-key",
        },
    ):
        with patch("app.routers.orders.httpx.AsyncClient", MockAsyncClient):
            client = TestClient(app)
            res = client.post(f"/api/orders/{order.id}/send-to-production")

    assert res.status_code == 200
    assert "travel_time_hours_round_trip" not in captured["payload"]
    assert captured["payload"]["deposit_paid"] is True
    assert captured["payload"]["deposit_amount"] == 50.0
