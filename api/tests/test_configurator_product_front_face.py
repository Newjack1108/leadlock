"""Allowed configurator front faces for standard rectangular products."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user, require_configurator_access
from app.database import get_session
from app.models import User, UserRole
from app.routers import products


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(products.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_configurator_access] = lambda: user
    return app


def test_wider_configurator_product_allows_short_edge_front_only():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            email="front@example.com",
            hashed_password="dummy",
            full_name="Front Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    client = TestClient(_make_app(engine, user))

    invalid = client.post(
        "/api/products",
        json={
            "name": "Wide Box",
            "category": "CONFIGURATOR",
            "base_price": "1500.00",
            "unit": "Unit",
            "configurator_width": "5.00",
            "configurator_length": "3.50",
            "configurator_front_face": "bottom",
        },
    )
    assert invalid.status_code == 422
    assert "left or right" in invalid.json()["detail"]

    valid = client.post(
        "/api/products",
        json={
            "name": "Wide Box",
            "category": "CONFIGURATOR",
            "base_price": "1500.00",
            "unit": "Unit",
            "configurator_width": "5.00",
            "configurator_length": "3.50",
            "configurator_front_face": "left",
        },
    )
    assert valid.status_code == 200
    assert valid.json()["configurator_front_face"] == "left"
