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
from app.models import Customer, Lead, LeadSource, LeadType, Order, Quote, QuoteStatus, User, UserRole
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
    lead_source: LeadSource | None = None,
    customer_since: datetime | None = None,
    total_amount: Decimal | None = None,
    created_at: datetime | None = None,
) -> int:
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "order-list@example.com")).first()
        assert user is not None

        amount = total_amount if total_amount is not None else Decimal("100.00")
        lead_id = None
        if lead_type is not None or lead_source is not None:
            lead = Lead(
                name=f"Lead {suffix}",
                email=f"lead-{suffix}@example.com",
                lead_type=lead_type or LeadType.UNKNOWN,
                lead_source=lead_source or LeadSource.UNKNOWN,
            )
            session.add(lead)
            session.commit()
            session.refresh(lead)
            lead_id = lead.id

        customer = Customer(
            customer_number=f"CUST-ORD-{suffix}",
            name=customer_name,
            email=f"cust-{suffix}@example.com",
            customer_since=customer_since or datetime.utcnow(),
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead_id,
            quote_number=f"QT-ORD-{suffix}",
            status=QuoteStatus.ACCEPTED,
            subtotal=amount,
            discount_total=Decimal("0.00"),
            total_amount=amount,
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
            subtotal=amount,
            discount_total=Decimal("0.00"),
            total_amount=amount,
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
            total_amount=Decimal("300.00"),
            customer_since=datetime(2024, 1, 15),
            created_at=base,
        ),
        _seed_order(
            sqlite_engine,
            "middle",
            customer_name="Beta Customer",
            deposit_paid=True,
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.FACEBOOK,
            total_amount=Decimal("100.00"),
            customer_since=datetime(2023, 6, 1),
            created_at=base - timedelta(hours=1),
        ),
        _seed_order(
            sqlite_engine,
            "oldest",
            customer_name="Gamma Searchable",
            installation_booked=True,
            lead_type=LeadType.CABINS,
            lead_source=LeadSource.REFERRAL,
            total_amount=Decimal("200.00"),
            customer_since=datetime(2022, 3, 20),
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


def test_order_list_includes_lead_source_and_customer_since(api_client, seeded_orders):
    r = api_client.get("/api/orders")
    assert r.status_code == 200
    by_number = {item["order_number"]: item for item in r.json()["items"]}

    newest = by_number["ORD-TEST-newest"]
    assert newest["lead_source"] is None
    assert newest["customer_since"].startswith("2024-01-15")

    middle = by_number["ORD-TEST-middle"]
    assert middle["lead_source"] == "FACEBOOK"
    assert middle["customer_since"].startswith("2023-06-01")


def test_order_list_created_from_to_filters_by_created_at(api_client, seeded_orders):
    today = datetime.utcnow().date().isoformat()
    r = api_client.get("/api/orders", params={"created_from": today, "created_to": today})
    assert r.status_code == 200
    assert r.json()["total"] == 3

    r2 = api_client.get(
        "/api/orders",
        params={"created_from": "2020-01-01", "created_to": "2020-01-02"},
    )
    assert r2.status_code == 200
    assert r2.json()["total"] == 0
    assert r2.json()["items"] == []


def test_order_list_created_to_before_from_returns_400(api_client, seeded_orders):
    r = api_client.get(
        "/api/orders",
        params={"created_from": "2024-06-01", "created_to": "2024-01-01"},
    )
    assert r.status_code == 400


def test_order_list_sort_by_total_asc(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"sort_by": "total", "sort_dir": "asc"})
    assert r.status_code == 200
    numbers = [item["order_number"] for item in r.json()["items"]]
    assert numbers == ["ORD-TEST-middle", "ORD-TEST-oldest", "ORD-TEST-newest"]


def test_order_list_invalid_sort_by_returns_422(api_client, seeded_orders):
    r = api_client.get("/api/orders", params={"sort_by": "nope"})
    assert r.status_code == 422


def test_order_list_export_pdf(api_client, seeded_orders):
    r = api_client.get("/api/orders/export.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    assert 'filename="orders-' in (r.headers.get("content-disposition") or "")

    empty = api_client.get(
        "/api/orders/export.pdf",
        params={"created_from": "2020-01-01", "created_to": "2020-01-02"},
    )
    assert empty.status_code == 200
    assert empty.content.startswith(b"%PDF")

    filtered = api_client.get(
        "/api/orders/export.pdf",
        params={"status": "deposit_paid", "sort_by": "total", "sort_dir": "asc"},
    )
    assert filtered.status_code == 200
    assert filtered.content.startswith(b"%PDF")


def test_order_list_export_pdf_inverted_range_returns_400(api_client, seeded_orders):
    r = api_client.get(
        "/api/orders/export.pdf",
        params={"created_from": "2024-06-01", "created_to": "2024-01-01"},
    )
    assert r.status_code == 400
