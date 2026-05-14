import asyncio
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.auth import get_current_user, has_configurator_access, require_configurator_access
from app.models import User, UserRole
from app.routers import auth, configurator


def _make_user(*, email: str, role: UserRole = UserRole.DIRECTOR) -> User:
    return User(
        id=1,
        email=email,
        hashed_password="dummy",
        full_name="Configurator Tester",
        role=role,
    )


def test_has_configurator_access_accepts_allowlisted_staff(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", " kelvin@example.com ,other@example.com ")
    monkeypatch.setenv("CONFIGURATOR_ALLOW_DIRECTOR_OVERRIDE", "false")

    user = _make_user(email="Kelvin@example.com", role=UserRole.CLOSER)

    assert has_configurator_access(user) is True


def test_has_configurator_access_rejects_dealer_even_if_allowlisted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", "dealer@example.com")

    user = _make_user(email="dealer@example.com", role=UserRole.DEALER_USER)
    user.dealer_id = 99
    user.dealer_commission_pct = 10

    assert has_configurator_access(user) is False


def test_require_configurator_access_rejects_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "false")
    monkeypatch.delenv("CONFIGURATOR_ALLOWED_EMAILS", raising=False)

    user = _make_user(email="kelvin@example.com")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_configurator_access(current_user=user))
    assert exc.value.status_code == 403


def test_auth_me_includes_computed_configurator_access(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", "kelvin@example.com")

    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user(email="kelvin@example.com")
    client = TestClient(app)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["can_access_configurator"] is True
    assert response.json()["role"] == "DIRECTOR"


def test_configurator_access_endpoint_is_guarded(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", "kelvin@example.com")

    app = FastAPI()
    app.include_router(configurator.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user(email="blocked@example.com")
    client = TestClient(app)

    response = client.get("/api/configurator/access")

    assert response.status_code == 403


def test_configurator_access_endpoint_returns_status_for_allowlisted_user(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", "kelvin@example.com")

    app = FastAPI()
    app.include_router(configurator.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user(email="kelvin@example.com")
    client = TestClient(app)

    response = client.get("/api/configurator/access")

    assert response.status_code == 200
    assert response.json()["enabled"] is True
