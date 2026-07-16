"""Pipeline summary: inbound leads by created_at; won/lost from accepted/rejected quotes."""
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
from app.models import Lead, LeadStatus, LossCategory, Quote, QuoteStatus, User, UserRole
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
        email="summary-reporter@example.com",
        hashed_password="x",
        full_name="Summary Reporter",
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


def test_weekly_summary_new_count_is_all_inbound(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/weekly-summary",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["new_count"] == 4
    assert data["quoted_count"] == 1
    # QUALIFIED + QUOTED + WON among inbound (4 leads: NEW, QUALIFIED, WON, QUOTED)
    assert data["qualified_count"] == 3
    # Won/lost are quote-based; no quotes seeded here
    assert data["won_count"] == 0
    assert data["lost_count"] == 0
    assert data["closed_count"] == 0
    assert data["period"] == "custom"


def test_weekly_summary_period_week_excludes_prior_week(api_client, sqlite_engine, monkeypatch):
    week_end = datetime(2026, 6, 11, 12, 0, 0)

    class FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return week_end

    monkeypatch.setattr("app.date_ranges.datetime", FixedDatetime)

    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get("/api/reports/weekly-summary", params={"period": "week"})
    assert response.status_code == 200
    data = response.json()

    assert data["period"] == "week"
    assert data["new_count"] == 4
    assert data["start_date"].startswith("2026-06-08")


def test_weekly_summary_won_lost_from_quotes_not_leads(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        in_range = datetime(2026, 6, 10, 10, 0, 0)
        out_of_range = datetime(2026, 5, 1, 10, 0, 0)

        # Lead statuses must not drive won/lost counts
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

        _add_quote(
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
        _add_quote(
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
        # Accepted outside range — excluded from won
        _add_quote(
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
        # Close quote (no loss_category) — counts as closed, not lost
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
        # Rejected outside range — excluded from lost
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
        # Draft should not affect average quote value
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
        "/api/reports/weekly-summary",
        params={"start_date": "2026-06-08", "end_date": "2026-06-12"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["won_count"] == 2
    assert data["lost_count"] == 1
    assert data["closed_count"] == 1
    # Quotes sent in range: WON-A, WON-B, QUOTED (draft + out-of-range rejected excluded)
    assert data["quotes_sent_count"] == 3
    # Win rate = accepted among those sent / sent = 2/3
    assert data["win_rate"] == 66.7
    # Avg quote by sent_at in range: 2000 + 1000 + 500 (rejected quotes sent out of range; draft excluded)
    assert Decimal(str(data["average_quote_value"])) == Decimal("3500") / Decimal("3")
    assert Decimal(str(data["total_quote_value"])) == Decimal("3500.00")
    assert Decimal(str(data["average_won_value"])) == Decimal("1500.00")

    won_names = [d["name"] for d in data["won_deals"]]
    assert won_names == ["Won Alice", "Won Bob"]
    assert Decimal(str(data["won_deals"][0]["value"])) == Decimal("2000.00")
    assert Decimal(str(data["won_deals"][1]["value"])) == Decimal("1000.00")

    assert len(data["lost_deals"]) == 1
    assert data["lost_deals"][0]["name"] == "Lost Carol"
    assert Decimal(str(data["lost_deals"][0]["value"])) == Decimal("1500.00")


def test_weekly_summary_pdf_accepts_date_range(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    response = api_client.get(
        "/api/reports/weekly-summary/pdf",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "Pipeline_Summary_" in response.headers.get("content-disposition", "")
    assert "2026-06-08_to_2026-06-11" in response.headers.get("content-disposition", "")


def test_weekly_summary_pdf_period_label_follows_query_params(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_inbound_leads(session)

    june = api_client.get(
        "/api/reports/weekly-summary",
        params={"start_date": "2026-06-08", "end_date": "2026-06-11"},
    ).json()
    may = api_client.get(
        "/api/reports/weekly-summary",
        params={"start_date": "2026-05-01", "end_date": "2026-05-31"},
    ).json()

    assert june["new_count"] == 4
    assert may["new_count"] == 0
    assert "08 Jun" in june["week_label"]
    assert "01 May" in may["week_label"]
    assert june["period"] == "custom"
    assert may["period"] == "custom"