"""QUALIFIED → QUOTED when a quote is sent via email, SMS, or share-link."""
import json
import os
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.database import get_session
from app.models import (
    Customer,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    Quote,
    QuoteStatus,
    QuoteTemplate,
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
            email="quote-send-transition@example.com",
            hashed_password="x",
            full_name="Send Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-SEND-TRANS",
            name="Send Transition Customer",
            email="customer@example.com",
            phone="+441234567890",
            postcode="AB1 2CD",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Qualified Lead",
            email="customer@example.com",
            phone="+441234567890",
            postcode="AB1 2CD",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.UNKNOWN,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        template = QuoteTemplate(
            name="Test template",
            email_subject_template="Quote {{ quote.quote_number }}",
            email_body_template="<p>Hello {{ customer.name }}</p>",
            created_by_id=user.id,
        )
        session.add(template)
        session.commit()
        session.refresh(template)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead.id,
            quote_number="QT-SEND-001",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("60.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(
                select(User).where(User.email == "quote-send-transition@example.com")
            ).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(
            select(User).where(User.email == "quote-send-transition@example.com")
        ).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _lead_status(sqlite_engine) -> LeadStatus:
    with Session(sqlite_engine) as session:
        lead = session.exec(select(Lead).where(Lead.id == 1)).first()
        assert lead is not None
        return lead.status


def _reset_lead_qualified(sqlite_engine):
    with Session(sqlite_engine) as session:
        lead = session.exec(select(Lead).where(Lead.id == 1)).first()
        assert lead is not None
        lead.status = LeadStatus.QUALIFIED
        session.add(lead)
        session.commit()


@patch.dict(os.environ, {"FRONTEND_BASE_URL": "https://app.example.com"})
def test_share_link_transitions_qualified_lead_to_quoted(api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    response = api_client.post("/api/quotes/1/share-link", headers=headers)
    assert response.status_code == 200
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED


@patch.dict(os.environ, {"FRONTEND_BASE_URL": "https://app.example.com"})
def test_share_link_resend_heals_stuck_qualified_lead(api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    first = api_client.post("/api/quotes/1/share-link", headers=headers)
    assert first.status_code == 200

    _reset_lead_qualified(sqlite_engine)
    assert _lead_status(sqlite_engine) == LeadStatus.QUALIFIED

    second = api_client.post("/api/quotes/1/share-link", headers=headers)
    assert second.status_code == 200
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED


@patch.dict(os.environ, {"FRONTEND_BASE_URL": "https://app.example.com", "TWILIO_PHONE_NUMBER": "+441111111111"})
@patch("app.routers.quotes.send_sms", return_value=(True, "SM123", None))
def test_send_sms_transitions_qualified_lead_to_quoted(_mock_sms, api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    response = api_client.post("/api/quotes/1/send-sms", headers=headers, json={})
    assert response.status_code == 200
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED


@patch.dict(os.environ, {"FRONTEND_BASE_URL": "https://app.example.com", "TWILIO_PHONE_NUMBER": "+441111111111"})
@patch("app.routers.quotes.send_sms", return_value=(True, "SM456", None))
def test_send_sms_resend_heals_stuck_qualified_lead(_mock_sms, api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    first = api_client.post("/api/quotes/1/send-sms", headers=headers, json={})
    assert first.status_code == 200

    _reset_lead_qualified(sqlite_engine)
    second = api_client.post("/api/quotes/1/send-sms", headers=headers, json={})
    assert second.status_code == 200
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED


@patch("app.routers.quotes.is_email_configured", return_value=True)
@patch(
    "app.routers.quotes.send_quote_email",
    return_value=(True, "msg-1", None, None, "Subject", "<p>Body</p>", "Body"),
)
def test_send_email_transitions_qualified_lead_to_quoted(_mock_send, _mock_cfg, api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    email_data = json.dumps(
        {
            "template_id": 1,
            "to_email": "customer@example.com",
        }
    )
    response = api_client.post(
        "/api/quotes/1/send-email",
        headers=headers,
        data={"email_data": email_data},
    )
    assert response.status_code == 200, response.text
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED


@patch("app.routers.quotes.is_email_configured", return_value=True)
@patch(
    "app.routers.quotes.send_quote_email",
    side_effect=[
        (True, "msg-resend-a", None, None, "Subject", "<p>Body</p>", "Body"),
        (True, "msg-resend-b", None, None, "Subject", "<p>Body</p>", "Body"),
    ],
)
def test_send_email_resend_heals_stuck_qualified_lead(_mock_send, _mock_cfg, api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)
    email_data = json.dumps(
        {
            "template_id": 1,
            "to_email": "customer@example.com",
        }
    )

    first = api_client.post(
        "/api/quotes/1/send-email",
        headers=headers,
        data={"email_data": email_data},
    )
    assert first.status_code == 200

    _reset_lead_qualified(sqlite_engine)

    second = api_client.post(
        "/api/quotes/1/send-email",
        headers=headers,
        data={"email_data": email_data},
    )
    assert second.status_code == 200
    assert _lead_status(sqlite_engine) == LeadStatus.QUOTED
