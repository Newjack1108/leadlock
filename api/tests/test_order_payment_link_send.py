"""Send payment link on orders — validation and delivery."""
import os
from unittest.mock import patch

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
from app.models import (
    Activity,
    ActivityType,
    Customer,
    Order,
    OrderAuditEvent,
    Quote,
    QuoteItem,
    QuoteStatus,
    SmsMessage,
    User,
    UserRole,
)
from app.routers import orders as orders_router
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

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="payment-link@example.com",
            hashed_password="x",
            full_name="Payment Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            user = session.exec(select(User).where(User.email == "payment-link@example.com")).first()
            assert user is not None
            return user

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "payment-link@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _seed_order(sqlite_engine, *, with_phone: bool = True) -> int:
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "payment-link@example.com")).first()
        assert user is not None

        customer = Customer(
            customer_number="CUST-PAY-1",
            name="Pay Customer",
            email="pay@example.com",
            phone="07123456789" if with_phone else None,
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-PAY-1",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("300.00"),
            balance_amount=Decimal("900.00"),
            created_by_id=user.id,
            accepted_at=datetime.utcnow(),
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteItem(
                quote_id=quote.id,
                description="Stable",
                quantity=Decimal("1.00"),
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
                discount_amount=Decimal("0.00"),
                final_line_total=Decimal("1000.00"),
                sort_order=0,
                is_custom=True,
            )
        )
        session.commit()
        quote_id = quote.id

    return quote_id


def _order_id(api_client, sqlite_engine, quote_id: int) -> int:
    headers = _auth_headers(sqlite_engine)
    resp = api_client.post(f"/api/quotes/{quote_id}/ensure-order", headers=headers)
    assert resp.status_code == 200
    return resp.json()["order_id"]


def test_send_payment_link_invalid_url(api_client, sqlite_engine):
    quote_id = _seed_order(sqlite_engine)
    order_id = _order_id(api_client, sqlite_engine, quote_id)
    headers = _auth_headers(sqlite_engine)

    resp = api_client.post(
        f"/api/orders/{order_id}/send-payment-link",
        headers=headers,
        json={"channel": "sms", "payment_url": "http://not-secure.example/pay"},
    )
    assert resp.status_code == 400
    assert "https" in resp.json()["detail"].lower()


def test_send_payment_link_missing_url(api_client, sqlite_engine):
    quote_id = _seed_order(sqlite_engine)
    order_id = _order_id(api_client, sqlite_engine, quote_id)
    headers = _auth_headers(sqlite_engine)

    resp = api_client.post(
        f"/api/orders/{order_id}/send-payment-link",
        headers=headers,
        json={"channel": "sms"},
    )
    assert resp.status_code == 400


def test_send_payment_link_missing_phone(api_client, sqlite_engine):
    quote_id = _seed_order(sqlite_engine, with_phone=False)
    order_id = _order_id(api_client, sqlite_engine, quote_id)
    headers = _auth_headers(sqlite_engine)

    resp = api_client.post(
        f"/api/orders/{order_id}/send-payment-link",
        headers=headers,
        json={"channel": "sms", "payment_url": "https://pay.example.com/abc"},
    )
    assert resp.status_code == 400
    assert "phone" in resp.json()["detail"].lower()


@patch.dict(os.environ, {"TWILIO_PHONE_NUMBER": "+441111111111"})
@patch("app.routers.orders.send_sms", return_value=(True, "SM-PAY-1", None))
def test_send_payment_link_sms_success(_mock_sms, api_client, sqlite_engine):
    quote_id = _seed_order(sqlite_engine)
    order_id = _order_id(api_client, sqlite_engine, quote_id)
    headers = _auth_headers(sqlite_engine)
    payment_url = "https://pay.example.com/order-123"

    resp = api_client.post(
        f"/api/orders/{order_id}/send-payment-link",
        headers=headers,
        json={
            "channel": "sms",
            "payment_url": payment_url,
            "save_link_on_order": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["channel"] == "sms"

    with Session(sqlite_engine) as session:
        order = session.get(Order, order_id)
        assert order is not None
        assert order.payment_link_url == payment_url

        sms = session.exec(select(SmsMessage)).first()
        assert sms is not None
        assert payment_url in sms.body

        activity = session.exec(
            select(Activity).where(Activity.activity_type == ActivityType.SMS_SENT)
        ).first()
        assert activity is not None
        assert "Payment link" in activity.notes

        audit = session.exec(
            select(OrderAuditEvent).where(
                OrderAuditEvent.order_id == order_id,
                OrderAuditEvent.event_type == "ORDER_PAYMENT_LINK_SENT",
            )
        ).first()
        assert audit is not None


@patch("app.routers.orders.is_email_configured", return_value=True)
@patch(
    "app.routers.orders.send_email",
    return_value=(True, "msg-pay-1", None, "<p>Pay</p>", "Pay"),
)
def test_send_payment_link_email_success(_mock_send, _mock_cfg, api_client, sqlite_engine):
    quote_id = _seed_order(sqlite_engine)
    order_id = _order_id(api_client, sqlite_engine, quote_id)
    headers = _auth_headers(sqlite_engine)
    payment_url = "https://pay.example.com/email-456"

    resp = api_client.post(
        f"/api/orders/{order_id}/send-payment-link",
        headers=headers,
        json={
            "channel": "email",
            "payment_url": payment_url,
            "to_email": "pay@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["channel"] == "email"

    _mock_send.assert_called_once()
    call_kwargs = _mock_send.call_args.kwargs
    assert call_kwargs["to_email"] == "pay@example.com"

    with Session(sqlite_engine) as session:
        audit = session.exec(
            select(OrderAuditEvent).where(
                OrderAuditEvent.order_id == order_id,
                OrderAuditEvent.event_type == "ORDER_PAYMENT_LINK_SENT",
            )
        ).first()
        assert audit is not None
        assert audit.details["payment_url"] == payment_url
