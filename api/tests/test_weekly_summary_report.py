"""Weekly pipeline summary counts inbound leads by created_at, not current NEW status."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import Lead, LeadStatus, UserRole
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


def _seed_weekly_leads(session: Session) -> None:
    week_start = datetime(2026, 6, 9, 0, 0, 0)  # Monday
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


@patch("app.routers.reports.get_date_range_for_period")
def test_weekly_summary_new_count_is_all_inbound(mock_week_range, api_client, sqlite_engine):
    week_start = datetime(2026, 6, 9, 0, 0, 0)
    week_end = datetime(2026, 6, 11, 12, 0, 0)
    mock_week_range.return_value = (week_start, week_end)

    with Session(sqlite_engine) as session:
        _seed_weekly_leads(session)

    response = api_client.get("/api/reports/weekly-summary")
    assert response.status_code == 200
    data = response.json()

    assert data["new_count"] == 4
    assert data["quoted_count"] == 1
    assert data["won_count"] == 1
    assert data["lost_count"] == 0
    assert data["closed_count"] == 0
