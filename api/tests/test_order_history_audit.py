"""Order audit events should surface in customer history."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.database import get_session
from app.models import Customer, Order, OrderAuditEvent, Quote, QuoteItem, QuoteStatus, User, UserRole
from app.routers import customers as customers_router
from app.routers import orders as orders_router
from app.routers import public as public_router
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
    app.include_router(orders_router.router)
    app.include_router(customers_router.router)
    app.include_router(public_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="order-history-audit@example.com",
            hashed_password="x",
            full_name="Audit Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            user = session.exec(select(User).where(User.email == "order-history-audit@example.com")).first()
            assert user is not None
            return user

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "order-history-audit@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _seed_accepted_quote(sqlite_engine, suffix: str) -> tuple[int, int]:
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "order-history-audit@example.com")).first()
        assert user is not None

        customer = Customer(
            customer_number=f"CUST-AUD-{suffix}",
            name=f"Audit Customer {suffix}",
            email=f"audit-{suffix}@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number=f"QT-AUD-{suffix}",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("60.00"),
            created_by_id=user.id,
            accepted_at=datetime.utcnow(),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteItem(
                quote_id=quote.id,
                description="Audit building",
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
        return customer.id, quote.id


def test_order_created_event_appears_in_customer_history(api_client, sqlite_engine):
    customer_id, quote_id = _seed_accepted_quote(sqlite_engine, "CREATE")

    response = api_client.post(f"/api/quotes/{quote_id}/ensure-order", headers=_auth_headers(sqlite_engine))
    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] is not None

    history = api_client.get(f"/api/customers/{customer_id}/history", headers=_auth_headers(sqlite_engine))
    assert history.status_code == 200
    events = history.json()["events"]

    created_events = [event for event in events if event["event_type"] == "ORDER_CREATED"]
    assert len(created_events) == 1
    assert created_events[0]["metadata"]["quote_number"] == f"QT-AUD-CREATE"
    assert created_events[0]["metadata"]["order_number"].startswith("ORD-")


def test_order_removed_event_survives_after_delete(api_client, sqlite_engine):
    customer_id, quote_id = _seed_accepted_quote(sqlite_engine, "DELETE")
    ensure = api_client.post(f"/api/quotes/{quote_id}/ensure-order", headers=_auth_headers(sqlite_engine))
    order_id = ensure.json()["order_id"]

    delete_response = api_client.delete(f"/api/orders/{order_id}", headers=_auth_headers(sqlite_engine))
    assert delete_response.status_code == 204

    with Session(sqlite_engine) as session:
        order = session.get(Order, order_id)
        assert order is None
        removed_event = session.exec(
            select(OrderAuditEvent).where(OrderAuditEvent.customer_id == customer_id, OrderAuditEvent.event_type == "ORDER_REMOVED")
        ).first()
        assert removed_event is not None
        assert removed_event.details["order_number"].startswith("ORD-")

    history = api_client.get(f"/api/customers/{customer_id}/history", headers=_auth_headers(sqlite_engine))
    assert history.status_code == 200
    assert any(event["event_type"] == "ORDER_REMOVED" for event in history.json()["events"])


def test_order_operational_events_appear_in_customer_history(api_client, sqlite_engine):
    customer_id, quote_id = _seed_accepted_quote(sqlite_engine, "OPS")
    ensure = api_client.post(f"/api/quotes/{quote_id}/ensure-order", headers=_auth_headers(sqlite_engine))
    order_id = ensure.json()["order_id"]

    update_response = api_client.patch(
        f"/api/orders/{order_id}",
        json={"deposit_paid": True, "installation_booked": True},
        headers=_auth_headers(sqlite_engine),
    )
    assert update_response.status_code == 200

    access_sheet = api_client.post(
        f"/api/orders/{order_id}/access-sheet/send",
        headers=_auth_headers(sqlite_engine),
    )
    assert access_sheet.status_code == 200
    token = access_sheet.json()["access_token"]

    submit = api_client.post(
        f"/api/public/access-sheet/{token}",
        json={"site_level": "yes", "area_clear": "yes"},
    )
    assert submit.status_code == 200

    history = api_client.get(f"/api/customers/{customer_id}/history", headers=_auth_headers(sqlite_engine))
    assert history.status_code == 200
    event_types = {event["event_type"] for event in history.json()["events"]}

    assert "ORDER_PAYMENT_UPDATED" in event_types
    assert "ORDER_INSTALLATION_UPDATED" in event_types
    assert "ORDER_ACCESS_SHEET_SENT" in event_types
    assert "ORDER_ACCESS_SHEET_COMPLETED" in event_types
