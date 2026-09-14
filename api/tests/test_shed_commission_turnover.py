"""Staff shed commission: 20% deposit default; reports count deposit ex VAT only."""
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
from app.commission_turnover import (
    default_deposit_amount,
    is_staff_shed_commission_sale,
    recognised_turnover,
)
from app.constants import (
    STAFF_DEFAULT_DEPOSIT_RATE,
    STAFF_SHED_COMMISSION_DEPOSIT_RATE,
    VAT_RATE_DECIMAL,
)
from app.database import get_session
from app.models import (
    Customer,
    Dealer,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    OpportunityStage,
    Order,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import quotes as quotes_router
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


def _seed_staff(session: Session) -> User:
    user = User(
        email="shed-comm@example.com",
        hashed_password="x",
        full_name="Shed Comm Tester",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_recognised_turnover_commission_uses_deposit_ex_vat():
    total = Decimal("1000.00")
    deposit_inc = Decimal("240.00")  # 20% of 1200 inc VAT
    assert recognised_turnover(total, deposit_inc, is_commission=True) == Decimal("200.00")
    assert recognised_turnover(total, deposit_inc, is_commission=False) == total


def test_default_deposit_rate_staff_shed_vs_stables(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead_shed = Lead(
            name="Shed Lead",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
        )
        lead_stables = Lead(
            name="Stables Lead",
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
        )
        session.add(lead_shed)
        session.add(lead_stables)
        session.commit()
        session.refresh(lead_shed)
        session.refresh(lead_stables)

        shed_quote = Quote(
            quote_number="QT-SHED-PROBE",
            lead_id=lead_shed.id,
            subtotal=Decimal("1000"),
            total_amount=Decimal("1000"),
            created_by_id=user.id,
        )
        stables_quote = Quote(
            quote_number="QT-STAB-PROBE",
            lead_id=lead_stables.id,
            subtotal=Decimal("1000"),
            total_amount=Decimal("1000"),
            created_by_id=user.id,
        )
        assert is_staff_shed_commission_sale(shed_quote, [], session) is True
        assert is_staff_shed_commission_sale(stables_quote, [], session) is False

        total_inc = Decimal("1200.00")
        assert default_deposit_amount(total_inc, shed_quote, [], session) == (
            total_inc * STAFF_SHED_COMMISSION_DEPOSIT_RATE
        )
        assert default_deposit_amount(total_inc, stables_quote, [], session) == (
            total_inc * STAFF_DEFAULT_DEPOSIT_RATE
        )


def test_dealer_quote_is_not_staff_shed_commission(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        dealer = Dealer(name="Trade Dealer")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)
        lead = Lead(
            name="Dealer Shed",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-DEALER-SHED",
            lead_id=lead.id,
            dealer_id=dealer.id,
            subtotal=Decimal("1000"),
            total_amount=Decimal("1000"),
            created_by_id=user.id,
        )
        assert is_staff_shed_commission_sale(quote, [], session) is False


def test_create_quote_defaults_deposit_20pct_for_sheds(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        customer = Customer(
            customer_number="CUST-SHED-DEP",
            name="Shed Customer",
            email="shed@example.com",
            phone="+441111111111",
            postcode="CW1 1AA",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        lead = Lead(
            name="Shed Customer",
            email="shed@example.com",
            phone="+441111111111",
            postcode="CW1 1AA",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        customer_id = customer.id
        lead_id = lead.id
        user_id = user.id

    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    with Session(sqlite_engine) as session:
        user = session.get(User, user_id)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    response = client.post(
        "/api/quotes",
        json={
            "customer_id": customer_id,
            "lead_id": lead_id,
            "items": [
                {
                    "description": "Garden shed",
                    "quantity": 1,
                    "unit_price": 1000,
                    "is_custom": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    total_ex = Decimal(str(body["total_amount"]))
    total_inc = (total_ex * (Decimal("1") + VAT_RATE_DECIMAL)).quantize(Decimal("0.01"))
    expected_dep = (total_inc * Decimal("0.20")).quantize(Decimal("0.01"))
    assert Decimal(str(body["deposit_amount"])) == expected_dep
    assert Decimal(str(body["balance_amount"])) == total_inc - expected_dep


def test_create_quote_defaults_deposit_50pct_for_stables(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        customer = Customer(
            customer_number="CUST-STAB-DEP",
            name="Stables Customer",
            email="stables@example.com",
            phone="+442222222222",
            postcode="CW1 1BB",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        lead = Lead(
            name="Stables Customer",
            email="stables@example.com",
            phone="+442222222222",
            postcode="CW1 1BB",
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        customer_id = customer.id
        lead_id = lead.id
        user_id = user.id

    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    with Session(sqlite_engine) as session:
        user = session.get(User, user_id)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    response = client.post(
        "/api/quotes",
        json={
            "customer_id": customer_id,
            "lead_id": lead_id,
            "items": [
                {
                    "description": "Stable",
                    "quantity": 1,
                    "unit_price": 1000,
                    "is_custom": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    total_ex = Decimal(str(body["total_amount"]))
    total_inc = (total_ex * (Decimal("1") + VAT_RATE_DECIMAL)).quantize(Decimal("0.01"))
    expected_dep = (total_inc * Decimal("0.50")).quantize(Decimal("0.01"))
    assert Decimal(str(body["deposit_amount"])) == expected_dep


def test_create_quote_explicit_deposit_wins_over_shed_default(sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        customer = Customer(
            customer_number="CUST-SHED-EXPLICIT",
            name="Explicit Deposit",
            email="explicit@example.com",
            phone="+443333333333",
            postcode="CW1 1CC",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)
        lead = Lead(
            name="Explicit Deposit",
            email="explicit@example.com",
            phone="+443333333333",
            postcode="CW1 1CC",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        customer_id = customer.id
        lead_id = lead.id
        user_id = user.id

    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    with Session(sqlite_engine) as session:
        user = session.get(User, user_id)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    response = client.post(
        "/api/quotes",
        json={
            "customer_id": customer_id,
            "lead_id": lead_id,
            "deposit_amount": 300,
            "items": [
                {
                    "description": "Garden shed",
                    "quantity": 1,
                    "unit_price": 1000,
                    "is_custom": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert Decimal(str(response.json()["deposit_amount"])) == Decimal("300.00")


@pytest.fixture()
def reports_client(sqlite_engine):
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


def test_sales_report_staff_shed_counts_deposit_ex_vat(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead = Lead(
            name="Shed Won",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.WON,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-SHED-REV",
            status=QuoteStatus.ACCEPTED,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            accepted_at=when,
            sent_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        order = Order(
            quote_id=quote.id,
            order_number="ORD-SHED-REV",
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            created_at=when,
        )
        session.add(order)
        session.commit()

    response = reports_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-07-01", "end_date": "2026-07-02"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quotes_accepted"]["count"] == 1
    assert Decimal(str(data["quotes_accepted"]["total_value"])) == Decimal("200.00")
    assert len(data["orders"]) == 1
    assert Decimal(str(data["orders"][0]["total_amount"])) == Decimal("200.00")


def test_sales_report_stables_still_counts_full_total(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead = Lead(
            name="Stables Won",
            lead_type=LeadType.STABLES,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.WON,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-STAB-REV",
            status=QuoteStatus.ACCEPTED,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("600.00"),
            balance_amount=Decimal("600.00"),
            created_by_id=user.id,
            accepted_at=when,
            sent_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        order = Order(
            quote_id=quote.id,
            order_number="ORD-STAB-REV",
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("600.00"),
            balance_amount=Decimal("600.00"),
            created_by_id=user.id,
            created_at=when,
        )
        session.add(order)
        session.commit()

    response = reports_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-07-01", "end_date": "2026-07-02"},
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["quotes_accepted"]["total_value"])) == Decimal("1000.00")


def test_sales_report_dealer_shed_counts_full_total(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        dealer = Dealer(name="Dealer Co")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)
        lead = Lead(
            name="Dealer Shed Won",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.WON,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-DEALER-REV",
            status=QuoteStatus.ACCEPTED,
            lead_id=lead.id,
            dealer_id=dealer.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("120.00"),
            balance_amount=Decimal("1080.00"),
            created_by_id=user.id,
            accepted_at=when,
            sent_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        order = Order(
            quote_id=quote.id,
            order_number="ORD-DEALER-REV",
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("120.00"),
            balance_amount=Decimal("1080.00"),
            created_by_id=user.id,
            created_at=when,
        )
        session.add(order)
        session.commit()

    response = reports_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-07-01", "end_date": "2026-07-02"},
    )
    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["quotes_accepted"]["total_value"])) == Decimal("1000.00")


def test_closer_performance_uses_shed_deposit_turnover(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead = Lead(
            name="Closer Shed",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.WON,
            assigned_to_id=user.id,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-CLOSER-SHED",
            status=QuoteStatus.ACCEPTED,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            owner_id=user.id,
            accepted_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()

    response = reports_client.get("/api/reports/closer-performance")
    assert response.status_code == 200
    closers = response.json()["closers"]
    assert len(closers) >= 1
    mine = next(c for c in closers if c["full_name"] == "Shed Comm Tester")
    assert Decimal(str(mine["total_revenue"])) == Decimal("200.00")


def test_pipeline_value_uses_shed_deposit_turnover(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead = Lead(
            name="Pipeline Shed",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.OTHER,
            status=LeadStatus.QUOTED,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-PIPE-SHED",
            status=QuoteStatus.SENT,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            opportunity_stage=OpportunityStage.QUOTE_SENT,
            close_probability=Decimal("50.00"),
            sent_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()

    response = reports_client.get("/api/reports/pipeline-value", params={"period": "all"})
    assert response.status_code == 200
    data = response.json()
    assert Decimal(str(data["total_value"])) == Decimal("200.00")
    assert Decimal(str(data["total_weighted_value"])) == Decimal("100.00")


def test_facebook_report_uses_shed_deposit_turnover(reports_client, sqlite_engine):
    when = datetime(2026, 7, 1, 12, 0, 0)
    with Session(sqlite_engine) as session:
        user = _seed_staff(session)
        lead = Lead(
            name="FB Shed",
            lead_type=LeadType.SHEDS,
            lead_source=LeadSource.FACEBOOK,
            status=LeadStatus.WON,
            created_at=when,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        quote = Quote(
            quote_number="QT-FB-SHED",
            status=QuoteStatus.ACCEPTED,
            lead_id=lead.id,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            accepted_at=when,
            created_at=when,
            updated_at=when,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        order = Order(
            quote_id=quote.id,
            order_number="ORD-FB-SHED",
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("240.00"),
            balance_amount=Decimal("960.00"),
            created_by_id=user.id,
            created_at=when,
        )
        session.add(order)
        session.commit()

    response = reports_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-07-01", "end_date": "2026-07-02"},
    )
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert Decimal(str(summary["total_order_revenue"])) == Decimal("200.00")
    assert Decimal(str(summary["average_order_value"])) == Decimal("200.00")
