"""GET /api/quotes/export.csv — filtered CSV export of quote list."""
import csv
import io
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
from app.models import (
    Customer,
    DiscountScope,
    DiscountType,
    Lead,
    LeadStatus,
    LeadType,
    Quote,
    QuoteDiscount,
    QuoteItem,
    QuoteStatus,
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
            email="quotes-export@example.com",
            hashed_password="x",
            full_name="Export Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-2025-001",
            name="Jane Smith",
            email="jane@example.com",
            phone="07700900000",
            postcode="AB1 2CD",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            customer_id=customer.id,
            name="Jane Smith - Stables",
            lead_type=LeadType.STABLES,
            status=LeadStatus.QUALIFIED,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        live_quote = Quote(
            quote_number="QT-EXP-001",
            status=QuoteStatus.SENT,
            customer_id=customer.id,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("100.00"),
            total_amount=Decimal("900.00"),
            deposit_amount=Decimal("540.00"),
            balance_amount=Decimal("540.00"),
            created_by_id=user.id,
        )
        closed_quote = Quote(
            quote_number="QT-EXP-002",
            status=QuoteStatus.REJECTED,
            customer_id=customer.id,
            subtotal=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            created_by_id=user.id,
        )
        session.add(live_quote)
        session.add(closed_quote)
        session.commit()
        session.refresh(live_quote)
        session.refresh(closed_quote)

        session.add(
            QuoteItem(
                quote_id=live_quote.id,
                description="12x Stable",
                quantity=Decimal("1"),
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
                final_line_total=Decimal("900.00"),
                discount_amount=Decimal("100.00"),
                sort_order=0,
            )
        )
        session.add(
            QuoteDiscount(
                quote_id=live_quote.id,
                discount_type=DiscountType.FIXED_AMOUNT,
                discount_value=Decimal("100.00"),
                scope=DiscountScope.QUOTE,
                discount_amount=Decimal("100.00"),
                description="Promo discount",
                applied_by_id=user.id,
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "quotes-export@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _auth_headers(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = session.exec(select(User).where(User.email == "quotes-export@example.com")).first()
        assert user is not None
    token = create_access_token(data={"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def _parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def test_quotes_export_csv_headers_and_content(api_client, sqlite_engine):
    r = api_client.get("/api/quotes/export.csv", headers=_auth_headers(sqlite_engine))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "quotes-export-" in r.headers.get("content-disposition", "")

    rows = _parse_csv(r.text)
    assert len(rows) == 1

    live_row = rows[0]
    assert live_row["status"] == "SENT"
    assert live_row["customer_name"] == "Jane Smith"
    assert live_row["customer_email"] == "jane@example.com"
    assert live_row["customer_number"] == "CUST-2025-001"
    assert live_row["lead_type"] == "STABLES"
    assert live_row["total_amount"] == "900.00"
    assert "12x Stable" in live_row["line_items_summary"]
    assert "Promo discount" in live_row["discounts_summary"]
    assert live_row["created_by_name"] == "Export Tester"


def test_quotes_export_csv_lifecycle_live_filter(api_client, sqlite_engine):
    r = api_client.get(
        "/api/quotes/export.csv",
        params={"lifecycle": "live"},
        headers=_auth_headers(sqlite_engine),
    )
    assert r.status_code == 200
    rows = _parse_csv(r.text)
    assert len(rows) == 1
    assert rows[0]["quote_number"] == "QT-EXP-001"
    assert rows[0]["status"] == "SENT"


def test_quotes_export_csv_lifecycle_closed_filter(api_client, sqlite_engine):
    r = api_client.get(
        "/api/quotes/export.csv",
        params={"lifecycle": "closed"},
        headers=_auth_headers(sqlite_engine),
    )
    assert r.status_code == 200
    rows = _parse_csv(r.text)
    assert len(rows) == 1
    assert rows[0]["quote_number"] == "QT-EXP-002"
    assert rows[0]["status"] == "REJECTED"


def test_quotes_export_csv_default_pipeline_excludes_rejected(api_client, sqlite_engine):
    """Default export matches list default: excludes REJECTED/EXPIRED."""
    r = api_client.get("/api/quotes/export.csv", headers=_auth_headers(sqlite_engine))
    assert r.status_code == 200
    rows = _parse_csv(r.text)
    quote_numbers = {row["quote_number"] for row in rows}
    assert quote_numbers == {"QT-EXP-001"}
