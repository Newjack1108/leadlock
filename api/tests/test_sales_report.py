"""Sales Report: leads by created_at; quote buckets by sent/updated/order dates."""
import os
from datetime import datetime, timedelta
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
from app.models import Lead, LeadStatus, LossCategory, Order, Quote, QuoteStatus, User, UserRole
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
        email="sales-reporter@example.com",
        hashed_password="x",
        full_name="Sales Reporter",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_quote(
    session: Session,
    *,
    user_id: int,
    lead_id: int | None,
    quote_number: str,
    status: QuoteStatus,
    total_amount: Decimal,
    accepted_at: datetime | None = None,
    sent_at: datetime | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    loss_category=None,
    loss_reason: str | None = None,
) -> Quote:
    created = created_at or datetime.utcnow()
    quote = Quote(
        quote_number=quote_number,
        status=status,
        subtotal=total_amount,
        total_amount=total_amount,
        created_by_id=user_id,
        lead_id=lead_id,
        customer_id=None,
        sent_at=sent_at if sent_at is not None else created,
        accepted_at=accepted_at,
        created_at=created,
        updated_at=updated_at or created,
        loss_category=loss_category,
        loss_reason=loss_reason,
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
    total_amount: Decimal | None = None,
) -> Order:
    amount = total_amount if total_amount is not None else quote.total_amount
    order = Order(
        quote_id=quote.id,
        customer_id=quote.customer_id,
        order_number=order_number,
        subtotal=amount,
        total_amount=amount,
        created_by_id=user_id,
        created_at=created_at,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def _seed_inbound_leads(session: Session) -> None:
    week_start = datetime(2026, 6, 8, 0, 0, 0)  # Monday
    week_mid = week_start + timedelta(days=2)
    last_week = week_start - timedelta(days=3)

    leads = [
        Lead(name="Inbound NEW", status=LeadStatus.NEW, created_at=week_mid),
        Lead(name="Inbound QUALIFIED", status=LeadStatus.QUALIFIED, created_at=week_mid),
        Lead(name="Inbound WON", status=LeadStatus.WON, created_at=week_mid),
        Lead(name="Inbound QUOTED", status=LeadStatus.QUOTED, created_at=week_mid),
        Lead(name="Old NEW", status=LeadStatus.NEW, created_at=last_week),
    ]
    for lead in leads:
        session.add(lead)
    session.commit()


def test_sales_report_leads_count_is_all_inbound(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["leads_count"] == 4
    # QUALIFIED + QUOTED + WON among inbound
    assert data["qualified_count"] == 3
    assert data["quotes_accepted"]["count"] == 0
    assert data["quotes_lost"]["count"] == 0
    assert data["quotes_closed"]["count"] == 0
    assert data["quotes_rejected"]["count"] == 0
    assert data["period"] == "custom"


def test_sales_report_period_week_excludes_prior_week(api_client, sqlite_engine, monkeypatch):
    week_end = datetime(2026, 6, 11, 12, 0, 0)

    class FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return week_end

    monkeypatch.setattr("app.date_ranges.datetime", FixedDatetime)

    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get("/api/reports/sales-report", params={"period": "week"})
    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "week"
    assert data["leads_count"] == 4
    assert data["start_date"].startswith("2026-06-08")


def test_sales_report_quote_buckets_and_accepted_requires_order(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        in_range = datetime(2026, 6, 10, 10, 0, 0)
        out_of_range = datetime(2026, 5, 1, 10, 0, 0)

        lead_won_status = Lead(name="Lead Still Won", status=LeadStatus.WON, created_at=in_range)
        lead_alice = Lead(name="Won Alice", status=LeadStatus.QUOTED, created_at=out_of_range)
        lead_bob = Lead(name="Won Bob", status=LeadStatus.NEW, created_at=out_of_range)
        lead_carol = Lead(name="Lost Carol", status=LeadStatus.NEW, created_at=out_of_range)
        lead_erin = Lead(name="Closed Erin", status=LeadStatus.NEW, created_at=out_of_range)
        lead_dave = Lead(name="Quoted Dave", status=LeadStatus.QUOTED, created_at=in_range)
        session.add(lead_won_status)
        session.add(lead_alice)
        session.add(lead_bob)
        session.add(lead_carol)
        session.add(lead_erin)
        session.add(lead_dave)
        session.commit()
        for lead in (lead_won_status, lead_alice, lead_bob, lead_carol, lead_erin, lead_dave):
            session.refresh(lead)

        q_a = _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_alice.id,
            quote_number="QT-WON-A",
            status=QuoteStatus.ACCEPTED,
            total_amount=Decimal("2000.00"),
            accepted_at=in_range,
            created_at=out_of_range,
            sent_at=in_range,
        )
        _add_order(
            session,
            quote=q_a,
            user_id=user.id,
            order_number="ORD-A",
            created_at=in_range,
            total_amount=Decimal("2000.00"),
        )
        q_b = _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_bob.id,
            quote_number="QT-WON-B",
            status=QuoteStatus.ACCEPTED,
            total_amount=Decimal("1000.00"),
            accepted_at=in_range,
            created_at=out_of_range,
            sent_at=in_range,
        )
        _add_order(
            session,
            quote=q_b,
            user_id=user.id,
            order_number="ORD-B",
            created_at=in_range,
            total_amount=Decimal("1000.00"),
        )
        # Accepted in range but no order — excluded from accepted
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_won_status.id,
            quote_number="QT-NO-ORDER",
            status=QuoteStatus.ACCEPTED,
            total_amount=Decimal("4000.00"),
            accepted_at=in_range,
            created_at=out_of_range,
            sent_at=in_range,
        )
        # Order outside range — excluded from accepted
        q_old = _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_won_status.id,
            quote_number="QT-WON-OLD",
            status=QuoteStatus.ACCEPTED,
            total_amount=Decimal("5000.00"),
            accepted_at=out_of_range,
            created_at=out_of_range,
            sent_at=out_of_range,
        )
        _add_order(
            session,
            quote=q_old,
            user_id=user.id,
            order_number="ORD-OLD",
            created_at=out_of_range,
            total_amount=Decimal("5000.00"),
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_carol.id,
            quote_number="QT-LOST-A",
            status=QuoteStatus.REJECTED,
            total_amount=Decimal("1500.00"),
            created_at=out_of_range,
            sent_at=out_of_range,
            updated_at=in_range,
            loss_category=LossCategory.PRICE,
            loss_reason="Too expensive",
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_erin.id,
            quote_number="QT-CLOSED-A",
            status=QuoteStatus.REJECTED,
            total_amount=Decimal("700.00"),
            created_at=out_of_range,
            sent_at=out_of_range,
            updated_at=in_range,
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_carol.id,
            quote_number="QT-LOST-OLD",
            status=QuoteStatus.REJECTED,
            total_amount=Decimal("800.00"),
            created_at=out_of_range,
            sent_at=out_of_range,
            updated_at=out_of_range,
            loss_category=LossCategory.OTHER,
            loss_reason="Old",
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_dave.id,
            quote_number="QT-QUOTED",
            status=QuoteStatus.SENT,
            total_amount=Decimal("500.00"),
            created_at=in_range,
            sent_at=in_range,
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead_dave.id,
            quote_number="QT-DRAFT",
            status=QuoteStatus.DRAFT,
            total_amount=Decimal("9999.00"),
            created_at=in_range,
            sent_at=in_range,
        )

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-12"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["quotes_accepted"]["count"] == 2
    assert Decimal(str(data["quotes_accepted"]["total_value"])) == Decimal("3000.00")
    assert Decimal(str(data["quotes_accepted"]["average_value"])) == Decimal("1500.00")

    assert data["quotes_lost"]["count"] == 1
    assert data["quotes_closed"]["count"] == 1
    assert data["quotes_rejected"]["count"] == 2
    assert data["quotes_rejected"]["count"] == (
        data["quotes_lost"]["count"] + data["quotes_closed"]["count"]
    )
    assert Decimal(str(data["quotes_rejected"]["total_value"])) == Decimal("2200.00")

    # Sent in range: WON-A, WON-B, NO-ORDER, QUOTED (draft + out-of-range rejected/sent excluded)
    assert data["quotes_sent"]["count"] == 4
    assert Decimal(str(data["quotes_sent"]["total_value"])) == Decimal("7500.00")
    assert Decimal(str(data["quotes_sent"]["average_value"])) == Decimal("1875.00")

    # Created in range: QT-QUOTED + QT-DRAFT (includes drafts; excludes older created_at)
    assert data["quotes_created"]["count"] == 2
    assert Decimal(str(data["quotes_created"]["total_value"])) == Decimal("10499.00")
    assert Decimal(str(data["quotes_created"]["average_value"])) == Decimal("5249.50")


def test_sales_report_quotes_created_uses_created_at(api_client, sqlite_engine):
    """quotes_created counts by created_at (including drafts), not sent_at."""
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        in_range = datetime(2026, 6, 10, 10, 0, 0)
        out_of_range = datetime(2026, 5, 1, 10, 0, 0)
        lead = Lead(name="Created range", status=LeadStatus.QUOTED, created_at=in_range)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead.id,
            quote_number="QT-CREATED-IN",
            status=QuoteStatus.DRAFT,
            total_amount=Decimal("1200.00"),
            created_at=in_range,
            sent_at=None,
        )
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead.id,
            quote_number="QT-CREATED-OUT",
            status=QuoteStatus.SENT,
            total_amount=Decimal("3400.00"),
            created_at=out_of_range,
            sent_at=in_range,
        )

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-12"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quotes_created"]["count"] == 1
    assert Decimal(str(data["quotes_created"]["total_value"])) == Decimal("1200.00")
    assert data["quotes_sent"]["count"] == 1
    assert Decimal(str(data["quotes_sent"]["total_value"])) == Decimal("3400.00")


def test_sales_report_quotes_sent_requires_sent_at(api_client, sqlite_engine):
    """Non-draft quotes with null sent_at must not inflate quotes_sent via created_at."""
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        in_range = datetime(2026, 6, 10, 10, 0, 0)
        lead = Lead(name="No sent_at", status=LeadStatus.QUOTED, created_at=in_range)
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = Quote(
            quote_number="QT-NO-SENT-AT",
            status=QuoteStatus.SENT,
            subtotal=Decimal("3000.00"),
            total_amount=Decimal("3000.00"),
            created_by_id=user.id,
            lead_id=lead.id,
            customer_id=None,
            sent_at=None,
            created_at=in_range,
            updated_at=in_range,
        )
        session.add(quote)
        _add_quote(
            session,
            user_id=user.id,
            lead_id=lead.id,
            quote_number="QT-REALLY-SENT",
            status=QuoteStatus.SENT,
            total_amount=Decimal("500.00"),
            created_at=in_range,
            sent_at=in_range,
        )

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-12"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quotes_sent"]["count"] == 1
    assert Decimal(str(data["quotes_sent"]["total_value"])) == Decimal("500.00")


def test_sales_report_pdf_accepts_date_range(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/sales-report/pdf",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Sales_Report_" in response.headers.get("content-disposition", "")
    assert "2026-06-08_to_2026-06-11" in response.headers.get("content-disposition", "")


def test_sales_report_period_label_follows_query_params(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    june = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    ).json()
    may = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-05-01", "end_date": "2026-05-31"},
    ).json()

    assert june["leads_count"] == 4
    assert may["leads_count"] == 0
    assert "08 Jun" in june["period_label"]
    assert "01 May" in may["period_label"]
    assert june["period"] == "custom"
    assert may["period"] == "custom"


def test_previous_equal_range_custom_shift():
    from app.date_ranges import ResolvedDateRange, previous_equal_range

    primary = ResolvedDateRange(
        period="custom",
        start=datetime(2026, 6, 8, 0, 0, 0),
        end=datetime(2026, 6, 11, 23, 59, 59, 999999),
        is_custom=True,
    )
    prior = previous_equal_range(primary)
    assert prior is not None
    assert prior.period == "comparison"
    assert prior.end == datetime(2026, 6, 7, 23, 59, 59, 999999)
    assert (prior.end - prior.start) == (primary.end - primary.start)


def test_previous_equal_range_all_returns_none():
    from app.date_ranges import ResolvedDateRange, previous_equal_range

    assert (
        previous_equal_range(
            ResolvedDateRange(
                period="all",
                start=datetime(1970, 1, 1),
                end=datetime(2026, 6, 11),
            )
        )
        is None
    )


def test_sales_report_comparison_custom_isolates_periods(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)
        session.add(Lead(name="Prior Only", status=LeadStatus.NEW, created_at=datetime(2026, 6, 5, 12, 0, 0)))
        session.commit()

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11", "compare": True},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["leads_count"] == 4
    assert data["comparison"] is not None
    assert data["comparison"]["leads_count"] == 2
    assert data["comparison"]["start_date"].startswith("2026-06-04")
    assert data["comparison"]["end_date"].startswith("2026-06-07")


def test_sales_report_comparison_week_equal_length(api_client, sqlite_engine, monkeypatch):
    week_end = datetime(2026, 6, 11, 12, 0, 0)

    class FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return week_end

    monkeypatch.setattr("app.date_ranges.datetime", FixedDatetime)

    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get("/api/reports/sales-report", params={"period": "week", "compare": True})
    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "week"
    assert data["leads_count"] == 4
    assert data["comparison"] is not None
    start = datetime.fromisoformat(data["start_date"])
    end = datetime.fromisoformat(data["end_date"])
    cmp_start = datetime.fromisoformat(data["comparison"]["start_date"])
    cmp_end = datetime.fromisoformat(data["comparison"]["end_date"])
    assert (cmp_end - cmp_start) == (end - start)
    assert cmp_end < start
    assert data["comparison"]["leads_count"] == 1


def test_sales_report_period_all_has_no_comparison(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get("/api/reports/sales-report", params={"period": "all", "compare": True})
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "all"
    assert data["comparison"] is None


def test_sales_report_compare_false_skips_comparison(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/sales-report",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11", "compare": False},
    )
    assert response.status_code == 200
    assert response.json()["comparison"] is None


def test_sales_report_pdf_with_compare(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/sales-report/pdf",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11", "compare": True},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
