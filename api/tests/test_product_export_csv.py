"""Tests for product list production_product_id and CSV export."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import Product, ProductCategory, User, UserRole
from app.routers import products


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(products.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_product_list_includes_production_product_id():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            email="export@example.com",
            hashed_password="dummy",
            full_name="Export Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.add(
            Product(
                name="Synced Box",
                category=ProductCategory.CONFIGURATOR,
                base_price=Decimal("100.00"),
                unit="Unit",
                is_active=True,
                production_product_id=4242,
                configurator_width=Decimal("3.50"),
                configurator_length=Decimal("3.50"),
                configurator_is_starter_box=True,
            )
        )
        session.commit()
        session.refresh(user)

    client = TestClient(_make_app(engine, user))
    res = client.get("/api/products")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["production_product_id"] == 4242
    assert rows[0]["is_production_synced"] is True


def test_products_export_csv_includes_ids_and_filters_extras():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            email="csv@example.com",
            hashed_password="dummy",
            full_name="CSV Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.add(
            Product(
                name="Main Product",
                category=ProductCategory.STABLES,
                base_price=Decimal("200.00"),
                unit="Unit",
                is_active=True,
                production_product_id=100,
            )
        )
        session.add(
            Product(
                name="Rubber Mat",
                category=ProductCategory.STABLES,
                base_price=Decimal("50.00"),
                unit="Unit",
                is_active=True,
                is_extra=True,
                allow_in_configurator=True,
                production_product_id=200,
            )
        )
        session.commit()
        session.refresh(user)

    client = TestClient(_make_app(engine, user))

    all_res = client.get("/api/products/export.csv")
    assert all_res.status_code == 200
    assert "text/csv" in all_res.headers["content-type"]
    assert 'attachment; filename="products-export-' in all_res.headers["content-disposition"]
    body = all_res.text
    assert "id,production_product_id,name" in body
    assert "Main Product" in body
    assert "Rubber Mat" in body
    assert ",100," in body or ",100\n" in body or body.count("100") >= 1

    extras_res = client.get("/api/products/export.csv", params={"is_extra": True})
    assert extras_res.status_code == 200
    assert 'attachment; filename="extras-export-' in extras_res.headers["content-disposition"]
    extras_body = extras_res.text
    assert "Rubber Mat" in extras_body
    assert "Main Product" not in extras_body
    assert "200" in extras_body
