"""MARKETING role: inbound/ads access, sales and admin denied."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token, get_password_hash
from app.database import get_session
from app.marketing_access import marketing_may_access
from app.models import Lead, LeadSource, LeadStatus, User, UserRole
from app.routers import (
    customers as customers_router,
    facebook_adverts as facebook_adverts_router,
    leads as leads_router,
    quotes as quotes_router,
    reports as reports_router,
    settings as settings_router,
    users as users_router,
)


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
    app.include_router(leads_router.router)
    app.include_router(quotes_router.router)
    app.include_router(customers_router.router)
    app.include_router(reports_router.router)
    app.include_router(facebook_adverts_router.router)
    app.include_router(settings_router.router)
    app.include_router(users_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _add_user(session: Session, *, email: str, role: UserRole) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("password123"),
        full_name=role.value.title(),
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _auth_header(email: str) -> dict[str, str]:
    token = create_access_token(data={"sub": email})
    return {"Authorization": f"Bearer {token}"}


def test_marketing_allowlist_matches_expected_paths():
    assert marketing_may_access("GET", "/api/leads")
    assert marketing_may_access("GET", "/api/leads/12")
    assert marketing_may_access("GET", "/api/reports/facebook-lead-conversion")
    assert marketing_may_access("POST", "/api/settings/facebook-adverts")
    assert marketing_may_access("PATCH", "/api/settings/facebook-adverts/3")
    assert marketing_may_access("POST", "/api/configurator-invites/9/mark-viewed")
    assert not marketing_may_access("PATCH", "/api/leads/12")
    assert not marketing_may_access("POST", "/api/leads/12/transition")
    assert not marketing_may_access("GET", "/api/quotes")
    assert not marketing_may_access("GET", "/api/customers")
    assert not marketing_may_access("GET", "/api/reports/sales-report")
    assert not marketing_may_access("GET", "/api/settings/company")
    assert not marketing_may_access("POST", "/api/configurator-invites")


def test_director_can_create_marketing_user(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_user(session, email="director-marketing@example.com", role=UserRole.DIRECTOR)
        director_email = director.email

    response = api_client.post(
        "/api/users",
        headers=_auth_header(director_email),
        json={
            "email": "ads@example.com",
            "full_name": "Website Ads",
            "password": "secure-password",
            "role": "MARKETING",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "MARKETING"
    assert response.json()["email"] == "ads@example.com"


def test_marketing_can_read_leads_and_manage_adverts_but_not_mutate_pipeline(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        marketer = _add_user(session, email="marketer@example.com", role=UserRole.MARKETING)
        marketer_email = marketer.email
        lead = Lead(
            name="Website Test",
            email="test@example.com",
            status=LeadStatus.NEW,
            lead_source=LeadSource.CS_WEBSITE,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        lead_id = lead.id

    headers = _auth_header(marketer_email)

    list_res = api_client.get("/api/leads", headers=headers)
    assert list_res.status_code == 200, list_res.text
    assert list_res.json()["items"][0]["name"] == "Website Test"

    detail_res = api_client.get(f"/api/leads/{lead_id}", headers=headers)
    assert detail_res.status_code == 200

    patch_res = api_client.patch(
        f"/api/leads/{lead_id}",
        headers=headers,
        json={"description": "should be blocked"},
    )
    assert patch_res.status_code == 403

    transition_res = api_client.post(
        f"/api/leads/{lead_id}/transition",
        headers=headers,
        json={"new_status": "ENGAGED"},
    )
    assert transition_res.status_code == 403

    quotes_res = api_client.get("/api/quotes", headers=headers)
    assert quotes_res.status_code == 403

    customers_res = api_client.get("/api/customers", headers=headers)
    assert customers_res.status_code == 403

    sales_res = api_client.get("/api/reports/sales-report", headers=headers)
    assert sales_res.status_code == 403

    company_res = api_client.get("/api/settings/company", headers=headers)
    assert company_res.status_code == 403

    facebook_res = api_client.get("/api/reports/facebook-lead-conversion", headers=headers)
    assert facebook_res.status_code == 200, facebook_res.text

    source_res = api_client.get("/api/reports/source-performance", headers=headers)
    assert source_res.status_code == 200, source_res.text

    create_advert = api_client.post(
        "/api/settings/facebook-adverts",
        headers=headers,
        json={"name": "Spring stables", "offer_type": "lead-form"},
    )
    assert create_advert.status_code == 200, create_advert.text
    advert_id = create_advert.json()["id"]

    patch_advert = api_client.patch(
        f"/api/settings/facebook-adverts/{advert_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert patch_advert.status_code == 200
    assert patch_advert.json()["is_active"] is False
