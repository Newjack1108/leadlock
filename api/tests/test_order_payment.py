"""Payment-flag reconcile on CRM PATCH and list filters."""
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
from app.models import Customer, Order, Quote, QuoteStatus, User, UserRole
from app.order_payment import (
    is_deposit_paid,
    is_paid_in_full,
    reconcile_payment_flags_from_update,
)
from app.routers import orders as orders_router


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
    app.include_router(orders_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="order-payment@example.com",
            hashed_password="x",
            full_name="Payment Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "order-payment@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_order(
    sqlite_engine,
    suffix: str,
    *,
    deposit_paid: bool = False,
    balance_paid: bool = False,
    paid_in_full: bool = False,
) -> int:
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "order-payment@example.com")).first()
        assert user is not None
        customer = Customer(
            customer_number=f"CUST-PAY-{suffix}",
            name=f"Pay Customer {suffix}",
            email=f"pay-{suffix}@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        quote = Quote(
            customer_id=customer.id,
            quote_number=f"QT-PAY-{suffix}",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("40.00"),
            created_by_id=user.id,
            accepted_at=datetime.utcnow(),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number=f"ORD-PAY-{suffix}",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("40.00"),
            created_by_id=user.id,
            deposit_paid=deposit_paid,
            balance_paid=balance_paid,
            paid_in_full=paid_in_full,
            created_at=datetime.utcnow(),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id


def test_is_deposit_paid_and_is_paid_in_full_helpers():
    assert is_deposit_paid(deposit_paid=True) is True
    assert is_deposit_paid(paid_in_full=True) is True
    assert is_deposit_paid(balance_paid=True) is True
    assert is_deposit_paid() is False
    assert is_paid_in_full(paid_in_full=True) is True
    assert is_paid_in_full(balance_paid=True) is True
    assert is_paid_in_full() is False
    assert is_paid_in_full(balance_paid=False, paid_in_full=False) is False


def test_reconcile_marking_paid_in_full_sets_all_three():
    update = {"paid_in_full": True}
    reconcile_payment_flags_from_update(update, {"deposit_paid": False, "balance_paid": False, "paid_in_full": False})
    assert update == {"deposit_paid": True, "balance_paid": True, "paid_in_full": True}


def test_reconcile_clearing_paid_in_full_keeps_deposit():
    update = {"paid_in_full": False}
    reconcile_payment_flags_from_update(
        update,
        {"deposit_paid": True, "balance_paid": True, "paid_in_full": True},
    )
    assert update["paid_in_full"] is False
    assert update["balance_paid"] is False
    assert update["deposit_paid"] is True


def test_reconcile_clearing_deposit_while_paid_in_full_clears_all():
    update = {"deposit_paid": False}
    reconcile_payment_flags_from_update(
        update,
        {"deposit_paid": True, "balance_paid": True, "paid_in_full": True},
    )
    assert update == {"deposit_paid": False, "balance_paid": False, "paid_in_full": False}


def test_patch_paid_in_full_true_sets_all_three_and_invoice(api_client, sqlite_engine):
    order_id = _seed_order(sqlite_engine, "mark")
    res = api_client.patch(f"/api/orders/{order_id}", json={"paid_in_full": True})
    assert res.status_code == 200
    body = res.json()
    assert body["deposit_paid"] is True
    assert body["balance_paid"] is True
    assert body["paid_in_full"] is True
    assert body["invoice_number"] is not None

    with Session(sqlite_engine) as session:
        order = session.get(Order, order_id)
        assert order.deposit_paid is True
        assert order.balance_paid is True
        assert order.paid_in_full is True
        assert order.invoice_number is not None


def test_patch_paid_in_full_false_clears_full_keeps_deposit(api_client, sqlite_engine):
    order_id = _seed_order(
        sqlite_engine,
        "clear",
        deposit_paid=True,
        balance_paid=True,
        paid_in_full=True,
    )
    res = api_client.patch(f"/api/orders/{order_id}", json={"paid_in_full": False})
    assert res.status_code == 200
    body = res.json()
    assert body["paid_in_full"] is False
    assert body["balance_paid"] is False
    assert body["deposit_paid"] is True


def test_list_filters_include_paid_in_full_only_rows(api_client, sqlite_engine):
    _seed_order(sqlite_engine, "newish")
    paid_id = _seed_order(
        sqlite_engine,
        "pif-only",
        deposit_paid=False,
        balance_paid=False,
        paid_in_full=True,
    )

    new_res = api_client.get("/api/orders", params={"status": "new"})
    assert new_res.status_code == 200
    new_numbers = {item["order_number"] for item in new_res.json()["items"]}
    assert "ORD-PAY-newish" in new_numbers
    assert "ORD-PAY-pif-only" not in new_numbers

    deposit_res = api_client.get("/api/orders", params={"status": "deposit_paid"})
    assert deposit_res.status_code == 200
    deposit_ids = {item["id"] for item in deposit_res.json()["items"]}
    assert paid_id in deposit_ids

    completed_res = api_client.get("/api/orders", params={"status": "completed"})
    assert completed_res.status_code == 200
    completed_ids = {item["id"] for item in completed_res.json()["items"]}
    assert paid_id in completed_ids
