"""Long-lived browser session for allowlisted VIEWER accounts."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ALLOW_INSECURE_SECRET_KEY", "true")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    LONG_LIVED_SESSION_CLAIM,
    SECRET_KEY,
    ALGORITHM,
    create_access_token,
    get_password_hash,
)
from app.auth_cookies import AUTH_COOKIE_NAME
from app.database import get_session
from app.models import User, UserRole
from app.routers import auth as auth_router


BOT_EMAIL = "cheshirestables@gmail.com"
PASSWORD = "password123"
THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60
DEFAULT_MAX_AGE = ACCESS_TOKEN_EXPIRE_MINUTES * 60


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def api_client(sqlite_engine):
    app = FastAPI()
    app.include_router(auth_router.router)

    def _override_session():
        with Session(sqlite_engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _add_user(session: Session, *, email: str, role: UserRole) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        full_name=role.value.title(),
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _cookie_max_age(response) -> int | None:
    set_cookie = response.headers.get("set-cookie") or ""
    for part in set_cookie.split(";"):
        piece = part.strip()
        if piece.lower().startswith("max-age="):
            return int(piece.split("=", 1)[1])
    return None


def _jwt_remaining_seconds(token: str) -> float:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    exp = payload["exp"]
    return float(exp) - datetime.utcnow().timestamp()


def test_allowlisted_viewer_gets_thirty_day_session(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _add_user(session, email=BOT_EMAIL, role=UserRole.VIEWER)

    response = api_client.post(
        "/api/auth/login",
        json={"email": BOT_EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload.get(LONG_LIVED_SESSION_CLAIM) is True
    remaining = _jwt_remaining_seconds(token)
    assert remaining > THIRTY_DAYS_SECONDS - 120
    assert remaining <= THIRTY_DAYS_SECONDS + 60

    max_age = _cookie_max_age(response)
    assert max_age is not None
    assert abs(max_age - THIRTY_DAYS_SECONDS) < 120
    assert AUTH_COOKIE_NAME in (response.headers.get("set-cookie") or "")


def test_allowlisted_email_as_director_keeps_default_expiry(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _add_user(session, email=BOT_EMAIL, role=UserRole.DIRECTOR)

    response = api_client.post(
        "/api/auth/login",
        json={"email": BOT_EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert not payload.get(LONG_LIVED_SESSION_CLAIM)
    remaining = _jwt_remaining_seconds(token)
    assert remaining <= DEFAULT_MAX_AGE + 60
    assert remaining > DEFAULT_MAX_AGE - 120

    max_age = _cookie_max_age(response)
    assert max_age is not None
    assert abs(max_age - DEFAULT_MAX_AGE) < 120


def test_other_viewer_keeps_default_expiry(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        _add_user(session, email="other-viewer@example.com", role=UserRole.VIEWER)

    response = api_client.post(
        "/api/auth/login",
        json={"email": "other-viewer@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert not payload.get(LONG_LIVED_SESSION_CLAIM)
    remaining = _jwt_remaining_seconds(token)
    assert remaining <= DEFAULT_MAX_AGE + 60
    assert remaining > DEFAULT_MAX_AGE - 120


def test_long_lived_token_rejected_after_role_change(api_client, sqlite_engine):
    with Session(sqlite_engine) as session:
        user = _add_user(session, email=BOT_EMAIL, role=UserRole.VIEWER)
        token = create_access_token(
            data={"sub": user.email},
            expires_delta=timedelta(days=30),
            token_version=int(getattr(user, "token_version", 0) or 0),
            long_lived=True,
        )
        user.role = UserRole.DIRECTOR
        session.add(user)
        session.commit()

    me = api_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 401
