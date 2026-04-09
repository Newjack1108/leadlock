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

from app.routers.webhooks import import_product_webhook
from app.schemas import ProductImportPayload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


@pytest.mark.asyncio
async def test_import_extra_uses_payload_category_precedence():
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

        await import_product_webhook(payload=payload, _api_key="test", session=session)

        product = session.exec(select(Product).where(Product.production_product_id == 101)).first()
        assert product is not None
        assert product.is_extra is True
        assert product.category == ProductCategory.SHEDS


@pytest.mark.asyncio
async def test_import_non_extra_uses_payload_category():
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

        await import_product_webhook(payload=payload, _api_key="test", session=session)

        product = session.exec(select(Product).where(Product.production_product_id == 102)).first()
        assert product is not None
        assert product.is_extra is False
        assert product.category == ProductCategory.CABINS


@pytest.mark.asyncio
async def test_import_missing_category_falls_back_to_product_type():
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

        await import_product_webhook(payload=payload, _api_key="test", session=session)

        product = session.exec(select(Product).where(Product.production_product_id == 103)).first()
        assert product is not None
        assert product.is_extra is False
        assert product.category == ProductCategory.SHEDS


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
