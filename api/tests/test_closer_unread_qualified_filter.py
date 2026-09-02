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


def _add_unread_sms(session: Session, customer_id: int, phone: str) -> None:
    session.add(
        SmsMessage(
            customer_id=customer_id,
            direction=SmsDirection.RECEIVED,
            from_phone=phone,
            to_phone="+441234567890",
            body="Thanks for the message",
            received_at=datetime.utcnow(),
        )
    )


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
        _add_unread_sms(session, customer.id, phone)
    session.commit()
    return closer, director, new_customer.id, qual_customer.id


def test_closer_unread_sms_excludes_pre_qual_only_customers(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer, director, _, qual_customer_id = _seed_unread_scenario(session)
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
        closer, _, _, qual_customer_id = _seed_unread_scenario(session)
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


def test_closer_unread_channels_hides_pre_qual_only_customer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer, director, new_customer_id, qual_customer_id = _seed_unread_scenario(session)
        closer_token = create_access_token(data={"sub": closer.email})
        director_token = create_access_token(data={"sub": director.email})

    closer_pre = api_client.get(
        f"/api/customers/{new_customer_id}/unread-channels",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert closer_pre.status_code == 200, closer_pre.text
    assert closer_pre.json() == {"sms_unread": 0, "messenger_unread": 0, "email_unread": 0}

    closer_qual = api_client.get(
        f"/api/customers/{qual_customer_id}/unread-channels",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert closer_qual.status_code == 200, closer_qual.text
    assert closer_qual.json()["sms_unread"] == 1

    director_pre = api_client.get(
        f"/api/customers/{new_customer_id}/unread-channels",
        headers={"Authorization": f"Bearer {director_token}"},
    )
    assert director_pre.status_code == 200, director_pre.text
    assert director_pre.json()["sms_unread"] == 1


def test_closer_sees_unread_for_mixed_new_and_qualified_customer(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        closer = _add_user(session, "closer-mixed@example.com", UserRole.CLOSER)
        mixed = Customer(
            customer_number="C-MIXED-UNREAD",
            name="Mixed Pipeline Customer",
            phone="+447700900103",
        )
        session.add(mixed)
        session.commit()
        session.refresh(mixed)

        session.add(
            Lead(
                name="Still New Lead",
                status=LeadStatus.NEW,
                customer_id=mixed.id,
                assigned_to_id=closer.id,
            )
        )
        session.add(
            Lead(
                name="Qualified Sibling Lead",
                status=LeadStatus.QUALIFIED,
                customer_id=mixed.id,
                assigned_to_id=closer.id,
            )
        )
        _add_unread_sms(session, mixed.id, "+447700900103")
        session.commit()
        mixed_id = mixed.id
        closer_token = create_access_token(data={"sub": closer.email})

    unread_sms = api_client.get(
        "/api/dashboard/unread-sms",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert unread_sms.status_code == 200, unread_sms.text
    assert unread_sms.json()["count"] == 1
    assert unread_sms.json()["messages"][0]["customer_id"] == mixed_id

    by_customer = api_client.get(
        "/api/dashboard/unread-by-customer",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert by_customer.status_code == 200, by_customer.text
    assert by_customer.json() == [{"customer_id": mixed_id, "unread_count": 1}]

    has_unread = api_client.get(
        "/api/customers",
        params={"has_unread": True},
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert has_unread.status_code == 200, has_unread.text
    assert [item["id"] for item in has_unread.json()["items"]] == [mixed_id]

    channels = api_client.get(
        f"/api/customers/{mixed_id}/unread-channels",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert channels.status_code == 200, channels.text
    assert channels.json()["sms_unread"] == 1


def test_closer_sees_unread_after_qualify_restores_previously_read_replies(api_client, sqlite_engine):
    """Pre-qualify replies marked read become unread indicators once the lead is QUALIFIED."""
    from app.models import LeadSource, LeadType
    from app.workflow import auto_transition_lead_status

    with Session(sqlite_engine) as session:
        closer = _add_user(session, "closer-restore-unread@example.com", UserRole.CLOSER)
        director = _add_user(session, "director-restore-unread@example.com", UserRole.DIRECTOR)
        customer = Customer(
            customer_number="C-RESTORE-UNREAD",
            name="Restore Unread Customer",
            phone="+447700900104",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Pre-qual then Qualify",
            status=LeadStatus.ENGAGED,
            lead_source=LeadSource.REFERRAL,
            lead_type=LeadType.STABLES,
            customer_id=customer.id,
            assigned_to_id=director.id,
        )
        session.add(lead)
        session.add(
            SmsMessage(
                customer_id=customer.id,
                direction=SmsDirection.RECEIVED,
                from_phone="+447700900104",
                to_phone="+441234567890",
                body="Reply before qualify",
                received_at=datetime.utcnow(),
                read_at=datetime.utcnow(),
            )
        )
        session.commit()
        session.refresh(lead)
        closer_token = create_access_token(data={"sub": closer.email})
        customer_id = customer.id
        lead_id = lead.id
        director_id = director.id

    before = api_client.get(
        "/api/dashboard/unread-sms",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert before.status_code == 200, before.text
    assert before.json()["count"] == 0

    with Session(sqlite_engine) as session:
        ok = auto_transition_lead_status(
            lead_id,
            LeadStatus.QUALIFIED,
            session,
            director_id,
            reason="Test qualify restores unread",
        )
        assert ok is True

    after = api_client.get(
        "/api/dashboard/unread-sms",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert after.status_code == 200, after.text
    assert after.json()["count"] == 1
    assert after.json()["messages"][0]["customer_id"] == customer_id

    by_customer = api_client.get(
        "/api/dashboard/unread-by-customer",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert by_customer.status_code == 200, by_customer.text
    assert by_customer.json() == [{"customer_id": customer_id, "unread_count": 1}]

    channels = api_client.get(
        f"/api/customers/{customer_id}/unread-channels",
        headers={"Authorization": f"Bearer {closer_token}"},
    )
    assert channels.status_code == 200, channels.text
    assert channels.json()["sms_unread"] == 1
