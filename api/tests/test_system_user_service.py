import os

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.models import User, UserRole
from app.system_user_service import (
    get_or_create_system_user,
    get_system_user_id,
    system_user_email,
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_get_or_create_system_user_is_idempotent():
    engine = _engine()
    with Session(engine) as session:
        u1 = get_or_create_system_user(session)
        u2 = get_or_create_system_user(session)
    assert u1.id == u2.id
    assert u1.full_name == "System"
    assert u1.is_active is False
    assert u1.email == system_user_email()


def test_get_system_user_id_returns_same_row():
    engine = _engine()
    with Session(engine) as session:
        uid = get_system_user_id(session)
        u = session.get(User, uid)
    assert u is not None
    assert u.full_name == "System"


def test_reactivating_system_user_is_corrected():
    engine = _engine()
    with Session(engine) as session:
        u = get_or_create_system_user(session)
        u.is_active = True
        u.full_name = "Wrong"
        session.add(u)
        session.commit()

        u2 = get_or_create_system_user(session)
    assert u2.is_active is False
    assert u2.full_name == "System"


def test_system_user_email_env_override(monkeypatch):
    monkeypatch.setenv("SYSTEM_USER_EMAIL", "Custom.System@Example.COM")
    assert system_user_email() == "custom.system@example.com"


def test_login_rejects_system_email_even_if_password_matches(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.auth import get_password_hash
    from app.database import get_session
    from app.routers import auth as auth_router

    monkeypatch.delenv("SYSTEM_USER_EMAIL", raising=False)

    engine = _engine()
    with Session(engine) as session:
        session.add(
            User(
                email="system@leadlock.internal",
                full_name="System",
                hashed_password=get_password_hash("correct-password"),
                role=UserRole.DIRECTOR,
                is_active=True,
            )
        )
        session.commit()

    app = FastAPI()
    app.include_router(auth_router.router)

    def session_override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    client = TestClient(app)
    res = client.post(
        "/api/auth/login",
        json={"email": "system@leadlock.internal", "password": "correct-password"},
    )
    assert res.status_code == 401
    app.dependency_overrides.clear()
