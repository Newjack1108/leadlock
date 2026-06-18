import json
import os
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.datastructures import Headers

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    Email,
    ScheduledEmail,
    ScheduledEmailStatus,
    User,
    UserRole,
)
from app.routers import emails as emails_router
from app.scheduled_email_service import process_due_scheduled_email


def _make_app(engine, user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(emails_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed(engine):
    with Session(engine) as session:
        user = User(
            email="scheduler@example.com",
            hashed_password="x",
            full_name="Scheduler",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="CUST-EMAIL-SCHED",
            name="Schedule Test Customer",
            email="customer@example.com",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)
        return user, customer


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def test_create_and_list_scheduled_email(engine, monkeypatch):
    user, customer = _seed(engine)
    app = _make_app(engine, user)
    client = TestClient(app)

    async def _fake_upload(_cid, _files):
        return None

    monkeypatch.setattr(
        "app.routers.emails.upload_scheduled_email_attachments",
        _fake_upload,
    )

    scheduled_at = (datetime.utcnow() + timedelta(hours=2)).isoformat()
    payload = {
        "customer_id": customer.id,
        "to_email": "customer@example.com",
        "subject": "Follow up",
        "body_html": "<p>Hello</p>",
        "body_text": "Hello",
        "scheduled_at": scheduled_at,
    }
    form = {"email_data": json.dumps(payload)}
    response = client.post("/api/emails/scheduled", data=form)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ScheduledEmailStatus.PENDING.value
    assert body["subject"] == "Follow up"

    listed = client.get(
        "/api/emails/scheduled",
        params={"customer_id": customer.id, "status": ScheduledEmailStatus.PENDING.value},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_cancel_scheduled_email(engine, monkeypatch):
    user, customer = _seed(engine)
    app = _make_app(engine, user)
    client = TestClient(app)
    deleted: list[str | None] = []

    async def _fake_upload(_cid, _files):
        return None

    monkeypatch.setattr(
        "app.routers.emails.upload_scheduled_email_attachments",
        _fake_upload,
    )

    def _delete(attachments_json):
        deleted.append(attachments_json)

    monkeypatch.setattr("app.routers.emails.delete_stored_attachments", _delete)

    scheduled_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    payload = {
        "customer_id": customer.id,
        "to_email": "customer@example.com",
        "subject": "Cancel me",
        "body_html": "<p>Bye</p>",
        "scheduled_at": scheduled_at,
    }
    created = client.post("/api/emails/scheduled", data={"email_data": json.dumps(payload)})
    scheduled_id = created.json()["id"]

    cancel = client.delete(f"/api/emails/scheduled/{scheduled_id}")
    assert cancel.status_code == 200

    with Session(engine) as session:
        row = session.get(ScheduledEmail, scheduled_id)
        assert row is not None
        assert row.status == ScheduledEmailStatus.CANCELLED


def test_cannot_cancel_non_pending(engine, monkeypatch):
    user, customer = _seed(engine)
    app = _make_app(engine, user)
    client = TestClient(app)

    async def _fake_upload(_cid, _files):
        return None

    monkeypatch.setattr(
        "app.routers.emails.upload_scheduled_email_attachments",
        _fake_upload,
    )

    with Session(engine) as session:
        scheduled = ScheduledEmail(
            customer_id=customer.id,
            to_email="customer@example.com",
            subject="Already sent",
            body_html="<p>Done</p>",
            scheduled_at=datetime.utcnow() - timedelta(minutes=5),
            status=ScheduledEmailStatus.SENT,
            created_by_id=user.id,
        )
        session.add(scheduled)
        session.commit()
        session.refresh(scheduled)
        scheduled_id = scheduled.id

    response = client.delete(f"/api/emails/scheduled/{scheduled_id}")
    assert response.status_code == 400


def test_process_due_scheduled_email_marks_sent(engine, monkeypatch):
    user, customer = _seed(engine)

    with Session(engine) as session:
        scheduled = ScheduledEmail(
            customer_id=customer.id,
            to_email="customer@example.com",
            subject="Due now",
            body_html="<p>Now</p>",
            body_text="Now",
            scheduled_at=datetime.utcnow() - timedelta(minutes=1),
            status=ScheduledEmailStatus.PENDING,
            created_by_id=user.id,
        )
        session.add(scheduled)
        session.commit()
        session.refresh(scheduled)
        scheduled_id = scheduled.id

    monkeypatch.setattr(
        "app.scheduled_email_service.load_scheduled_email_attachment_list_sync",
        lambda _json: None,
    )
    monkeypatch.setattr(
        "app.scheduled_email_service.send_email",
        lambda **kwargs: (True, "<msg-id@test>", None, kwargs.get("body_html"), kwargs.get("body_text")),
    )
    monkeypatch.setattr(
        "app.scheduled_email_service.delete_stored_attachments",
        lambda _json: None,
    )

    with Session(engine) as session:
        process_due_scheduled_email(session, scheduled_id)

    with Session(engine) as session:
        row = session.get(ScheduledEmail, scheduled_id)
        assert row is not None
        assert row.status == ScheduledEmailStatus.SENT
        assert row.message_id == "<msg-id@test>"
        emails = list(session.exec(select(Email).where(Email.customer_id == customer.id)).all())
        assert len(emails) == 1
        assert emails[0].subject == "Due now"
