import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user, require_configurator_access
from app.database import get_session
from app.models import Product, ProductCategory, Quote, QuoteStatus, User, UserRole
from app.routers import configurator, products, quotes


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(products.router)
    app.include_router(configurator.router)
    app.include_router(quotes.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_configurator_access] = lambda: user
    return app


def _seed_user(engine) -> User:
    with Session(engine) as session:
        user = User(
            email="configurator@example.com",
            hashed_password="dummy",
            full_name="Configurator User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_configurator_products_require_dimensions():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    client = TestClient(_make_app(engine, user))

    response = client.post(
        "/api/products",
        json={
            "name": "Loose Box",
            "category": "CONFIGURATOR",
            "base_price": "1250.00",
            "unit": "Unit",
        },
    )

    assert response.status_code == 422
    assert "configurator_width" in response.json()["detail"]


def test_configurator_catalog_save_preview_and_apply_flow():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        item = Product(
            name="3m Front Box",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        extra = Product(
            name="Rubber Matting",
            category=ProductCategory.STABLES,
            is_extra=True,
            allow_in_configurator=True,
            unit="Per Box",
            base_price=Decimal("125.00"),
        )
        quote = Quote(
            quote_number="QT-CONFIG-001",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            created_by_id=user.id,
        )
        session.add(item)
        session.add(extra)
        session.add(quote)
        session.commit()
        session.refresh(item)
        session.refresh(extra)
        session.refresh(quote)
        quote_id = quote.id
        item_id = item.id
        extra_id = extra.id

    client = TestClient(_make_app(engine, user))

    catalog_response = client.get("/api/configurator/catalog")
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert [row["id"] for row in catalog["items"]] == [item_id]
    assert [row["id"] for row in catalog["extras"]] == [extra_id]

    payload = {
        "schema_version": 1,
        "name": "Stable block A",
        "boxes": [
            {
                "id": "box-1",
                "product_id": item_id,
                "x": "0",
                "y": "0",
                "rotation": 0,
            }
        ],
        "extras": [
            {
                "product_id": extra_id,
            }
        ],
    }

    preview_response = client.post("/api/configurator/preview", json=payload)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["valid"] is True
    assert len(preview["items"]) == 2
    assert Decimal(preview["subtotal"]) == Decimal("2625.00")

    save_response = client.put(f"/api/quotes/{quote_id}/configuration", json=payload)
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["quote_id"] == quote_id
    assert saved["configuration"]["name"] == "Stable block A"

    apply_response = client.post(f"/api/quotes/{quote_id}/configuration/apply")
    assert apply_response.status_code == 200
    applied = apply_response.json()
    assert applied["id"] == quote_id
    assert applied["include_spec_sheets"] is False
    assert applied["include_available_optional_extras"] is False
    assert len(applied["items"]) == 2
    assert {row["description"] for row in applied["items"]} == {
        "3m Front Box",
        "Rubber Matting",
    }


def test_configurator_preview_rejects_disconnected_layouts_and_accepts_snap_tolerance():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        item = Product(
            name="3m Side Box",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("1800.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    client = TestClient(_make_app(engine, user))

    disconnected = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "7", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert disconnected.status_code == 200
    disconnected_payload = disconnected.json()
    assert disconnected_payload["valid"] is False
    assert any(issue["code"] == "DISCONNECTED_LAYOUT" for issue in disconnected_payload["issues"])

    within_tolerance = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "3.03", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert within_tolerance.status_code == 200
    tolerant_payload = within_tolerance.json()
    assert tolerant_payload["valid"] is True
    assert all(issue["code"] != "DISCONNECTED_LAYOUT" for issue in tolerant_payload["issues"])
