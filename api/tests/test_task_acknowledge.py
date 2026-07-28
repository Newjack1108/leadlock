import os
from datetime import date as date_type, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import Reminder, ReminderPriority, ReminderType, SuggestedAction, User, UserRole
from app.routers import reminders as reminders_router


@pytest.fixture(name="engine")
def fixture_engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _make_test_app(engine, user: SimpleNamespace):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed(engine):
    with Session(engine) as session:
        assignee = User(
            email="ack-assignee@example.com",
            hashed_password="dummy",
            full_name="Assignee",
            role=UserRole.CLOSER,
        )
        other = User(
            email="ack-other@example.com",
            hashed_password="dummy",
            full_name="Other",
            role=UserRole.DIRECTOR,
        )
        session.add(assignee)
        session.add(other)
        session.commit()
        session.refresh(assignee)
        session.refresh(other)

        task = Reminder(
            reminder_type=ReminderType.USER_TASK,
            assigned_to_id=assignee.id,
            created_by_id=other.id,
            priority=ReminderPriority.MEDIUM,
            title="Ack me",
            message="Please acknowledge",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=2),
        )
        stale = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            assigned_to_id=assignee.id,
            priority=ReminderPriority.HIGH,
            title="Not a task",
            message="Cannot acknowledge",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=3,
        )
        session.add(task)
        session.add(stale)
        session.commit()
        session.refresh(task)
        session.refresh(stale)

        assignee_ctx = SimpleNamespace(id=assignee.id, role=assignee.role, full_name=assignee.full_name)
        other_ctx = SimpleNamespace(id=other.id, role=other.role, full_name=other.full_name)
        return assignee_ctx, other_ctx, task.id, stale.id


def test_acknowledge_task_as_assignee(engine):
    assignee_ctx, _, task_id, _ = _seed(engine)
    client = TestClient(_make_test_app(engine, assignee_ctx))

    res = client.post(f"/api/reminders/{task_id}/acknowledge")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == task_id
    assert body["acknowledged_at"] is not None

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.acknowledged_at is not None

    # Idempotent
    res2 = client.post(f"/api/reminders/{task_id}/acknowledge")
    assert res2.status_code == 200
    assert res2.json()["acknowledged_at"] is not None


def test_acknowledge_forbidden_for_non_assignee(engine):
    _, other_ctx, task_id, _ = _seed(engine)
    client = TestClient(_make_test_app(engine, other_ctx))

    res = client.post(f"/api/reminders/{task_id}/acknowledge")
    assert res.status_code == 403

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.acknowledged_at is None


def test_acknowledge_non_task_rejected(engine):
    assignee_ctx, _, _, stale_id = _seed(engine)
    client = TestClient(_make_test_app(engine, assignee_ctx))

    res = client.post(f"/api/reminders/{stale_id}/acknowledge")
    assert res.status_code == 400
