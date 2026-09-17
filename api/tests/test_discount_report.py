"""Discount Usage Report: offered (applied_at) vs taken (accepted)."""
import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    DiscountScope,
    DiscountType,
    Order,
    Quote,
    QuoteDiscount,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import reports as reports_router


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
    app.include_router(reports_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=UserRole.DIRECTOR)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _seed_user(session: Session) -> User:
    user = User(
        email="discount-reporter@example.com",
        hashed_password="x",
        full_name="Discount Reporter",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_customer(
    session: Session,
    *,
    name: str,
    customer_number: str,
    exclude_from_stats: bool = False,
) -> Customer:
    customer = Customer(
        customer_number=customer_number,
        name=name,
        exclude_from_stats=exclude_from_stats,
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def _add_quote(
    session: Session,
    *,
    user_id: int,
    customer_id: int | None,
    quote_number: str,
    status: QuoteStatus,
    subtotal: Decimal,
    discount_total: Decimal = Decimal("0"),
    accepted_at: datetime | None = None,
) -> Quote:
    total = subtotal - discount_total
    quote = Quote(
        quote_number=quote_number,
        status=status,
        subtotal=subtotal,
        discount_total=discount_total,
        total_amount=total,
        created_by_id=user_id,
        customer_id=customer_id,
        accepted_at=accepted_at,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return quote


def _add_order(
    session: Session,
    *,
    quote: Quote,
    user_id: int,
    order_number: str,
    created_at: datetime,
) -> Order:
    order = Order(
        quote_id=quote.id,
        customer_id=quote.customer_id,
        order_number=order_number,
        subtotal=quote.subtotal,
        discount_total=quote.discount_total,
        total_amount=quote.total_amount,
        created_by_id=user_id,
        created_at=created_at,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def _add_discount(
    session: Session,
    *,
    quote: Quote,
    user_id: int,
    description: str,
    discount_amount: Decimal,
    applied_at: datetime,
    quote_item_id: int | None = None,
    scope: DiscountScope = DiscountScope.QUOTE,
) -> QuoteDiscount:
    discount = QuoteDiscount(
        quote_id=quote.id,
        quote_item_id=quote_item_id,
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=discount_amount,
        scope=scope,
        discount_amount=discount_amount,
        description=description,
        applied_at=applied_at,
        applied_by_id=user_id,
    )
    session.add(discount)
    session.commit()
    session.refresh(discount)
    return discount


def test_offered_only_when_applied_in_range_not_accepted(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        customer = _add_customer(session, name="Alice Offered", customer_number="C-OFF-1")
        quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            quote_number="QT-OFF-1",
            status=QuoteStatus.SENT,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("100.00"),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="10% Off",
            discount_amount=Decimal("100.00"),
            applied_at=datetime(2026, 6, 10, 12, 0, 0),
        )

    response = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["summary"]["offered_count"] == 1
    assert data["summary"]["taken_count"] == 0
    assert data["summary"]["offered_quote_count"] == 1
    assert float(data["summary"]["offered_total"]) == 100.0
    assert len(data["offered"]) == 1
    assert data["offered"][0]["customer_name"] == "Alice Offered"
    assert data["offered"][0]["discount_name"] == "10% Off"
    assert float(data["offered"][0]["order_value"]) == 1000.0
    assert float(data["offered"][0]["discount_amount"]) == 100.0
    assert data["taken"] == []


def test_taken_when_accepted_in_range_even_if_applied_earlier(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        customer = _add_customer(session, name="Bob Taken", customer_number="C-TAK-1")
        quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            quote_number="QT-TAK-1",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("2000.00"),
            discount_total=Decimal("250.00"),
            accepted_at=datetime(2026, 7, 5, 9, 0, 0),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="Summer Deal",
            discount_amount=Decimal("250.00"),
            applied_at=datetime(2026, 6, 15, 10, 0, 0),
        )
        _add_order(
            session,
            quote=quote,
            user_id=user.id,
            order_number="ORD-TAK-1",
            created_at=datetime(2026, 7, 5, 9, 5, 0),
        )

    # June: offered only
    june = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    ).json()
    assert june["summary"]["offered_count"] == 1
    assert june["summary"]["taken_count"] == 0
    assert june["offered"][0]["discount_name"] == "Summer Deal"

    # July: taken only
    july = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-07-01", "end_date": "2026-07-31"},
    ).json()
    assert july["summary"]["offered_count"] == 0
    assert july["summary"]["taken_count"] == 1
    assert july["summary"]["taken_order_count"] == 1
    assert july["taken"][0]["customer_name"] == "Bob Taken"
    assert july["taken"][0]["order_number"] == "ORD-TAK-1"
    assert float(july["taken"][0]["discount_amount"]) == 250.0
    assert float(july["taken"][0]["order_value"]) == 2000.0


def test_multiple_discounts_on_one_quote_aggregate_to_single_row(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        customer = _add_customer(session, name="Carol Multi", customer_number="C-MUL-1")
        quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            quote_number="QT-MUL-1",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("3000.00"),
            discount_total=Decimal("350.00"),
            accepted_at=datetime(2026, 6, 20, 11, 0, 0),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="Loyalty £200",
            discount_amount=Decimal("200.00"),
            applied_at=datetime(2026, 6, 18, 10, 0, 0),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="Promo £150",
            discount_amount=Decimal("150.00"),
            applied_at=datetime(2026, 6, 18, 10, 5, 0),
        )
        _add_order(
            session,
            quote=quote,
            user_id=user.id,
            order_number="ORD-MUL-1",
            created_at=datetime(2026, 6, 20, 11, 5, 0),
        )

    data = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    ).json()

    assert data["summary"]["offered_count"] == 1
    assert data["summary"]["taken_count"] == 1
    assert data["summary"]["offered_quote_count"] == 1
    assert data["summary"]["taken_order_count"] == 1
    assert float(data["summary"]["offered_total"]) == 350.0
    assert float(data["summary"]["taken_total"]) == 350.0
    assert len(data["offered"]) == 1
    assert len(data["taken"]) == 1
    assert float(data["offered"][0]["discount_amount"]) == 350.0
    assert float(data["offered"][0]["order_value"]) == 3000.0
    assert float(data["taken"][0]["discount_amount"]) == 350.0
    assert float(data["taken"][0]["order_value"]) == 3000.0
    offered_name = data["offered"][0]["discount_name"]
    taken_name = data["taken"][0]["discount_name"]
    assert "Loyalty £200" in offered_name
    assert "Promo £150" in offered_name
    assert "Loyalty £200" in taken_name
    assert "Promo £150" in taken_name


def test_item_level_discounts_collapse_to_quote_total(api_client, sqlite_engine):
    """Product-scope discounts fan out per line item; report must show one quote total."""
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        customer = _add_customer(session, name="Eve Items", customer_number="C-ITEM-1")
        quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            quote_number="QT-ITEM-1",
            status=QuoteStatus.SENT,
            subtotal=Decimal("5000.00"),
            discount_total=Decimal("500.00"),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="10% OFF Building",
            discount_amount=Decimal("300.00"),
            applied_at=datetime(2026, 6, 10, 9, 0, 0),
            quote_item_id=101,
            scope=DiscountScope.PRODUCT,
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="10% OFF Building",
            discount_amount=Decimal("200.00"),
            applied_at=datetime(2026, 6, 10, 9, 0, 0),
            quote_item_id=102,
            scope=DiscountScope.PRODUCT,
        )

    data = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    ).json()

    assert data["summary"]["offered_count"] == 1
    assert data["summary"]["offered_quote_count"] == 1
    assert float(data["summary"]["offered_total"]) == 500.0
    assert len(data["offered"]) == 1
    row = data["offered"][0]
    assert row["customer_name"] == "Eve Items"
    assert row["quote_number"] == "QT-ITEM-1"
    assert row["discount_name"] == "10% OFF Building"
    assert float(row["discount_amount"]) == 500.0
    assert float(row["order_value"]) == 5000.0
    assert data["taken"] == []


def test_sandbox_customer_excluded(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        sandbox = _add_customer(
            session,
            name="Sandbox Customer",
            customer_number="C-SANDBOX",
            exclude_from_stats=True,
        )
        real = _add_customer(session, name="Real Customer", customer_number="C-REAL")
        sandbox_quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=sandbox.id,
            quote_number="QT-SANDBOX",
            status=QuoteStatus.SENT,
            subtotal=Decimal("500.00"),
            discount_total=Decimal("50.00"),
        )
        real_quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=real.id,
            quote_number="QT-REAL",
            status=QuoteStatus.SENT,
            subtotal=Decimal("800.00"),
            discount_total=Decimal("80.00"),
        )
        _add_discount(
            session,
            quote=sandbox_quote,
            user_id=user.id,
            description="Sandbox Offer",
            discount_amount=Decimal("50.00"),
            applied_at=datetime(2026, 6, 12, 12, 0, 0),
        )
        _add_discount(
            session,
            quote=real_quote,
            user_id=user.id,
            description="Real Offer",
            discount_amount=Decimal("80.00"),
            applied_at=datetime(2026, 6, 12, 12, 0, 0),
        )

    data = api_client.get(
        "/api/reports/discount-usage",
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    ).json()

    assert data["summary"]["offered_count"] == 1
    assert data["offered"][0]["customer_name"] == "Real Customer"
    assert data["offered"][0]["discount_name"] == "Real Offer"


def test_discount_usage_csv_and_pdf(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        customer = _add_customer(session, name="Dave Export", customer_number="C-EXP-1")
        quote = _add_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            quote_number="QT-EXP-1",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("1200.00"),
            discount_total=Decimal("120.00"),
            accepted_at=datetime(2026, 6, 15, 10, 0, 0),
        )
        _add_discount(
            session,
            quote=quote,
            user_id=user.id,
            description="Export Deal",
            discount_amount=Decimal("120.00"),
            applied_at=datetime(2026, 6, 14, 10, 0, 0),
        )
        _add_order(
            session,
            quote=quote,
            user_id=user.id,
            order_number="ORD-EXP-1",
            created_at=datetime(2026, 6, 15, 10, 5, 0),
        )

    params = {"start_date": "2026-06-01", "end_date": "2026-06-30"}
    csv_response = api_client.get("/api/reports/discount-usage.csv", params=params)
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.headers["content-type"]
    body = csv_response.text
    assert "Offered" in body
    assert "Taken" in body
    assert "Export Deal" in body
    assert "Dave Export" in body

    pdf_response = api_client.get("/api/reports/discount-usage/pdf", params=params)
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content[:4] == b"%PDF"
