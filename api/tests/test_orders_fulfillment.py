"""Tests for order fulfillment_method and production webhook."""
import os

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
    QuoteFulfillmentMethod,
    QuoteItem,
    QuoteItemLineType,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import orders as orders_router
from app.routers import quotes as quotes_router


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
            email="test-fulfillment@example.com",
            hashed_password="dummy",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-FF-001",
            name="Test Customer",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            lead_id=None,
            quote_number="QT-FF-001",
            version=1,
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
            fulfillment_method=QuoteFulfillmentMethod.COLLECTION,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-FF-001",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
            deposit_paid=True,
            fulfillment_method=QuoteFulfillmentMethod.COLLECTION,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        item = OrderItem(
            order_id=order.id,
            description="Stable",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
            discount_amount=Decimal("0"),
            final_line_total=Decimal("100.00"),
            sort_order=0,
            is_custom=False,
        )
        session.add(item)
        session.commit()

        yield session, user, order, customer, quote


@pytest.fixture(name="client")
def fixture_client(engine, seeded_session):
    session, user, *_ = seeded_session

    def override_get_session():
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(orders_router.router)
    app.include_router(quotes_router.router)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: user

    with TestClient(app) as c:
        yield c


def test_create_order_from_quote_copies_fulfillment(engine, seeded_session):
    session, user, order, customer, quote = seeded_session
    from app.routers.quotes import create_order_from_quote

    quote2 = Quote(
        customer_id=customer.id,
        lead_id=None,
        quote_number="QT-FF-002",
        version=1,
        status=QuoteStatus.ACCEPTED,
        subtotal=Decimal("50.00"),
        discount_total=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        deposit_amount=Decimal("25.00"),
        balance_amount=Decimal("25.00"),
        currency="GBP",
        created_by_id=user.id,
        fulfillment_method=QuoteFulfillmentMethod.COLLECTION,
    )
    session.add(quote2)
    session.commit()
    session.refresh(quote2)

    created = create_order_from_quote(quote2, session, user.id)
    session.commit()
    session.refresh(created)
    assert created.fulfillment_method == QuoteFulfillmentMethod.COLLECTION


def test_collection_quote_rejects_delivery_line(client, seeded_session):
    session, user, _, customer, _ = seeded_session
    from sqlmodel import select
    from app.models import Lead, LeadStatus, LeadType

    lead = Lead(
        name="Test Lead",
        customer_id=customer.id,
        status=LeadStatus.QUALIFIED,
        lead_type=LeadType.STABLES,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)

    res = client.post(
        "/api/quotes",
        json={
            "customer_id": customer.id,
            "lead_id": lead.id,
            "items": [
                {
                    "description": "Delivery only",
                    "quantity": 1,
                    "unit_price": 100,
                    "is_custom": True,
                    "line_type": "DELIVERY",
                }
            ],
            "fulfillment_method": "COLLECTION",
        },
    )
    assert res.status_code == 400
    assert "collection" in res.json()["detail"].lower()


@patch.dict(os.environ, {"PRODUCTION_APP_API_URL": "https://prod.example", "PRODUCTION_APP_API_KEY": "key"})
def test_send_to_production_collection_skips_address_and_includes_fulfillment(client, seeded_session):
    session, user, order, customer, quote = seeded_session

    captured = {}

    class FakeResponse:
        status_code = 200
        content = b'{"ok": true}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json=None, headers=None):
            captured["payload"] = json
            return FakeResponse()

    with patch("app.routers.orders.httpx.AsyncClient", FakeClient):
        res = client.post(f"/api/orders/{order.id}/send-to-production")

    assert res.status_code == 200
    assert captured["payload"]["fulfillment_method"] == "collection"
    assert "travel_time_hours_round_trip" not in captured["payload"]
