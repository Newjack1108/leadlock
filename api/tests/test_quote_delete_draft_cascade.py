import os
from decimal import Decimal

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import create_access_token
from app.database import get_session
from app.models import (
    ConfiguratorInvite,
    ConfiguratorInviteStatus,
    Quote,
    QuoteConfiguration,
    QuoteStatus,
    Reminder,
    ReminderPriority,
    ReminderType,
    SuggestedAction,
    User,
    UserRole,
)
from app.routers import quotes as quotes_router


def test_delete_draft_quote_removes_quote_reminders():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(engine) as session:
        user = User(
            email="quote-delete-cascade@example.com",
            hashed_password="x",
            full_name="Delete Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        quote = Quote(
            quote_number="QT-DELETE-REM-1",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        reminder = Reminder(
            reminder_type=ReminderType.QUOTE_STALE,
            quote_id=quote.id,
            assigned_to_id=user.id,
            priority=ReminderPriority.MEDIUM,
            title="Follow up draft",
            message="Draft quote pending review",
            suggested_action=SuggestedAction.REVIEW_QUOTE,
            days_stale=1,
        )
        session.add(reminder)
        session.commit()

    async def _override_user():
        with Session(engine) as session:
            u = session.exec(select(User).where(User.email == "quote-delete-cascade@example.com")).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        token = create_access_token(data={"sub": "quote-delete-cascade@example.com"})
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/quotes/1", headers=headers)
        assert response.status_code == 204

    with Session(engine) as session:
        assert session.exec(select(Quote).where(Quote.id == 1)).first() is None
        assert session.exec(select(Reminder).where(Reminder.quote_id == 1)).first() is None


def test_delete_draft_quote_removes_configurator_rows():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = FastAPI()
    app.include_router(quotes_router.router)

    def _override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with Session(engine) as session:
        user = User(
            email="quote-delete-config@example.com",
            hashed_password="x",
            full_name="Config Delete Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        quote = Quote(
            quote_number="QT-DELETE-CFG-1",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteConfiguration(
                quote_id=quote.id,
                configuration_json={"schema_version": 1, "boxes": [], "extras": []},
                created_by_id=user.id,
            )
        )
        session.add(
            ConfiguratorInvite(
                access_token="delete-cascade-token",
                status=ConfiguratorInviteStatus.SUBMITTED,
                quote_id=quote.id,
            )
        )
        session.commit()

    async def _override_user():
        with Session(engine) as session:
            u = session.exec(
                select(User).where(User.email == "quote-delete-config@example.com")
            ).first()
            assert u is not None
            return u

    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = _override_user

    with TestClient(app) as client:
        token = create_access_token(data={"sub": "quote-delete-config@example.com"})
        headers = {"Authorization": f"Bearer {token}"}
        response = client.delete("/api/quotes/1", headers=headers)
        assert response.status_code == 204

    with Session(engine) as session:
        assert session.exec(select(Quote).where(Quote.id == 1)).first() is None
        assert (
            session.exec(select(QuoteConfiguration).where(QuoteConfiguration.quote_id == 1)).first()
            is None
        )
        assert (
            session.exec(select(ConfiguratorInvite).where(ConfiguratorInvite.quote_id == 1)).first()
            is None
        )
