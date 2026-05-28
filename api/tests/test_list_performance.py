"""Tests for list endpoint performance helpers (includeTotal, batching)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Lead, LeadStatus, User, UserRole
from app.auth import get_password_hash, create_access_token


@pytest.fixture
def api_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session
    with Session(engine) as session:
        user = User(
            email="perf@test.local",
            hashed_password=get_password_hash("secret"),
            full_name="Perf Tester",
            role=UserRole.DIRECTOR,
            is_active=True,
        )
        session.add(user)
        for i in range(3):
            session.add(
                Lead(
                    name=f"Lead {i}",
                    status=LeadStatus.NEW,
                )
            )
        session.commit()
        token = create_access_token({"sub": user.email})

    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    app.dependency_overrides.clear()


def test_leads_list_include_total_false_skips_count_query(api_client):
  with patch("app.routers.leads.scalar_int", side_effect=[999]) as mock_scalar:
    response = api_client.get("/api/leads", params={"includeTotal": "false"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 3
    mock_scalar.assert_not_called()


def test_leads_list_include_total_true_runs_count(api_client):
  response = api_client.get("/api/leads", params={"includeTotal": "true"})
  assert response.status_code == 200
  assert response.json()["total"] == 3


def test_quotes_list_returns_items_without_line_items(api_client):
  response = api_client.get("/api/quotes")
  assert response.status_code == 200
  data = response.json()
  assert "items" in data
  for item in data["items"]:
    assert item.get("items") == []
