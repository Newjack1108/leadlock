import os
from datetime import date, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    Activity,
    ActivityType,
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


def _seed_pending_call_item(session: Session, user: User) -> WeeklyPlanItem:
    customer = Customer(
        customer_number="CUST-WP-SEND-001",
        name="Weekly Plan Customer",
        phone="07123456789",
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
        channel="CALL",
        recommended_action="PHONE_CALL",
        suggested_message="Call to discuss quote follow-up",
        status=WeeklyPlanItemStatus.PENDING_REVIEW,
        priority_score=10,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_closer_can_send_call_weekly_plan_item():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        closer = User(
            email="closer-wp@example.com",
            hashed_password="dummy",
            full_name="Closer",
            role=UserRole.CLOSER,
        )
        session.add(closer)
        session.commit()
        session.refresh(closer)
        item = _seed_pending_call_item(session, closer)
        closer_id = closer.id
        item_id = item.id

    app = _make_test_app(engine, SimpleNamespace(id=closer_id, role=UserRole.CLOSER, full_name="Closer"))
    client = TestClient(app)

    res = client.post(f"/api/reminders/weekly-plan/items/{item_id}/send")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == WeeklyPlanItemStatus.AUTO_SENT.value

    with Session(engine) as session:
        activities = session.exec(
            select(Activity).where(Activity.activity_type == ActivityType.CALL_ATTEMPTED)
        ).all()
        assert len(activities) == 1
        assert "Weekly planner call task" in activities[0].notes
        assert activities[0].created_by_id == closer_id


def test_sales_manager_cannot_send_weekly_plan_item():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        manager = User(
            email="manager-wp@example.com",
            hashed_password="dummy",
            full_name="Manager",
            role=UserRole.SALES_MANAGER,
        )
        session.add(manager)
        session.commit()
        session.refresh(manager)
        item = _seed_pending_call_item(session, manager)
        manager_id = manager.id
        item_id = item.id

    app = _make_test_app(
        engine,
        SimpleNamespace(id=manager_id, role=UserRole.SALES_MANAGER, full_name="Manager"),
    )
    client = TestClient(app)

    res = client.post(f"/api/reminders/weekly-plan/items/{item_id}/send")
    assert res.status_code == 403
    assert "closers" in res.json()["detail"].lower()
