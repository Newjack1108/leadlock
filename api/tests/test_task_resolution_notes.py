import os
from datetime import date as date_type, timedelta
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


def _make_test_app(engine, user: User):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_user_and_reminders(engine, email: str):
    with Session(engine) as session:
        user = User(
            email=email,
            hashed_password="dummy",
            full_name="Task Notes User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        task = Reminder(
            reminder_type=ReminderType.USER_TASK,
            assigned_to_id=user.id,
            created_by_id=user.id,
            priority=ReminderPriority.MEDIUM,
            title="Call customer",
            message="Follow up on quote",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=1),
        )
        stale = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            assigned_to_id=user.id,
            priority=ReminderPriority.HIGH,
            title="Stale lead",
            message="Lead has gone quiet",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=5,
        )
        session.add(task)
        session.add(stale)
        session.commit()
        session.refresh(task)
        session.refresh(stale)
        user_ctx = SimpleNamespace(id=user.id, role=user.role, full_name=user.full_name)
        return user_ctx, task.id, stale.id


def test_user_task_dismiss_requires_note(engine):
    user_ctx, task_id, _ = _seed_user_and_reminders(engine, "task-notes-dismiss-req@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(f"/api/reminders/{task_id}/dismiss", json={})
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "TASK_NOTE_REQUIRED"

    res_blank = client.post(f"/api/reminders/{task_id}/dismiss", json={"reason": "   "})
    assert res_blank.status_code == 400


def test_user_task_act_requires_note(engine):
    user_ctx, task_id, _ = _seed_user_and_reminders(engine, "task-notes-act-req@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(
        f"/api/reminders/{task_id}/act",
        json={"action_taken": "FOLLOW_UP"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["error"] == "TASK_NOTE_REQUIRED"


def test_user_task_dismiss_with_note_persists(engine):
    user_ctx, task_id, _ = _seed_user_and_reminders(engine, "task-notes-dismiss-ok@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(
        f"/api/reminders/{task_id}/dismiss",
        json={"reason": "Customer postponed"},
    )
    assert res.status_code == 200

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.dismissed_at is not None
        assert reminder.resolution_notes == "Customer postponed"


def test_user_task_act_with_note_persists(engine):
    user_ctx, task_id, _ = _seed_user_and_reminders(engine, "task-notes-act-ok@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(
        f"/api/reminders/{task_id}/act",
        json={"action_taken": "FOLLOW_UP", "notes": "Left voicemail"},
    )
    assert res.status_code == 200

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.acted_upon_at is not None
        assert reminder.resolution_notes == "Left voicemail"


def test_non_user_task_dismiss_without_note_allowed(engine):
    user_ctx, _, stale_id = _seed_user_and_reminders(engine, "task-notes-stale-dismiss@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(f"/api/reminders/{stale_id}/dismiss", json={})
    assert res.status_code == 200

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == stale_id)).first()
        assert reminder is not None
        assert reminder.dismissed_at is not None
        assert reminder.resolution_notes is None


def test_non_user_task_act_without_note_allowed(engine):
    user_ctx, _, stale_id = _seed_user_and_reminders(engine, "task-notes-stale-act@example.com")
    client = TestClient(_make_test_app(engine, user_ctx))

    res = client.post(
        f"/api/reminders/{stale_id}/act",
        json={"action_taken": "FOLLOW_UP"},
    )
    assert res.status_code == 200

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == stale_id)).first()
        assert reminder is not None
        assert reminder.acted_upon_at is not None
        assert reminder.resolution_notes is None


def _seed_task_for_assignee(engine, assignee_email: str, other_email: str):
    with Session(engine) as session:
        assignee = User(
            email=assignee_email,
            hashed_password="dummy",
            full_name="Assignee User",
            role=UserRole.DIRECTOR,
        )
        other = User(
            email=other_email,
            hashed_password="dummy",
            full_name="Other User",
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
            title="Assigned task",
            message="Only assignee may close",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=1),
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        assignee_ctx = SimpleNamespace(id=assignee.id, role=assignee.role, full_name=assignee.full_name)
        other_ctx = SimpleNamespace(id=other.id, role=other.role, full_name=other.full_name)
        return assignee_ctx, other_ctx, task.id


def test_user_task_dismiss_forbidden_for_non_assignee(engine):
    _, other_ctx, task_id = _seed_task_for_assignee(
        engine,
        "task-assignee-dismiss@example.com",
        "task-other-dismiss@example.com",
    )
    client = TestClient(_make_test_app(engine, other_ctx))

    res = client.post(
        f"/api/reminders/{task_id}/dismiss",
        json={"reason": "Trying to dismiss"},
    )
    assert res.status_code == 403
    assert "assigned user" in res.json()["detail"].lower()

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.dismissed_at is None


def test_user_task_act_forbidden_for_non_assignee(engine):
    _, other_ctx, task_id = _seed_task_for_assignee(
        engine,
        "task-assignee-act@example.com",
        "task-other-act@example.com",
    )
    client = TestClient(_make_test_app(engine, other_ctx))

    res = client.post(
        f"/api/reminders/{task_id}/act",
        json={"action_taken": "FOLLOW_UP", "notes": "Trying to complete"},
    )
    assert res.status_code == 403
    assert "assigned user" in res.json()["detail"].lower()

    with Session(engine) as session:
        reminder = session.exec(select(Reminder).where(Reminder.id == task_id)).first()
        assert reminder is not None
        assert reminder.acted_upon_at is None
