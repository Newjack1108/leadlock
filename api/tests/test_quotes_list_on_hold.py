"""GET /api/quotes on_hold filter."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token, get_current_user
from app.database import get_session
from app.models import Quote, QuoteStatus, User, UserRole
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
            email="quotes-on-hold@example.com",
            hashed_password="x",
            full_name="Test",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        session.add(
            Quote(
                quote_number="QT-HOLD-YES",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                sent_at=datetime.utcnow(),
                on_hold_at=datetime.utcnow(),
            )
        )
        session.add(
            Quote(
                quote_number="QT-HOLD-NO",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10.00"),
                total_amount=Decimal("10.00"),
                created_by_id=user.id,
                sent_at=datetime.utcnow(),
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "quotes-on-hold@example.com")).first()
            assert u is not None
            return u

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "quotes-on-hold@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_on_hold_true_returns_only_held_quotes(api_client, sqlite_engine):
    headers = _auth_headers(sqlite_engine)

    all_live = api_client.get("/api/quotes", params={"lifecycle": "live"}, headers=headers)
    assert all_live.status_code == 200
    all_numbers = {q["quote_number"] for q in all_live.json()["items"]}
    assert "QT-HOLD-YES" in all_numbers
    assert "QT-HOLD-NO" in all_numbers

    held = api_client.get(
        "/api/quotes",
        params={"lifecycle": "live", "on_hold": True},
        headers=headers,
    )
    assert held.status_code == 200
    numbers = {q["quote_number"] for q in held.json()["items"]}
    assert numbers == {"QT-HOLD-YES"}
    assert all(q.get("on_hold_at") for q in held.json()["items"])
