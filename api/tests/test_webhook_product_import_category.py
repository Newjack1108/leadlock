import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from app.models import Product, ProductCategory

fake_database = types.ModuleType("app.database")
fake_database.get_session = lambda: None
sys.modules.setdefault("app.database", fake_database)

from app.routers.webhooks import import_product_webhook, import_products_batch_webhook
from app.schemas import ProductImportPayload, ProductImportBatchPayload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_import_extra_uses_payload_category_precedence():
    with _session() as session:
        payload = ProductImportPayload(
            product_id=101,
            name="Extra A",
            description="",
            price_ex_vat=Decimal("100"),
            install_hours=Decimal("1"),
            number_of_boxes=Decimal("1"),
            product_type="extra",
            category="sheds",
        )

        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 101)).first()
        assert product is not None
        assert product.is_extra is True
        assert product.category == ProductCategory.SHEDS
        assert product.production_pushed_at is not None


def test_import_non_extra_uses_payload_category():
    with _session() as session:
        payload = ProductImportPayload(
            product_id=102,
            name="Cabin Main",
            description="",
            price_ex_vat=Decimal("100"),
            install_hours=Decimal("1"),
            number_of_boxes=Decimal("1"),
            product_type="product",
            category="cabins",
        )

        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 102)).first()
        assert product is not None
        assert product.is_extra is False
        assert product.category == ProductCategory.CABINS


def test_import_missing_category_falls_back_to_product_type():
    with _session() as session:
        payload = ProductImportPayload(
            product_id=103,
            name="Shed Main",
            description="",
            price_ex_vat=Decimal("100"),
            install_hours=Decimal("1"),
            number_of_boxes=Decimal("1"),
            product_type="sheds",
        )

        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 103)).first()
        assert product is not None
        assert product.is_extra is False
        assert product.category == ProductCategory.SHEDS


def test_import_sets_production_pushed_at_and_updates_on_reimport():
    with _session() as session:
        payload = ProductImportPayload(
            product_id=201,
            name="Pushed Product",
            description="",
            price_ex_vat=Decimal("100"),
            install_hours=Decimal("1"),
            number_of_boxes=Decimal("1"),
            product_type="product",
            category="stables",
        )

        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 201)).first()
        assert product is not None
        assert product.production_pushed_at is not None

        past = datetime.utcnow() - timedelta(hours=1)
        product.production_pushed_at = past
        session.add(product)
        session.commit()

        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        session.refresh(product)
        assert product.production_pushed_at is not None
        assert product.production_pushed_at > past


def test_update_by_product_id_keeps_leadlock_name_and_applies_pricing_ops():
    with _session() as session:
        create_payload = ProductImportPayload(
            product_id=301,
            name="Production Name",
            description="From production",
            price_ex_vat=Decimal("100"),
            install_hours=Decimal("1"),
            number_of_boxes=Decimal("1"),
            product_type="product",
            category="stables",
        )
        asyncio.run(import_product_webhook(payload=create_payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 301)).first()
        assert product is not None
        product.name = "LeadLock Display Name"
        product.description = "Staff-edited description"
        session.add(product)
        session.commit()

        update_payload = ProductImportPayload(
            product_id=301,
            name="Production Name Changed",
            description="Should not overwrite description",
            price_ex_vat=Decimal("200"),
            install_hours=Decimal("2.5"),
            number_of_boxes=Decimal("3"),
            product_type="extra",
            category="sheds",
        )
        asyncio.run(import_product_webhook(payload=update_payload, _api_key="test", session=session))

        session.refresh(product)
        assert product.name == "LeadLock Display Name"
        assert product.description == "Staff-edited description"
        assert product.base_price == Decimal("200")
        assert product.installation_hours == Decimal("2.5")
        assert product.boxes_per_product == 3
        assert product.is_extra is True
        assert product.category == ProductCategory.SHEDS


def test_create_still_uses_payload_name():
    with _session() as session:
        payload = ProductImportPayload(
            product_id=302,
            name="Brand New Product",
            description="Created from production",
            price_ex_vat=Decimal("50"),
            install_hours=Decimal("0.5"),
            number_of_boxes=Decimal("2"),
            product_type="product",
            category="cabins",
        )
        asyncio.run(import_product_webhook(payload=payload, _api_key="test", session=session))

        product = session.exec(select(Product).where(Product.production_product_id == 302)).first()
        assert product is not None
        assert product.name == "Brand New Product"
        assert product.description == "Created from production"


def test_invalid_category_returns_422_validation_error():
    app = FastAPI()

    @app.post("/validate")
    async def validate(payload: ProductImportPayload):
        return {"ok": True, "category": payload.category}

    client = TestClient(app)
    response = client.post(
        "/validate",
        json={
            "product_id": 104,
            "name": "Invalid Category",
            "description": "",
            "price_ex_vat": "100",
            "install_hours": "1",
            "number_of_boxes": "1",
            "product_type": "product",
            "category": "other",
        },
    )
    assert response.status_code == 422


def test_batch_import_mixed_create_update_and_partial_failure():
    with _session() as session:
        asyncio.run(
            import_product_webhook(
                payload=ProductImportPayload(
                    product_id=401,
                    name="Existing Batch Product",
                    description="",
                    price_ex_vat=Decimal("100"),
                    install_hours=Decimal("1"),
                    number_of_boxes=Decimal("1"),
                    product_type="product",
                    category="stables",
                ),
                _api_key="test",
                session=session,
            )
        )

        batch = ProductImportBatchPayload(
            products=[
                {
                    "product_id": 401,
                    "name": "Existing Batch Product Renamed",
                    "description": "should not overwrite after product_id match",
                    "price_ex_vat": "150",
                    "install_hours": "2",
                    "number_of_boxes": "2",
                    "product_type": "product",
                    "category": "sheds",
                },
                {
                    "product_id": 402,
                    "name": "New Batch Product",
                    "description": "Created in batch",
                    "price_ex_vat": "50",
                    "install_hours": "0.5",
                    "number_of_boxes": "1",
                    "product_type": "product",
                    "category": "cabins",
                },
                {
                    "product_id": 403,
                    "name": "Bad Type Product",
                    "description": "",
                    "price_ex_vat": "10",
                    "install_hours": "1",
                    "number_of_boxes": "1",
                    "product_type": "other",
                    "category": "stables",
                },
            ]
        )

        response = asyncio.run(
            import_products_batch_webhook(payload=batch, _api_key="test", session=session)
        )

        assert response.success is False
        assert len(response.results) == 3
        assert response.results[0].success is True
        assert response.results[0].production_product_id == 401
        assert response.results[0].product_id is not None
        assert response.results[1].success is True
        assert response.results[1].production_product_id == 402
        assert response.results[2].success is False
        assert response.results[2].production_product_id == 403
        assert response.results[2].error

        existing = session.exec(select(Product).where(Product.production_product_id == 401)).first()
        assert existing is not None
        assert existing.name == "Existing Batch Product"
        assert existing.base_price == Decimal("150")
        assert existing.category == ProductCategory.SHEDS

        created = session.exec(select(Product).where(Product.production_product_id == 402)).first()
        assert created is not None
        assert created.name == "New Batch Product"
        assert created.category == ProductCategory.CABINS

        missing = session.exec(select(Product).where(Product.production_product_id == 403)).first()
        assert missing is None


def test_batch_import_invalid_category_item_does_not_block_others():
    with _session() as session:
        batch = ProductImportBatchPayload(
            products=[
                {
                    "product_id": 501,
                    "name": "Good Product",
                    "description": "",
                    "price_ex_vat": "100",
                    "install_hours": "1",
                    "number_of_boxes": "1",
                    "product_type": "product",
                    "category": "stables",
                },
                {
                    "product_id": 502,
                    "name": "Bad Category",
                    "description": "",
                    "price_ex_vat": "100",
                    "install_hours": "1",
                    "number_of_boxes": "1",
                    "product_type": "product",
                    "category": "other",
                },
            ]
        )

        response = asyncio.run(
            import_products_batch_webhook(payload=batch, _api_key="test", session=session)
        )

        assert response.success is False
        assert response.results[0].success is True
        assert response.results[1].success is False
        assert "category" in (response.results[1].error or "").lower()

        good = session.exec(select(Product).where(Product.production_product_id == 501)).first()
        assert good is not None
