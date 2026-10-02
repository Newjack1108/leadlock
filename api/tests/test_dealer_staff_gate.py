"""DEALER roles: dealer portal only; staff CRM denied."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ALLOW_INSECURE_SECRET_KEY", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token, get_password_hash
from app.database import get_session
from app.dealer_access import dealer_may_access
from app.models import Dealer, User, UserRole
from app.routers import customers as customers_router
from app.routers import dealer_portal as dealer_portal_router
from app.routers import settings as settings_router


def test_dealer_allowlist_matches_expected_paths():
    assert dealer_may_access("GET", "/api/auth/login-quote")
    assert dealer_may_access("GET", "/api/dealer-portal/welcome")
    assert dealer_may_access("POST", "/api/dealer-portal/quotes")
    assert dealer_may_access("PUT", "/api/dealer-portal/profile")
    assert not dealer_may_access("GET", "/api/customers")
    assert not dealer_may_access("GET", "/api/settings/customers/export")
    assert not dealer_may_access("GET", "/api/quotes")
    assert not dealer_may_access("GET", "/api/leads")
    assert not dealer_may_access("GET", "/api/orders")
    assert not dealer_may_access("GET", "/api/dashboard/stats")


def test_dealer_token_blocked_from_staff_customer_routes():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Gate Dealer", company_name="Gate Dealer Ltd")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)
        user = User(
            email="dealer-gate@example.com",
            hashed_password=get_password_hash("password12345"),
            full_name="Dealer Gate",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
            token_version=0,
        )
        session.add(user)
        session.commit()
        email = user.email

    app = FastAPI()
    app.include_router(customers_router.router)
    app.include_router(settings_router.router)
    app.include_router(dealer_portal_router.router)

    def _override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    token = create_access_token(data={"sub": email}, token_version=0)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        blocked_customers = client.get("/api/customers", headers=headers)
        blocked_export = client.get("/api/settings/customers/export", headers=headers)
        allowed_welcome = client.get("/api/dealer-portal/welcome", headers=headers)

    assert blocked_customers.status_code == 403, blocked_customers.text
    assert blocked_export.status_code == 403, blocked_export.text
    assert allowed_welcome.status_code == 200, allowed_welcome.text
