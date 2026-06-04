import os
from datetime import date as date_type, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

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


def test_get_reminders_hides_far_future_user_tasks(engine):
    today = date_type.today()
    with Session(engine) as session:
        user = User(
            email="reminders-near-due@example.com",
            hashed_password="dummy",
            full_name="Reminder User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        session.add(
            Reminder(
                reminder_type=ReminderType.USER_TASK,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.MEDIUM,
                title="Far future task",
                message="Hidden until near due",
                suggested_action=SuggestedAction.FOLLOW_UP,
                days_stale=0,
                due_date=today + timedelta(days=2),
            )
        )
        session.add(
            Reminder(
                reminder_type=ReminderType.USER_TASK,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.MEDIUM,
                title="Tomorrow task",
                message="Should be visible",
                suggested_action=SuggestedAction.FOLLOW_UP,
                days_stale=0,
                due_date=today + timedelta(days=1),
            )
        )
        session.add(
            Reminder(
                reminder_type=ReminderType.USER_TASK,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.HIGH,
                title="Overdue task",
                message="Should be visible",
                suggested_action=SuggestedAction.FOLLOW_UP,
                days_stale=3,
                due_date=today - timedelta(days=1),
            )
        )
        session.add(
            Reminder(
                reminder_type=ReminderType.LEAD_STALE,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.HIGH,
                title="Non-task reminder",
                message="Should be visible",
                suggested_action=SuggestedAction.REVIEW_QUOTE,
                days_stale=4,
            )
        )
        session.commit()
        user_ctx = SimpleNamespace(id=user.id, role=user.role, full_name=user.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)
    res = client.get("/api/reminders")
    assert res.status_code == 200
    titles = {item["title"] for item in res.json()}
    assert "Far future task" not in titles
    assert "Tomorrow task" in titles
    assert "Overdue task" in titles
    assert "Non-task reminder" in titles


def test_stale_summary_matches_active_reminder_visibility(engine):
    today = date_type.today()
    with Session(engine) as session:
        user = User(
            email="reminders-summary@example.com",
            hashed_password="dummy",
            full_name="Summary User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        session.add(
            Reminder(
                reminder_type=ReminderType.USER_TASK,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.MEDIUM,
                title="Far future task",
                message="Excluded from summary",
                suggested_action=SuggestedAction.FOLLOW_UP,
                days_stale=0,
                due_date=today + timedelta(days=2),
            )
        )
        session.add(
            Reminder(
                reminder_type=ReminderType.LEAD_STALE,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.HIGH,
                title="Stale lead",
                message="Counted",
                suggested_action=SuggestedAction.REVIEW_QUOTE,
                days_stale=4,
            )
        )
        session.commit()
        user_ctx = SimpleNamespace(id=user.id, role=user.role, full_name=user.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)
    list_res = client.get("/api/reminders")
    summary_res = client.get("/api/reminders/stale-summary")
    assert list_res.status_code == 200
    assert summary_res.status_code == 200
    assert len(list_res.json()) == 1
    assert summary_res.json()["total_reminders"] == 1


def test_get_done_reminders_keeps_far_future_user_tasks(engine):
    today = date_type.today()
    with Session(engine) as session:
        user = User(
            email="reminders-done@example.com",
            hashed_password="dummy",
            full_name="Done User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        session.add(
            Reminder(
                reminder_type=ReminderType.USER_TASK,
                assigned_to_id=user.id,
                created_by_id=user.id,
                priority=ReminderPriority.MEDIUM,
                title="Completed future task",
                message="Should remain visible in done",
                suggested_action=SuggestedAction.FOLLOW_UP,
                days_stale=0,
                due_date=today + timedelta(days=10),
                acted_upon_at=datetime.now(),
            )
        )
        session.commit()
        user_ctx = SimpleNamespace(id=user.id, role=user.role, full_name=user.full_name)

    app = _make_test_app(engine, user_ctx)
    client = TestClient(app)
    res = client.get("/api/reminders?done=true")
    assert res.status_code == 200
    titles = {item["title"] for item in res.json()}
    assert "Completed future task" in titles
