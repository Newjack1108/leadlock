"""Review hub short link for customer review platform buttons."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import backfill_review_request_templates, get_session
from app.models import (
    CompanySettings,
    Customer,
    Order,
    Quote,
    QuoteStatus,
    ReviewHubRequest,
    SmsTemplate,
    User,
    UserRole,
)
from app.review_hub_service import (
    build_review_hub_url,
    ensure_review_hub_request,
    get_hub_context,
)
from app.review_request_service import build_review_template_context
from app.routers import public as public_router


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


def _seed(session: Session, *, prize_draw: bool = False) -> tuple[CompanySettings, Order]:
    user = User(
        email="hub-test@example.com",
        hashed_password="x",
        full_name="Hub Tester",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    settings = CompanySettings(
        company_name="Test Co",
        trading_name="Test Trading",
        review_google_url="https://example.com/google",
        review_facebook_url="https://example.com/facebook",
        review_trustpilot_url="https://example.com/trustpilot",
        review_prize_draw_enabled=prize_draw,
        review_prize_draw_title="Monthly voucher",
        updated_by_id=user.id,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)

    customer = Customer(
        customer_number="CUST-HUB-1",
        name="Hub Customer",
        email="hub@example.com",
        phone="+447700900123",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        customer_id=customer.id,
        quote_number="QT-HUB-1",
        status=QuoteStatus.ACCEPTED,
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        deposit_amount=500,
        balance_amount=500,
        created_by_id=user.id,
        accepted_at=datetime.utcnow(),
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    order = Order(
        quote_id=quote.id,
        customer_id=customer.id,
        order_number="ORD-HUB-1",
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        deposit_amount=500,
        balance_amount=500,
        created_by_id=user.id,
        installation_completed=True,
        installation_completed_at=datetime.utcnow() - timedelta(days=5),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return settings, order


def test_ensure_review_hub_request_is_idempotent(sqlite_engine):
    with Session(sqlite_engine) as session:
        _settings, order = _seed(session)
        first = ensure_review_hub_request(order, session)
        second = ensure_review_hub_request(order, session)
        session.commit()
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert first.access_token == second.access_token

        rows = session.exec(select(ReviewHubRequest).where(ReviewHubRequest.order_id == order.id)).all()
        assert len(rows) == 1


def test_template_context_includes_hub_url(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        ctx = build_review_template_context(settings, order, session)
        assert ctx["review"]["hub_url"]
        assert "/review/" in ctx["review"]["hub_url"]


def test_get_hub_context_returns_platforms_and_prize_draw(sqlite_engine):
    with Session(sqlite_engine) as session:
        _settings, order = _seed(session, prize_draw=True)
        hub = ensure_review_hub_request(order, session)
        session.commit()
        assert hub is not None

        data, err = get_hub_context(hub.access_token, session)
        assert err is None
        assert data is not None
        assert data["company_name"] == "Test Trading"
        assert len(data["platforms"]) == 3
        assert data["prize_draw"] is not None
        assert data["prize_draw"]["url"]
        assert "/review-prize/" in data["prize_draw"]["url"]


def test_backfill_sms_template_uses_hub_url(sqlite_engine):
    from app.models import EmailTemplate

    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        stale_sms = SmsTemplate(
            name="Post-Install Review Request",
            body_template="Google: {{ review.google_url }}",
            created_by_id=user.id,
        )
        session.add(stale_sms)
        session.add(
            EmailTemplate(
                name="Post-Install Review Request",
                subject_template="Thanks",
                body_template="<p>Old</p>",
                created_by_id=user.id,
            )
        )
        settings.review_request_sms_template_id = None
        settings.review_request_email_template_id = None
        session.add(settings)
        session.commit()

        backfill_review_request_templates(session)
        session.refresh(stale_sms)
        assert "hub_url" in stale_sms.body_template
        assert "google_url" not in stale_sms.body_template


@pytest.fixture()
def public_client(sqlite_engine):
    app = FastAPI()
    app.include_router(public_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with TestClient(app) as client:
        yield client


def test_public_review_hub_endpoint(public_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _settings, order = _seed(session, prize_draw=True)
        hub = ensure_review_hub_request(order, session)
        session.commit()
        token = hub.access_token

    response = public_client.get(f"/api/public/review/{token}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["order_number"] == "ORD-HUB-1"
    assert len(payload["platforms"]) == 3
    assert payload["prize_draw"]["title"] == "Monthly voucher"
    assert payload["platforms"][0]["url"].startswith("https://example.com/")
