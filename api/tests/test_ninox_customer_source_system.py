"""Ninox is a customer.source_system flag, not a lead source."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import get_current_user
from app.customer_import_export import import_customers_from_csv
from app.database import get_session
from app.lead_qualify_rules import STAFF_SELECTABLE_LEAD_SOURCES
from app.models import (
    Customer,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    Order,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import customers as customers_router
from app.routers import orders as orders_router
from app.routers.orders import build_order_response


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
    app.include_router(orders_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(sqlite_engine) as session:
        user = User(
            email="ninox-test@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.add(
            Customer(
                customer_number="CUST-NINOX-1",
                name="Ninox Candidate",
                email="ninox-candidate@example.com",
            )
        )
        session.add(
            Customer(
                customer_number="CUST-TEST-1",
                name="Test Sandbox",
                email="test-sandbox@example.com",
                source_system="TEST",
                exclude_from_stats=True,
            )
        )
        session.commit()

    async def _override_user():
        with Session(sqlite_engine) as session:
            u = session.exec(select(User).where(User.email == "ninox-test@example.com")).first()
            assert u is not None
            return u

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_ninox_not_staff_selectable():
    assert LeadSource.NINOX not in STAFF_SELECTABLE_LEAD_SOURCES


def test_patch_source_system_set_and_clear(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        customer = session.exec(
            select(Customer).where(Customer.customer_number == "CUST-NINOX-1")
        ).first()
        assert customer is not None
        customer_id = customer.id

    r = api_client.patch(f"/api/customers/{customer_id}", json={"source_system": "Ninox"})
    assert r.status_code == 200
    assert r.json()["source_system"] == "Ninox"

    r = api_client.patch(f"/api/customers/{customer_id}", json={"source_system": None})
    assert r.status_code == 200
    assert r.json()["source_system"] is None


def test_patch_source_system_rejects_invalid_value(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        customer = session.exec(
            select(Customer).where(Customer.customer_number == "CUST-NINOX-1")
        ).first()
        assert customer is not None
        customer_id = customer.id

    r = api_client.patch(f"/api/customers/{customer_id}", json={"source_system": "Salesforce"})
    assert r.status_code == 400


def test_patch_source_system_protects_test_customers(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        customer = session.exec(
            select(Customer).where(Customer.customer_number == "CUST-TEST-1")
        ).first()
        assert customer is not None
        customer_id = customer.id

    r = api_client.patch(f"/api/customers/{customer_id}", json={"source_system": "Ninox"})
    assert r.status_code == 400
    assert "TEST" in r.json()["detail"]


def test_csv_import_sets_source_system_not_lead_source(sqlite_engine):
    csv_content = (
        "First Name,Surname,Email,Phone,First of Postcode,Last modified,First of Product Type,Lead Status\n"
        "Jane,Doe,jane.ninox@import.test,07111111111,AB1 2CD,01/01/2024,Stables,Qualified\n"
    )
    with Session(sqlite_engine) as session:
        created, skipped, errors = import_customers_from_csv(csv_content, session)
        assert errors == []
        assert created == 1
        assert skipped == 0

        customer = session.exec(
            select(Customer).where(Customer.email == "jane.ninox@import.test")
        ).first()
        assert customer is not None
        assert customer.source_system == "Ninox"

        lead = session.exec(select(Lead).where(Lead.customer_id == customer.id)).first()
        assert lead is not None
        assert lead.lead_source == LeadSource.UNKNOWN
        assert lead.lead_source != LeadSource.NINOX


def test_is_ninox_origin_uses_customer_not_lead_source(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = User(
            email="ninox-order@example.com",
            hashed_password="x",
            full_name="Order User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        customer = Customer(
            customer_number="CUST-NINOX-ORD",
            name="Ninox Facebook Customer",
            source_system="Ninox",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Ninox Facebook Customer",
            status=LeadStatus.NEW,
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.FACEBOOK,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            customer_id=customer.id,
            lead_id=lead.id,
            quote_number="QT-NINOX-1",
            version=1,
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-NINOX-1",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            currency="GBP",
            created_by_id=user.id,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        response = build_order_response(order, [], session)
        assert response.is_ninox_origin is True

        customer.source_system = None
        session.add(customer)
        session.commit()
        session.refresh(order)

        response = build_order_response(order, [], session)
        assert response.is_ninox_origin is False
