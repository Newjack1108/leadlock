import os
from datetime import date as date_type, timedelta
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


def _make_test_app(engine, user: SimpleNamespace):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_users_and_tasks(engine):
    with Session(engine) as session:
        assignee = User(
            email="assignee-tasks@example.com",
            hashed_password="dummy",
            full_name="Assignee User",
            role=UserRole.CLOSER,
        )
        creator = User(
            email="creator-tasks@example.com",
            hashed_password="dummy",
            full_name="Creator User",
            role=UserRole.DIRECTOR,
        )
        other = User(
            email="other-tasks@example.com",
            hashed_password="dummy",
            full_name="Other User",
            role=UserRole.CLOSER,
        )
        session.add(assignee)
        session.add(creator)
        session.add(other)
        session.commit()
        session.refresh(assignee)
        session.refresh(creator)
        session.refresh(other)

        far_future = Reminder(
            reminder_type=ReminderType.USER_TASK,
            assigned_to_id=assignee.id,
            created_by_id=creator.id,
            priority=ReminderPriority.MEDIUM,
            title="Far future task",
            message="Due in two weeks",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=14),
        )
        other_task = Reminder(
            reminder_type=ReminderType.USER_TASK,
            assigned_to_id=other.id,
            created_by_id=creator.id,
            priority=ReminderPriority.MEDIUM,
            title="Someone else's task",
            message="Should not appear",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=1),
        )
        closed = Reminder(
            reminder_type=ReminderType.USER_TASK,
            assigned_to_id=assignee.id,
            created_by_id=creator.id,
            priority=ReminderPriority.MEDIUM,
            title="Closed task",
            message="Already done",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=0,
            due_date=date_type.today() + timedelta(days=1),
            acted_upon_at=__import__("datetime").datetime.utcnow(),
        )
        session.add(far_future)
        session.add(other_task)
        session.add(closed)
        session.commit()
        session.refresh(far_future)

        assignee_ctx = SimpleNamespace(id=assignee.id, role=assignee.role, full_name=assignee.full_name)
        return assignee_ctx, far_future.id


def test_assigned_to_me_returns_open_tasks_including_far_future(engine):
    assignee_ctx, far_future_id = _seed_users_and_tasks(engine)
    client = TestClient(_make_test_app(engine, assignee_ctx))

    res = client.get("/api/reminders/tasks/assigned-to-me")
    assert res.status_code == 200
    data = res.json()
    ids = {item["id"] for item in data}
    assert far_future_id in ids
    assert all(item["assigned_to_id"] == assignee_ctx.id for item in data)
    assert all(item["reminder_type"] == ReminderType.USER_TASK for item in data)
    titles = {item["title"] for item in data}
    assert "Far future task" in titles
    assert "Someone else's task" not in titles
    assert "Closed task" not in titles
