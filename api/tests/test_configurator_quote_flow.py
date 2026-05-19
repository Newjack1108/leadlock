import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user, require_configurator_access
from app.database import get_session
from app.models import (
    ConfiguratorConnectionProfile,
    ConfiguratorFrontFace,
    Product,
    ProductCategory,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
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


def test_non_square_configurator_products_require_valid_front_face():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    client = TestClient(_make_app(engine, user))

    missing_front = client.post(
        "/api/products",
        json={
            "name": "Rectangular Box",
            "category": "CONFIGURATOR",
            "base_price": "1450.00",
            "unit": "Unit",
            "configurator_width": "3.50",
            "configurator_length": "5.00",
        },
    )
    assert missing_front.status_code == 422
    assert "configurator_front_face" in missing_front.json()["detail"]

    invalid_front = client.post(
        "/api/products",
        json={
            "name": "Rectangular Box",
            "category": "CONFIGURATOR",
            "base_price": "1450.00",
            "unit": "Unit",
            "configurator_width": "3.50",
            "configurator_length": "5.00",
            "configurator_front_face": "right",
        },
    )
    assert invalid_front.status_code == 422
    assert "top or bottom" in invalid_front.json()["detail"]

    valid_front = client.post(
        "/api/products",
        json={
            "name": "Rectangular Box",
            "category": "CONFIGURATOR",
            "base_price": "1450.00",
            "unit": "Unit",
            "configurator_width": "3.50",
            "configurator_length": "5.00",
            "configurator_front_face": "top",
        },
    )
    assert valid_front.status_code == 200
    assert valid_front.json()["configurator_front_face"] == "top"

    invalid_corner_profile = client.post(
        "/api/products",
        json={
            "name": "Square Corner Box",
            "category": "CONFIGURATOR",
            "base_price": "1450.00",
            "unit": "Unit",
            "configurator_width": "3.50",
            "configurator_length": "3.50",
            "configurator_front_face": "bottom",
            "configurator_connection_profile": "corner_right",
        },
    )
    assert invalid_corner_profile.status_code == 422
    assert "non-square configurator footprint" in invalid_corner_profile.json()["detail"]

    conflicting_corner_front = client.post(
        "/api/products",
        json={
            "name": "Right Hand Corner Box",
            "category": "CONFIGURATOR",
            "base_price": "2450.00",
            "unit": "Unit",
            "configurator_width": "5.00",
            "configurator_length": "3.50",
            "configurator_front_face": "top",
            "configurator_connection_profile": "corner_right",
        },
    )
    assert conflicting_corner_front.status_code == 422
    assert "define the fixed front automatically" in conflicting_corner_front.json()["detail"]

    corner_without_profile = client.post(
        "/api/products",
        json={
            "name": "Corner Missing Profile",
            "category": "CONFIGURATOR",
            "base_price": "2450.00",
            "unit": "Unit",
            "configurator_width": "4.90",
            "configurator_length": "3.60",
            "configurator_is_corner_box": True,
        },
    )
    assert corner_without_profile.status_code == 422
    assert "corner connection profile" in corner_without_profile.json()["detail"].lower()

    valid_corner_profile = client.post(
        "/api/products",
        json={
            "name": "Right Hand Corner Box",
            "category": "CONFIGURATOR",
            "base_price": "2450.00",
            "unit": "Unit",
            "configurator_width": "4.90",
            "configurator_length": "3.60",
            "configurator_is_corner_box": True,
            "configurator_connection_profile": "corner_right",
        },
    )
    assert valid_corner_profile.status_code == 200
    assert valid_corner_profile.json()["configurator_connection_profile"] == "corner_right"
    assert valid_corner_profile.json()["configurator_is_corner_box"] is True
    assert valid_corner_profile.json()["configurator_front_face"] in (None, "bottom")


def test_configurator_catalog_only_lists_extras_opted_into_configurator():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        allowed_extra = Product(
            name="Configurator Rubber Mat",
            category=ProductCategory.STABLES,
            is_extra=True,
            allow_in_configurator=True,
            configurator_per_box=True,
            unit="Unit",
            base_price=Decimal("125.00"),
        )
        blocked_extra = Product(
            name="Quote-only Mat",
            category=ProductCategory.STABLES,
            is_extra=True,
            allow_in_configurator=False,
            unit="Unit",
            base_price=Decimal("99.00"),
        )
        session.add(allowed_extra)
        session.add(blocked_extra)
        session.commit()
        session.refresh(allowed_extra)
        session.refresh(blocked_extra)
        allowed_extra_id = allowed_extra.id
        blocked_extra_id = blocked_extra.id

    client = TestClient(_make_app(engine, user))

    catalog_response = client.get("/api/configurator/catalog")
    assert catalog_response.status_code == 200
    catalog_extra_ids = [row["id"] for row in catalog_response.json()["extras"]]
    assert allowed_extra_id in catalog_extra_ids
    assert blocked_extra_id not in catalog_extra_ids

    preview_response = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [],
            "extras": [{"product_id": blocked_extra_id, "quantity": 1}],
        },
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["valid"] is False
    assert any(issue["code"] == "INVALID_EXTRA" for issue in preview_payload["issues"])


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
            configurator_is_starter_box=True,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        extra = Product(
            name="Rubber Matting",
            category=ProductCategory.STABLES,
            is_extra=True,
            allow_in_configurator=True,
            configurator_per_box=True,
            unit="Unit",
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
    mat_line = next(row for row in applied["items"] if row["description"] == "Rubber Matting")
    assert Decimal(mat_line["quantity"]) == Decimal("1")


def test_configurator_per_box_extra_quantity_tracks_box_count():
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
            configurator_is_starter_box=True,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        extra = Product(
            name="Rubber Matting",
            category=ProductCategory.STABLES,
            is_extra=True,
            allow_in_configurator=True,
            configurator_per_box=True,
            unit="Unit",
            base_price=Decimal("125.00"),
        )
        session.add(item)
        session.add(extra)
        session.commit()
        session.refresh(item)
        session.refresh(extra)
        item_id = item.id
        extra_id = extra.id

    client = TestClient(_make_app(engine, user))

    two_box_payload = {
        "schema_version": 1,
        "boxes": [
            {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
            {"id": "box-2", "product_id": item_id, "x": "3", "y": "0", "rotation": 0},
        ],
        "extras": [{"product_id": extra_id, "quantity": 1}],
    }
    preview = client.post("/api/configurator/preview", json=two_box_payload).json()
    assert preview["valid"] is True
    mat_line = next(row for row in preview["items"] if row["description"] == "Rubber Matting")
    assert Decimal(mat_line["quantity"]) == Decimal("2")
    assert Decimal(preview["subtotal"]) == Decimal("5250.00")


def test_deleted_boxes_do_not_reappear_after_save_and_reapply():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        first_item = Product(
            name="Front Box A",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        second_item = Product(
            name="Front Box B",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2750.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        quote = Quote(
            quote_number="QT-CONFIG-DELETE",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            created_by_id=user.id,
        )
        session.add(first_item)
        session.add(second_item)
        session.add(quote)
        session.commit()
        session.refresh(first_item)
        session.refresh(second_item)
        session.refresh(quote)
        quote_id = quote.id
        first_item_id = first_item.id
        second_item_id = second_item.id

    client = TestClient(_make_app(engine, user))

    initial_payload = {
        "schema_version": 1,
        "name": "Two box layout",
        "boxes": [
            {
                "id": "box-a",
                "product_id": first_item_id,
                "x": "0",
                "y": "0",
                "rotation": 0,
            },
            {
                "id": "box-b",
                "product_id": second_item_id,
                "x": "3.00",
                "y": "0",
                "rotation": 0,
            },
        ],
        "extras": [],
    }

    save_initial = client.put(f"/api/quotes/{quote_id}/configuration", json=initial_payload)
    assert save_initial.status_code == 200

    apply_initial = client.post(f"/api/quotes/{quote_id}/configuration/apply")
    assert apply_initial.status_code == 200
    initial_applied = apply_initial.json()
    assert {row["description"] for row in initial_applied["items"]} == {
        "Front Box A",
        "Front Box B",
    }

    updated_payload = {
        "schema_version": 1,
        "name": "One box layout",
        "boxes": [
            {
                "id": "box-a",
                "product_id": first_item_id,
                "x": "0",
                "y": "0",
                "rotation": 0,
            }
        ],
        "extras": [],
    }

    preview_updated = client.post("/api/configurator/preview", json=updated_payload)
    assert preview_updated.status_code == 200
    updated_preview = preview_updated.json()
    assert updated_preview["valid"] is True
    assert [row["description"] for row in updated_preview["items"]] == ["Front Box A"]

    save_updated = client.put(f"/api/quotes/{quote_id}/configuration", json=updated_payload)
    assert save_updated.status_code == 200
    saved_updated = save_updated.json()
    assert [box["id"] for box in saved_updated["configuration"]["boxes"]] == ["box-a"]

    apply_updated = client.post(f"/api/quotes/{quote_id}/configuration/apply")
    assert apply_updated.status_code == 200
    updated_applied = apply_updated.json()
    assert [row["description"] for row in updated_applied["items"]] == ["Front Box A"]
    assert len(updated_applied["items"]) == 1


def test_configurator_preview_enforces_zero_overlap_and_front_face_rules():
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
            configurator_is_starter_box=True,
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

    flush_stack = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "3.00", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert flush_stack.status_code == 200
    flush_payload = flush_stack.json()
    assert flush_payload["valid"] is True
    assert all(issue["code"] != "DISCONNECTED_LAYOUT" for issue in flush_payload["issues"])

    slight_overlap = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "2.99", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert slight_overlap.status_code == 200
    overlap_payload = slight_overlap.json()
    assert overlap_payload["valid"] is False
    assert any(issue["code"] == "OVERLAP" for issue in overlap_payload["issues"])

    slight_gap = client.post(
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
    assert slight_gap.status_code == 200
    gap_payload = slight_gap.json()
    assert gap_payload["valid"] is False
    assert any(issue["code"] == "DISCONNECTED_LAYOUT" for issue in gap_payload["issues"])

    front_blocked = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 90},
                {"id": "box-2", "product_id": item_id, "x": "3.00", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert front_blocked.status_code == 200
    front_payload = front_blocked.json()
    assert front_payload["valid"] is False
    assert any(issue["code"] == "FRONT_FACE_BLOCKED" for issue in front_payload["issues"])

    snapped_row = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "3.00", "y": "0", "rotation": 0},
                {"id": "box-3", "product_id": item_id, "x": "6.00", "y": "0", "rotation": 0},
                {"id": "box-4", "product_id": item_id, "x": "9.00", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert snapped_row.status_code == 200
    row_payload = snapped_row.json()
    assert row_payload["valid"] is True
    assert all(issue["code"] != "OVERLAP" for issue in row_payload["issues"])

    invalid_rotation = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 45},
            ],
            "extras": [],
        },
    )
    assert invalid_rotation.status_code == 422


def test_configurator_preview_uses_product_front_face_for_rectangular_items():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        item = Product(
            name="3.5 x 5 Rectangular Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2200.00"),
            configurator_width=Decimal("3.50"),
            configurator_length=Decimal("5.00"),
            configurator_front_face=ConfiguratorFrontFace.TOP,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        item_id = item.id

    client = TestClient(_make_app(engine, user))

    # Front on top (short edge); boxes joined along vertical faces — front stays exposed.
    side_join_front_exposed = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "3.50", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert side_join_front_exposed.status_code == 200
    exposed_payload = side_join_front_exposed.json()
    assert exposed_payload["valid"] is True
    assert all(issue["code"] != "FRONT_FACE_BLOCKED" for issue in exposed_payload["issues"])

    # Stack along y so top/bottom (front) faces meet.
    top_front_blocked = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": item_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": item_id, "x": "0", "y": "5.00", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert top_front_blocked.status_code == 200
    top_payload = top_front_blocked.json()
    assert top_payload["valid"] is False
    assert any(issue["code"] == "FRONT_FACE_BLOCKED" for issue in top_payload["issues"])


def test_corner_connection_profiles_restrict_front_segment_and_side_faces():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        standard_box = Product(
            name="3.5 Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1800.00"),
            configurator_width=Decimal("3.50"),
            configurator_length=Decimal("3.50"),
        )
        right_corner = Product(
            name="Right Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("5.00"),
            configurator_length=Decimal("3.50"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_RIGHT,
            configurator_is_corner_box=True,
        )
        left_corner = Product(
            name="Left Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("5.00"),
            configurator_length=Decimal("3.50"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_LEFT,
            configurator_is_corner_box=True,
        )
        session.add(standard_box)
        session.add(right_corner)
        session.add(left_corner)
        session.commit()
        session.refresh(standard_box)
        session.refresh(right_corner)
        session.refresh(left_corner)
        standard_box_id = standard_box.id
        right_corner_id = right_corner.id
        left_corner_id = left_corner.id

    client = TestClient(_make_app(engine, user))

    locked_rotation = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 90},
            ],
            "extras": [],
        },
    )
    assert locked_rotation.status_code == 200
    locked_payload = locked_rotation.json()
    assert locked_payload["valid"] is False
    assert any(issue["code"] == "CORNER_ROTATION_LOCKED" for issue in locked_payload["issues"])

    right_front_allowed = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "0", "y": "3.50", "rotation": 180},
            ],
            "extras": [],
        },
    )
    assert right_front_allowed.status_code == 200
    assert right_front_allowed.json()["valid"] is True

    right_front_blocked = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "1.50", "y": "3.50", "rotation": 180},
            ],
            "extras": [],
        },
    )
    assert right_front_blocked.status_code == 200
    right_front_blocked_payload = right_front_blocked.json()
    assert right_front_blocked_payload["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in right_front_blocked_payload["issues"])

    right_side_allowed = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "5.00", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert right_side_allowed.status_code == 200
    assert right_side_allowed.json()["valid"] is True

    right_forbidden_face = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "-3.50", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert right_forbidden_face.status_code == 200
    right_forbidden_face_payload = right_forbidden_face.json()
    assert right_forbidden_face_payload["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_FACE" for issue in right_forbidden_face_payload["issues"])

    left_front_allowed = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "1.50", "y": "3.50", "rotation": 180},
            ],
            "extras": [],
        },
    )
    assert left_front_allowed.status_code == 200
    assert left_front_allowed.json()["valid"] is True

    left_front_blocked = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "joiner", "product_id": standard_box_id, "x": "0", "y": "3.50", "rotation": 180},
            ],
            "extras": [],
        },
    )
    assert left_front_blocked.status_code == 200
    left_front_blocked_payload = left_front_blocked.json()
    assert left_front_blocked_payload["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in left_front_blocked_payload["issues"])


def test_corner_connection_profiles_rotate_their_physical_front_and_side_rules():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        standard_box = Product(
            name="3.5 Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1800.00"),
            configurator_width=Decimal("3.50"),
            configurator_length=Decimal("3.50"),
        )
        right_corner = Product(
            name="Right Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("5.00"),
            configurator_length=Decimal("3.50"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_RIGHT,
            configurator_is_corner_box=False,
        )
        left_corner = Product(
            name="Left Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("5.00"),
            configurator_length=Decimal("3.50"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_LEFT,
            configurator_is_corner_box=False,
        )
        session.add(standard_box)
        session.add(right_corner)
        session.add(left_corner)
        session.commit()
        session.refresh(standard_box)
        session.refresh(right_corner)
        session.refresh(left_corner)
        standard_box_id = standard_box.id
        right_corner_id = right_corner.id
        left_corner_id = left_corner.id

    client = TestClient(_make_app(engine, user))

    def preview(boxes):
        response = client.post(
            "/api/configurator/preview",
            json={
                "schema_version": 1,
                "boxes": boxes,
                "extras": [],
            },
        )
        assert response.status_code == 200
        return response.json()

    right_front_allowed_rotated_90 = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 90},
            {"id": "joiner", "product_id": standard_box_id, "x": "-2.75", "y": "-0.75", "rotation": 0},
        ]
    )
    assert right_front_allowed_rotated_90["valid"] is True

    right_front_blocked_rotated_90 = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 90},
            {"id": "joiner", "product_id": standard_box_id, "x": "-2.75", "y": "0.75", "rotation": 0},
        ]
    )
    assert right_front_blocked_rotated_90["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in right_front_blocked_rotated_90["issues"])

    left_standard_allowed_rotated_90 = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 90},
            {"id": "joiner", "product_id": standard_box_id, "x": "0.75", "y": "-4.25", "rotation": 0},
        ]
    )
    assert left_standard_allowed_rotated_90["valid"] is True

    left_forbidden_face_rotated_90 = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 90},
            {"id": "joiner", "product_id": standard_box_id, "x": "0.75", "y": "4.25", "rotation": 0},
        ]
    )
    assert left_forbidden_face_rotated_90["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_FACE" for issue in left_forbidden_face_rotated_90["issues"])

    left_front_allowed_rotated_180 = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 180},
            {"id": "joiner", "product_id": standard_box_id, "x": "0", "y": "-3.50", "rotation": 0},
        ]
    )
    assert left_front_allowed_rotated_180["valid"] is True

    left_front_blocked_rotated_180 = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 180},
            {"id": "joiner", "product_id": standard_box_id, "x": "1.50", "y": "-3.50", "rotation": 0},
        ]
    )
    assert left_front_blocked_rotated_180["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in left_front_blocked_rotated_180["issues"])

    right_front_allowed_rotated_270 = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 270},
            {"id": "joiner", "product_id": standard_box_id, "x": "4.25", "y": "0.75", "rotation": 0},
        ]
    )
    assert right_front_allowed_rotated_270["valid"] is True

    right_front_blocked_rotated_270 = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 270},
            {"id": "joiner", "product_id": standard_box_id, "x": "4.25", "y": "-0.75", "rotation": 0},
        ]
    )
    assert right_front_blocked_rotated_270["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in right_front_blocked_rotated_270["issues"])


def test_tall_corner_profiles_keep_front_on_the_long_side():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        standard_box = Product(
            name="3.5 Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1800.00"),
            configurator_width=Decimal("3.50"),
            configurator_length=Decimal("3.50"),
        )
        right_corner = Product(
            name="Tall Right Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("3.60"),
            configurator_length=Decimal("4.90"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_RIGHT,
            configurator_is_corner_box=True,
        )
        left_corner = Product(
            name="Tall Left Corner Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("2400.00"),
            configurator_width=Decimal("3.60"),
            configurator_length=Decimal("4.90"),
            configurator_front_face=ConfiguratorFrontFace.BOTTOM,
            configurator_connection_profile=ConfiguratorConnectionProfile.CORNER_LEFT,
            configurator_is_corner_box=True,
        )
        session.add(standard_box)
        session.add(right_corner)
        session.add(left_corner)
        session.commit()
        session.refresh(standard_box)
        session.refresh(right_corner)
        session.refresh(left_corner)
        standard_box_id = standard_box.id
        right_corner_id = right_corner.id
        left_corner_id = left_corner.id

    client = TestClient(_make_app(engine, user))

    def preview(boxes):
        response = client.post(
            "/api/configurator/preview",
            json={
                "schema_version": 1,
                "boxes": boxes,
                "extras": [],
            },
        )
        assert response.status_code == 200
        return response.json()

    right_front_allowed = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
            {"id": "joiner", "product_id": standard_box_id, "x": "-3.50", "y": "0", "rotation": 0},
        ]
    )
    assert right_front_allowed["valid"] is True

    right_front_blocked = preview(
        [
            {"id": "corner", "product_id": right_corner_id, "x": "0", "y": "0", "rotation": 0},
            {"id": "joiner", "product_id": standard_box_id, "x": "-3.50", "y": "1.40", "rotation": 0},
        ]
    )
    assert right_front_blocked["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in right_front_blocked["issues"])

    left_front_allowed = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 0},
            {"id": "joiner", "product_id": standard_box_id, "x": "3.60", "y": "0", "rotation": 0},
        ]
    )
    assert left_front_allowed["valid"] is True

    left_front_blocked = preview(
        [
            {"id": "corner", "product_id": left_corner_id, "x": "0", "y": "0", "rotation": 0},
            {"id": "joiner", "product_id": standard_box_id, "x": "3.60", "y": "1.40", "rotation": 0},
        ]
    )
    assert left_front_blocked["valid"] is False
    assert any(issue["code"] == "INVALID_CONNECTION_SEGMENT" for issue in left_front_blocked["issues"])


def test_optional_extra_cannot_be_marked_starter_box():
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
            "name": "Extra Starter",
            "category": "STABLES",
            "is_extra": True,
            "base_price": "50.00",
            "unit": "Unit",
            "configurator_is_starter_box": True,
        },
    )
    assert response.status_code == 422
    assert "starter boxes" in response.json()["detail"].lower()


def test_configurator_preview_requires_starter_box_in_layout():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        starter = Product(
            name="Starter SKU",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1000.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        regular = Product(
            name="Regular SKU",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=False,
            base_price=Decimal("1200.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(starter)
        session.add(regular)
        session.commit()
        session.refresh(starter)
        session.refresh(regular)
        regular_id = regular.id

    client = TestClient(_make_app(engine, user))
    preview = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": regular_id, "x": "0", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["valid"] is False
    assert any(issue["code"] == "STARTER_BOX_REQUIRED" for issue in payload["issues"])


def test_configurator_preview_accepts_layout_with_starter_box():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        starter = Product(
            name="Starter SKU",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1000.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(starter)
        session.commit()
        session.refresh(starter)
        starter_id = starter.id

    client = TestClient(_make_app(engine, user))
    preview = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": starter_id, "x": "0", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["valid"] is True
    assert not any(issue["code"] == "STARTER_BOX_REQUIRED" for issue in payload["issues"])


def test_configurator_preview_rejects_multiple_starter_boxes():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        starter_a = Product(
            name="Starter A",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1000.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        starter_b = Product(
            name="Starter B",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1100.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(starter_a)
        session.add(starter_b)
        session.commit()
        session.refresh(starter_a)
        session.refresh(starter_b)
        starter_a_id = starter_a.id
        starter_b_id = starter_b.id

    client = TestClient(_make_app(engine, user))
    preview = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": starter_a_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": starter_b_id, "x": "3", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["valid"] is False
    assert any(issue["code"] == "MULTIPLE_STARTER_BOXES" for issue in payload["issues"])


def test_configurator_preview_accepts_starter_plus_non_starter_box():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        starter = Product(
            name="Starter SKU",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=True,
            base_price=Decimal("1000.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        extension = Product(
            name="Extension Box",
            category=ProductCategory.CONFIGURATOR,
            configurator_is_starter_box=False,
            base_price=Decimal("900.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("3.00"),
        )
        session.add(starter)
        session.add(extension)
        session.commit()
        session.refresh(starter)
        session.refresh(extension)
        starter_id = starter.id
        extension_id = extension.id

    client = TestClient(_make_app(engine, user))
    preview = client.post(
        "/api/configurator/preview",
        json={
            "schema_version": 1,
            "boxes": [
                {"id": "box-1", "product_id": starter_id, "x": "0", "y": "0", "rotation": 0},
                {"id": "box-2", "product_id": extension_id, "x": "3", "y": "0", "rotation": 0},
            ],
            "extras": [],
        },
    )
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["valid"] is True
    assert not any(issue["code"] == "MULTIPLE_STARTER_BOXES" for issue in payload["issues"])


def test_save_empty_configuration_and_placeholder_draft_reset():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        quote = Quote(
            quote_number="QT-RESET-001",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("1000.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        quote_id = quote.id

    client = TestClient(_make_app(engine, user))

    empty_payload = {
        "schema_version": 1,
        "name": "QT-RESET-001",
        "boxes": [],
        "extras": [],
    }

    preview_response = client.post("/api/configurator/preview", json=empty_payload)
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["valid"] is False
    assert preview["items"] == []
    assert any(issue["code"] == "EMPTY_LAYOUT" for issue in preview["issues"])

    save_response = client.put(f"/api/quotes/{quote_id}/configuration", json=empty_payload)
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["configuration"]["boxes"] == []
    assert saved["configuration"]["extras"] == []

    draft_response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "description": "Draft — in progress",
                    "quantity": 1,
                    "unit_price": 0,
                    "is_custom": True,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert len(draft["items"]) == 1
    assert draft["items"][0]["description"] == "Draft — in progress"
    assert Decimal(draft["subtotal"]) == Decimal("0")
