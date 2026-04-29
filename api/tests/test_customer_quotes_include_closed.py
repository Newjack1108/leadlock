"""GET /api/customers/{id}/quotes should include closed statuses."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from decimal import Decimal
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import Customer, Quote, QuoteStatus, User, UserRole
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
            email="customer-quotes@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-TST-1",
            name="Test Customer",
            email="customer@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        statuses = [QuoteStatus.ACCEPTED, QuoteStatus.REJECTED, QuoteStatus.EXPIRED]
        for i, st in enumerate(statuses):
            session.add(
                Quote(
                    customer_id=customer.id,
                    quote_number=f"QT-CUST-{i}",
                    status=st,
                    subtotal=Decimal("100.00"),
                    total_amount=Decimal("100.00"),
                    created_by_id=user.id,
                )
            )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "customer-quotes@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_customer_quotes_includes_closed_statuses(api_client):
    r = api_client.get("/api/customers/1/quotes")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert {item["status"] for item in data} == {"ACCEPTED", "REJECTED", "EXPIRED"}
