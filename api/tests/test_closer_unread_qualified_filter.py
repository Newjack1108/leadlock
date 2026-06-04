"""CLOSER unread indicators only include customers with pipeline leads (QUALIFIED+)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import create_access_token
from app.routers import customers as customers_router
from app.routers import dashboard as dashboard_router
from app.models import (
    Customer,
    Lead,
    LeadStatus,
    SmsDirection,
    SmsMessage,
    User,
    UserRole,
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
    from app.database import get_session

    app = FastAPI()
    app.include_router(dashboard_router.router)
    app.include_router(customers_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _add_user(session: Session, email: str, role: UserRole) -> User:
    user = User(email=email, hashed_password="x", full_name=role.value, role=role)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_unread_scenario(session: Session):
    closer = _add_user(session, "closer-unread@example.com", UserRole.CLOSER)
    director = _add_user(session, "director-unread@example.com", UserRole.DIRECTOR)

    new_customer = Customer(customer_number="C-NEW-UNREAD", name="Pre-qual Customer", phone="+447700900101")
    qual_customer = Customer(customer_number="C-QUAL-UNREAD", name="Qualified Customer", phone="+447700900102")
    session.add(new_customer)
    session.add(qual_customer)
    session.commit()
    session.refresh(new_customer)
    session.refresh(qual_customer)

    new_lead = Lead(
        name="Pre-qual Lead",
        status=LeadStatus.NEW,
        customer_id=new_customer.id,
        assigned_to_id=director.id,
    )
    qual_lead = Lead(
        name="Qualified Lead",
        status=LeadStatus.QUALIFIED,
        customer_id=qual_customer.id,
        assigned_to_id=closer.id,
    )
    session.add(new_lead)
    session.add(qual_lead)
    session.commit()

    for customer, phone in (
        (new_customer, "+447700900101"),
        (qual_customer, "+447700900102"),
    ):
        session.add(
            SmsMessage(
                customer_id=customer.id,
                direction=SmsDirection.RECEIVED,
                from_phone=phone,
                to_phone="+441234567890",
                body="Thanks for the message",
                received_at=datetime.utcnow(),
            )
        )
    session.commit()
    return closer, director, qual_customer.id


def test_closer_unread_sms_excludes_pre_qual_only_customers(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer, director, qual_customer_id = _seed_unread_scenario(session)
        closer_token = create_access_token(data={"sub": closer.email})
        director_token = create_access_token(data={"sub": director.email})

    closer_res = api_client.get(
        "/api/dashboard/unread-sms",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert closer_res.status_code == 200, closer_res.text
    closer_data = closer_res.json()
    assert closer_data["count"] == 1
    assert len(closer_data["messages"]) == 1
    assert closer_data["messages"][0]["customer_id"] == qual_customer_id

    director_res = api_client.get(
        "/api/dashboard/unread-sms",
        headers={"Authorization": f"Bearer {director_token}"},
    )
    assert director_res.status_code == 200, director_res.text
    assert director_res.json()["count"] == 2


def test_closer_unread_by_customer_and_has_unread_list(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer, _, qual_customer_id = _seed_unread_scenario(session)
        closer_token = create_access_token(data={"sub": closer.email})

    by_customer_res = api_client.get(
        "/api/dashboard/unread-by-customer",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert by_customer_res.status_code == 200, by_customer_res.text
    by_customer = by_customer_res.json()
    assert len(by_customer) == 1
    assert by_customer[0]["customer_id"] == qual_customer_id
    assert by_customer[0]["unread_count"] == 1

    customers_res = api_client.get(
        "/api/customers",
        params={"has_unread": True},
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert customers_res.status_code == 200, customers_res.text
    items = customers_res.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == qual_customer_id
