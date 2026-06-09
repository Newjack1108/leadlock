import os
from datetime import date, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Customer,
    User,
    UserRole,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
    WeeklyPlanScope,
)
from app.routers import reminders as reminders_router


def _make_test_app(engine, user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_pending_item(session: Session, user: User) -> WeeklyPlanItem:
    customer = Customer(
        customer_number="CUST-WP-OUTCOME-001",
        name="Weekly Plan Outcome Customer",
        email="outcome@example.com",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    run = WeeklyPlanRun(
        week_start=date.today(),
        scope=WeeklyPlanScope.FULL_PIPELINE,
        generated_by_id=user.id,
        generated_at=datetime.utcnow(),
        total_items=1,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    item = WeeklyPlanItem(
        plan_run_id=run.id,
        customer_id=customer.id,
        assigned_to_id=user.id,
        channel="EMAIL",
        recommended_action="FOLLOW_UP",
        suggested_message="Follow up on quote",
        status=WeeklyPlanItemStatus.PENDING_REVIEW,
        priority_score=60,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_patch_weekly_plan_item_rejected():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        director = User(
            email="director-wp-outcome@example.com",
            hashed_password="dummy",
            full_name="Director",
            role=UserRole.DIRECTOR,
        )
        session.add(director)
        session.commit()
        session.refresh(director)
        item = _seed_pending_item(session, director)
        director_id = director.id
        item_id = item.id

    app = _make_test_app(engine, SimpleNamespace(id=director_id, role=UserRole.DIRECTOR, full_name="Director"))
    client = TestClient(app)

    res = client.patch(
        f"/api/reminders/weekly-plan/items/{item_id}",
        json={"status": WeeklyPlanItemStatus.REJECTED.value, "outcome_result": "rejected_by_user"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == WeeklyPlanItemStatus.REJECTED.value
    assert body["outcome_result"] == "rejected_by_user"

    with Session(engine) as session:
        updated = session.get(WeeklyPlanItem, item_id)
        assert updated is not None
        assert updated.status == WeeklyPlanItemStatus.REJECTED
        assert updated.outcome_result == "rejected_by_user"
