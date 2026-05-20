"""GET /api/customers returns paginated results."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import Customer, User, UserRole
from app.routers import customers as customers_router


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
    app.include_router(customers_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="customer-list@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        for i in range(3):
            session.add(
                Customer(
                    customer_number=f"CUST-PG-{i}",
                    name=f"Customer {i}",
                    email=f"c{i}@example.com",
                )
            )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "customer-list@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_customer_list_pagination(api_client):
    r = api_client.get("/api/customers", params={"page": 1, "page_size": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2

    r2 = api_client.get("/api/customers", params={"page": 2, "page_size": 2})
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["items"]) == 1
