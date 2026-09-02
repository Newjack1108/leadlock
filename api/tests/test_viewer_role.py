"""VIEWER role: read-only access; Users and Company Settings blocked."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token, get_password_hash
from app.database import get_session
from app.models import Customer, Lead, LeadStatus, User, UserRole
from app.routers import (
    customers as customers_router,
    leads as leads_router,
    settings as settings_router,
    users as users_router,
)
from app.viewer_access import viewer_may_access


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
    app.include_router(customers_router.router)
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


def test_viewer_access_rules():
    assert viewer_may_access("GET", "/api/leads")
    assert viewer_may_access("GET", "/api/customers")
    assert viewer_may_access("GET", "/api/quotes")
    assert viewer_may_access("HEAD", "/api/leads/1")
    assert not viewer_may_access("POST", "/api/leads")
    assert not viewer_may_access("PUT", "/api/leads/1")
    assert not viewer_may_access("PATCH", "/api/customers/1")
    assert not viewer_may_access("DELETE", "/api/leads/1")
    assert not viewer_may_access("GET", "/api/users")
    assert not viewer_may_access("GET", "/api/settings/company")
    assert not viewer_may_access("GET", "/api/settings/company/bank-details")
    assert not viewer_may_access("PUT", "/api/settings/company")
    assert viewer_may_access("GET", "/api/settings/user/email")
    assert not viewer_may_access("PUT", "/api/settings/user/email")


def test_director_can_create_viewer_user(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        director = _add_user(session, email="director-viewer@example.com", role=UserRole.DIRECTOR)

    response = api_client.post(
        "/api/users",
        headers=_auth_header(director.email),
        json={
            "email": "viewer@example.com",
            "full_name": "Read Only",
            "password": "secure-password",
            "role": "VIEWER",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "VIEWER"


def test_viewer_can_read_leads_and_customers_but_not_mutate(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        viewer = _add_user(session, email="viewer-ro@example.com", role=UserRole.VIEWER)
        customer = Customer(customer_number="C-VIEW-1", name="View Customer", phone="+447700900201")
        session.add(customer)
        session.commit()
        session.refresh(customer)
        session.add(
            Lead(
                name="View Lead",
                status=LeadStatus.QUALIFIED,
                customer_id=customer.id,
                assigned_to_id=viewer.id,
            )
        )
        session.commit()
        viewer_email = viewer.email
        customer_id = customer.id

    headers = _auth_header(viewer_email)

    leads = api_client.get("/api/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert leads.json()["total"] >= 1

    customers = api_client.get("/api/customers", headers=headers)
    assert customers.status_code == 200, customers.text
    assert any(item["id"] == customer_id for item in customers.json()["items"])

    create = api_client.post(
        "/api/leads",
        headers=headers,
        json={"name": "Should Fail", "lead_type": "GARDEN_ROOM", "lead_source": "WEBSITE"},
    )
    assert create.status_code == 403

    users = api_client.get("/api/users", headers=headers)
    assert users.status_code == 403

    company = api_client.get("/api/settings/company", headers=headers)
    assert company.status_code == 403
