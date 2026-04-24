"""GET /api/quotes lifecycle=live | lifecycle=closed filtering."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
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
            email="quotes-list-lifecycle@example.com",
            hashed_password="x",
            full_name="Test",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        statuses = [
            QuoteStatus.DRAFT,
            QuoteStatus.SENT,
            QuoteStatus.VIEWED,
            QuoteStatus.ACCEPTED,
            QuoteStatus.REJECTED,
            QuoteStatus.EXPIRED,
        ]
        for i, st in enumerate(statuses):
            session.add(
                Quote(
                    quote_number=f"QT-LC-{i}",
                    status=st,
                    subtotal=Decimal("10.00"),
                    total_amount=Decimal("10.00"),
                    created_by_id=user.id,
                )
            )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "quotes-list-lifecycle@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "quotes-list-lifecycle@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_quotes_list_lifecycle_live(api_client, sqlite_engine):
    r = api_client.get("/api/quotes", params={"lifecycle": "live"}, headers=_auth_headers(sqlite_engine))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert {item["status"] for item in data["items"]} == {"DRAFT", "SENT", "VIEWED"}


def test_quotes_list_lifecycle_closed(api_client, sqlite_engine):
    r = api_client.get("/api/quotes", params={"lifecycle": "closed"}, headers=_auth_headers(sqlite_engine))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert {item["status"] for item in data["items"]} == {"ACCEPTED", "REJECTED", "EXPIRED"}


def test_quotes_list_status_overrides_lifecycle(api_client, sqlite_engine):
    r = api_client.get(
        "/api/quotes",
        params={"lifecycle": "live", "status": "ACCEPTED"},
        headers=_auth_headers(sqlite_engine),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "ACCEPTED"


def test_quotes_list_default_pipeline_excludes_rejected_expired(api_client, sqlite_engine):
    r = api_client.get("/api/quotes", headers=_auth_headers(sqlite_engine))
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4
    assert {item["status"] for item in data["items"]} == {"DRAFT", "SENT", "VIEWED", "ACCEPTED"}
