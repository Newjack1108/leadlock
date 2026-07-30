"""Tests for production → LeadLock work-order status webhook."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PRODUCTION_APP_API_KEY", "prod-test-key")

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import (
    Customer,
    Order,
    OrderAuditEvent,
    Quote,
    QuoteFulfillmentMethod,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import webhooks as webhooks_router
from app.schemas import CustomerHistoryEventType


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
            email="status-webhook@example.com",
            hashed_password="dummy",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-WO-001",
            name="Status Customer",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            lead_id=None,
            quote_number="QT-WO-001",
            version=1,
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
            fulfillment_method=QuoteFulfillmentMethod.DELIVERY,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-WO-001",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
            deposit_paid=True,
            fulfillment_method=QuoteFulfillmentMethod.DELIVERY,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        yield session, user, order, customer, quote


@pytest.fixture(name="client")
def fixture_client(engine, seeded_session):
    def override_get_session():
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(webhooks_router.router)
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as c:
        yield c


def _auth_headers(key: str = "prod-test-key"):
    return {"Authorization": f"Bearer {key}"}


def test_work_order_status_rejects_missing_auth(client, seeded_session):
    _, _, order, *_ = seeded_session
    res = client.post(
        "/api/webhooks/work-orders/status",
        json={"order_id": order.id, "installation_completed": True},
    )
    assert res.status_code == 401


def test_work_order_status_rejects_bad_key(client, seeded_session):
    _, _, order, *_ = seeded_session
    res = client.post(
        "/api/webhooks/work-orders/status",
        json={"order_id": order.id, "installation_completed": True},
        headers=_auth_headers("wrong"),
    )
    assert res.status_code == 401


def test_work_order_status_unknown_order(client, seeded_session):
    res = client.post(
        "/api/webhooks/work-orders/status",
        json={"order_id": 999999, "installation_booked": True},
        headers=_auth_headers(),
    )
    assert res.status_code == 404


def test_work_order_status_scheduled_date_sets_booked(client, engine, seeded_session):
    _, _, order, *_ = seeded_session
    start = "2026-08-15T09:00:00"
    end = "2026-08-16T17:00:00"
    res = client.post(
        "/api/webhooks/work-orders/status",
        json={
            "order_id": order.id,
            "installation_scheduled_at": start,
            "installation_scheduled_end_at": end,
        },
        headers=_auth_headers(),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["updated"] is True
    assert body["order_id"] == order.id

    with Session(engine) as session:
        updated = session.get(Order, order.id)
        assert updated.installation_booked is True
        assert updated.installation_scheduled_at is not None
        assert updated.installation_scheduled_end_at is not None
        events = session.exec(
            select(OrderAuditEvent).where(
                OrderAuditEvent.order_id == order.id,
                OrderAuditEvent.event_type == CustomerHistoryEventType.ORDER_INSTALLATION_UPDATED.value,
            )
        ).all()
        assert len(events) == 1


def test_work_order_status_completion_triggers_side_effects(client, engine, seeded_session):
    _, _, order, *_ = seeded_session
    with patch("app.routers.webhooks.on_installation_completed") as mock_completed:
        res = client.post(
            "/api/webhooks/work-orders/status",
            json={"order_id": order.id, "installation_completed": True},
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        assert res.json()["updated"] is True
        mock_completed.assert_called_once()

    with Session(engine) as session:
        updated = session.get(Order, order.id)
        assert updated.installation_completed is True


def test_work_order_status_uncompletion_triggers_side_effects(client, engine, seeded_session):
    _, _, order, *_ = seeded_session
    with Session(engine) as session:
        db_order = session.get(Order, order.id)
        db_order.installation_completed = True
        db_order.installation_completed_at = datetime.utcnow()
        session.add(db_order)
        session.commit()

    with patch("app.routers.webhooks.on_installation_uncompleted") as mock_uncompleted:
        res = client.post(
            "/api/webhooks/work-orders/status",
            json={"order_id": order.id, "installation_completed": False},
            headers=_auth_headers(),
        )
        assert res.status_code == 200
        assert res.json()["updated"] is True
        mock_uncompleted.assert_called_once()


def test_work_order_status_idempotent_repeat(client, engine, seeded_session):
    _, _, order, *_ = seeded_session
    payload = {
        "order_id": order.id,
        "installation_booked": True,
        "installation_scheduled_at": "2026-08-15T09:00:00",
    }
    first = client.post(
        "/api/webhooks/work-orders/status",
        json=payload,
        headers=_auth_headers(),
    )
    assert first.status_code == 200
    assert first.json()["updated"] is True

    second = client.post(
        "/api/webhooks/work-orders/status",
        json=payload,
        headers=_auth_headers(),
    )
    assert second.status_code == 200
    assert second.json()["updated"] is False

    with Session(engine) as session:
        events = session.exec(
            select(OrderAuditEvent).where(
                OrderAuditEvent.order_id == order.id,
                OrderAuditEvent.event_type == CustomerHistoryEventType.ORDER_INSTALLATION_UPDATED.value,
            )
        ).all()
        assert len(events) == 1
