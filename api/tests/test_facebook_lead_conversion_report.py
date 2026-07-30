"""Facebook Lead-to-Order report: accepted-date period metrics + cohort rates."""
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
from app.models import (
    FacebookAdvertProfile,
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
        email="fb-reporter@example.com",
        hashed_password="x",
        full_name="FB Reporter",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_advert(session: Session, name: str) -> FacebookAdvertProfile:
    profile = FacebookAdvertProfile(name=name)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _add_lead(
    session: Session,
    *,
    name: str,
    created_at: datetime,
    advert_id: int | None = None,
    status: LeadStatus = LeadStatus.NEW,
    product_interest: str | None = None,
) -> Lead:
    lead = Lead(
        name=name,
        status=status,
        lead_source=LeadSource.FACEBOOK,
        lead_type=LeadType.UNKNOWN,
        facebook_advert_profile_id=advert_id,
        product_interest=product_interest,
        created_at=created_at,
        updated_at=created_at,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


def _add_quote_and_order(
    session: Session,
    *,
    user_id: int,
    lead: Lead,
    quote_number: str,
    order_number: str,
    total_amount: Decimal,
    accepted_at: datetime | None,
    order_created_at: datetime,
) -> tuple[Quote, Order]:
    quote = Quote(
        quote_number=quote_number,
        status=QuoteStatus.ACCEPTED,
        subtotal=total_amount,
        total_amount=total_amount,
        created_by_id=user_id,
        lead_id=lead.id,
        accepted_at=accepted_at,
        created_at=order_created_at - timedelta(days=1),
        updated_at=order_created_at,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    order = Order(
        quote_id=quote.id,
        order_number=order_number,
        subtotal=total_amount,
        total_amount=total_amount,
        created_by_id=user_id,
        created_at=order_created_at,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return quote, order


def test_older_lead_accepted_in_week_counts_as_converted(api_client, sqlite_engine):
    week_start = datetime(2026, 6, 8, 0, 0, 0)
    week_mid = week_start + timedelta(days=2)
    last_month = week_start - timedelta(days=30)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        advert = _add_advert(session, "Summer Ad")
        old_lead = _add_lead(session, name="Old Lead", created_at=last_month, advert_id=advert.id)
        new_lead = _add_lead(session, name="New Lead", created_at=week_mid, advert_id=advert.id)
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=old_lead,
            quote_number="QT-OLD-1",
            order_number="ORD-OLD-1",
            total_amount=Decimal("1000.00"),
            accepted_at=week_mid,
            order_created_at=week_mid,
        )

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    data = response.json()
    summary = data["summary"]

    assert summary["total_facebook_leads"] == 1  # only new_lead created in week
    assert summary["converted_leads"] == 1  # old_lead accepted in week
    assert summary["period_conversion_rate"] == 100.0
    assert summary["cohort_converted_leads"] == 0
    assert summary["cohort_conversion_rate"] == 0.0
    assert summary["total_orders"] == 1
    assert float(summary["total_order_revenue"]) == 1000.0

    by_name = {row["lead_name"]: row for row in data["rows"]}
    assert "Old Lead" in by_name
    assert "New Lead" in by_name
    assert by_name["Old Lead"]["created_in_period"] is False
    assert by_name["Old Lead"]["converted_in_period"] is True
    assert by_name["New Lead"]["created_in_period"] is True
    assert by_name["New Lead"]["converted_in_period"] is False


def test_created_in_week_accepted_outside_counts_for_cohort_only(api_client, sqlite_engine):
    week_start = datetime(2026, 6, 8, 0, 0, 0)
    week_mid = week_start + timedelta(days=2)
    next_week = week_start + timedelta(days=10)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        lead = _add_lead(session, name="Late Convert", created_at=week_mid)
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=lead,
            quote_number="QT-LATE-1",
            order_number="ORD-LATE-1",
            total_amount=Decimal("500.00"),
            accepted_at=next_week,
            order_created_at=next_week,
        )

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    summary = response.json()["summary"]

    assert summary["total_facebook_leads"] == 1
    assert summary["converted_leads"] == 0
    assert summary["period_conversion_rate"] == 0.0
    assert summary["cohort_converted_leads"] == 1
    assert summary["cohort_conversion_rate"] == 100.0
    assert summary["total_orders"] == 0
    assert float(summary["total_order_revenue"]) == 0.0


def test_period_rate_can_exceed_100_percent(api_client, sqlite_engine):
    week_start = datetime(2026, 6, 8, 0, 0, 0)
    week_mid = week_start + timedelta(days=2)
    earlier = week_start - timedelta(days=20)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        created = _add_lead(session, name="Created This Week", created_at=week_mid)
        older_a = _add_lead(session, name="Older A", created_at=earlier)
        older_b = _add_lead(session, name="Older B", created_at=earlier - timedelta(days=5))
        for idx, lead in enumerate([created, older_a, older_b], start=1):
            _add_quote_and_order(
                session,
                user_id=user.id,
                lead=lead,
                quote_number=f"QT-OVER-{idx}",
                order_number=f"ORD-OVER-{idx}",
                total_amount=Decimal("100.00"),
                accepted_at=week_mid + timedelta(hours=idx),
                order_created_at=week_mid + timedelta(hours=idx),
            )

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    summary = response.json()["summary"]

    assert summary["total_facebook_leads"] == 1
    assert summary["converted_leads"] == 3
    assert summary["period_conversion_rate"] == 300.0
    assert summary["cohort_converted_leads"] == 1
    assert summary["cohort_conversion_rate"] == 100.0


def test_legacy_accepted_at_falls_back_to_order_created_at(api_client, sqlite_engine):
    week_mid = datetime(2026, 6, 10, 12, 0, 0)
    earlier = week_mid - timedelta(days=40)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        lead = _add_lead(session, name="Legacy Accept", created_at=earlier)
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=lead,
            quote_number="QT-LEGACY-1",
            order_number="ORD-LEGACY-1",
            total_amount=Decimal("750.00"),
            accepted_at=None,  # legacy blank accepted_at
            order_created_at=week_mid,
        )

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    data = response.json()
    summary = data["summary"]

    assert summary["converted_leads"] == 1
    assert summary["total_facebook_leads"] == 0
    assert float(summary["total_order_revenue"]) == 750.0
    row = data["rows"][0]
    assert row["converted_in_period"] is True
    assert row["accepted_at"].startswith("2026-06-10")


def test_multiple_orders_do_not_double_count_converted_leads(api_client, sqlite_engine):
    week_mid = datetime(2026, 6, 10, 12, 0, 0)
    earlier = week_mid - timedelta(days=15)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        lead = _add_lead(session, name="Multi Order", created_at=earlier)
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=lead,
            quote_number="QT-MULTI-1",
            order_number="ORD-MULTI-1",
            total_amount=Decimal("200.00"),
            accepted_at=week_mid,
            order_created_at=week_mid,
        )
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=lead,
            quote_number="QT-MULTI-2",
            order_number="ORD-MULTI-2",
            total_amount=Decimal("300.00"),
            accepted_at=week_mid + timedelta(hours=2),
            order_created_at=week_mid + timedelta(hours=2),
        )

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    summary = response.json()["summary"]

    assert summary["converted_leads"] == 1
    assert summary["total_orders"] == 2
    assert float(summary["total_order_revenue"]) == 500.0


def test_advert_breakdown_uses_period_and_cohort_bases(api_client, sqlite_engine):
    week_mid = datetime(2026, 6, 10, 12, 0, 0)
    earlier = week_mid - timedelta(days=20)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        advert = _add_advert(session, "Patio Promo")
        created = _add_lead(session, name="Created", created_at=week_mid, advert_id=advert.id)
        older = _add_lead(session, name="Older", created_at=earlier, advert_id=advert.id)
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=older,
            quote_number="QT-AD-1",
            order_number="ORD-AD-1",
            total_amount=Decimal("400.00"),
            accepted_at=week_mid,
            order_created_at=week_mid,
        )
        # created lead remains unconverted

    response = api_client.get(
        "/api/reports/facebook-lead-conversion",
        params={"start_date": "2026-06-08", "end_date": "2026-06-14"},
    )
    assert response.status_code == 200
    breakdown = {item["name"]: item for item in response.json()["advert_breakdown"]}
    patio = breakdown["Patio Promo"]

    assert patio["leads_count"] == 1
    assert patio["converted_leads"] == 1
    assert patio["period_conversion_rate"] == 100.0
    assert patio["cohort_converted_leads"] == 0
    assert patio["cohort_conversion_rate"] == 0.0
    assert float(patio["total_revenue"]) == 400.0


def test_all_time_view_keeps_matching_period_and_cohort(api_client, sqlite_engine):
    now = datetime(2026, 6, 10, 12, 0, 0)

    with Session(sqlite_engine) as session:
        user = _seed_user(session)
        converted = _add_lead(session, name="Converted", created_at=now - timedelta(days=5))
        open_lead = _add_lead(session, name="Open", created_at=now - timedelta(days=2))
        _add_quote_and_order(
            session,
            user_id=user.id,
            lead=converted,
            quote_number="QT-ALL-1",
            order_number="ORD-ALL-1",
            total_amount=Decimal("250.00"),
            accepted_at=now,
            order_created_at=now,
        )

    response = api_client.get("/api/reports/facebook-lead-conversion", params={"period": "all"})
    assert response.status_code == 200
    summary = response.json()["summary"]

    assert summary["total_facebook_leads"] == 2
    assert summary["converted_leads"] == 1
    assert summary["period_conversion_rate"] == 50.0
    assert summary["cohort_converted_leads"] == 1
    assert summary["cohort_conversion_rate"] == 50.0
    assert summary["conversion_rate"] == summary["period_conversion_rate"]
