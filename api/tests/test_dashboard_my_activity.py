"""Dashboard my-activity returns only the signed-in user's newest 10 rows."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import Activity, ActivityType, Customer, User, UserRole
from app.routers import dashboard as dashboard_router


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(dashboard_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_my_activity_returns_only_current_users_newest_ten():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        me = User(
            email="me@example.com",
            hashed_password="dummy",
            full_name="Current User",
            role=UserRole.CLOSER,
        )
        other = User(
            email="other@example.com",
            hashed_password="dummy",
            full_name="Other User",
            role=UserRole.CLOSER,
        )
        session.add(me)
        session.add(other)
        session.commit()
        session.refresh(me)
        session.refresh(other)

        customer = Customer(
            customer_number="CUST-MY-ACT-001",
            name="Pat Customer",
            email="pat@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        now = datetime.utcnow()
        for i in range(12):
            session.add(
                Activity(
                    customer_id=customer.id,
                    activity_type=ActivityType.NOTE,
                    notes=f"Mine note {i}",
                    created_by_id=me.id,
                    created_at=now - timedelta(minutes=i),
                )
            )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.SMS_SENT,
                notes="Other user's SMS",
                created_by_id=other.id,
                created_at=now + timedelta(minutes=1),
            )
        )
        session.commit()
        me_id = me.id

    with Session(engine) as session:
        me = session.get(User, me_id)
        client = TestClient(_make_app(engine, me))
        response = client.get("/api/dashboard/my-activity")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 10
    assert all(item["customer_name"] == "Pat Customer" for item in items)
    assert all("Other user's SMS" not in (item.get("notes") or "") for item in items)
    assert items[0]["notes"] == "Mine note 0"
    assert items[9]["notes"] == "Mine note 9"
    assert items[0]["activity_type"] == ActivityType.NOTE.value
