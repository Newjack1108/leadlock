"""GET /api/orders returns paginated results with server-side filters."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import Customer, Lead, LeadType, Order, Quote, QuoteStatus, User, UserRole
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
            email="order-list@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "order-list@example.com")).first()
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
    customer_name: str,
    deposit_paid: bool = False,
    installation_booked: bool = False,
    lead_type: LeadType | None = None,
    created_at: datetime | None = None,
) -> int:
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "order-list@example.com")).first()
        assert user is not None

        lead_id = None
        if lead_type is not None:
            lead = Lead(
                name=f"Lead {suffix}",
                email=f"lead-{suffix}@example.com",
                lead_type=lead_type,
            )
            session.add(lead)
            session.commit()
            session.refresh(lead)
            lead_id = lead.id

        customer = Customer(
            customer_number=f"CUST-ORD-{suffix}",
            name=customer_name,
            email=f"cust-{suffix}@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead_id,
            quote_number=f"QT-ORD-{suffix}",
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
            order_number=f"ORD-TEST-{suffix}",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("60.00"),
            balance_amount=Decimal("40.00"),
            created_by_id=user.id,
            deposit_paid=deposit_paid,
            installation_booked=installation_booked,
            created_at=created_at or datetime.utcnow(),
        )
        session.add(order)
        session.commit()
        session.refresh(order)
        return order.id


@pytest.fixture()
def seeded_orders(sqlite_engine):
    base = datetime.utcnow()
    ids = [
        _seed_order(
            sqlite_engine,
            "newest",
            customer_name="Alpha Customer",
            created_at=base,
        ),
        _seed_order(
            sqlite_engine,
            "middle",
            customer_name="Beta Customer",
            deposit_paid=True,
            lead_type=LeadType.STABLES,
            created_at=base - timedelta(hours=1),
        ),
        _seed_order(
            sqlite_engine,
            "oldest",
            customer_name="Gamma Searchable",
            installation_booked=True,
            lead_type=LeadType.CABINS,
            created_at=base - timedelta(hours=2),
        ),
    ]
    return ids


def test_order_list_pagination(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"page": 1, "page_size": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["order_number"] == "ORD-TEST-newest"
    assert data["items"][1]["order_number"] == "ORD-TEST-middle"

    r2 = api_client.get("/api/orders", params={"page": 2, "page_size": 2})
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["items"]) == 1
    assert data2["items"][0]["order_number"] == "ORD-TEST-oldest"


def test_order_list_status_filter(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"status": "new"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["order_number"] == "ORD-TEST-newest"

    r2 = api_client.get("/api/orders", params={"status": "deposit_paid"})
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["order_number"] == "ORD-TEST-middle"


def test_order_list_search_filter(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"search": "Searchable"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_name"] == "Gamma Searchable"


def test_order_list_lead_type_filter(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"lead_type": "STABLES"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["lead_type"] == "STABLES"

    r2 = api_client.get("/api/orders", params={"lead_type": "unknown"})
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["order_number"] == "ORD-TEST-newest"
