"""Tests for product import gross margin (company default vs per-product override)."""
import asyncio
from decimal import Decimal
import sys
import types

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import CompanySettings, Product, User, UserRole

fake_database = types.ModuleType("app.database")
fake_database.get_session = lambda: None
sys.modules.setdefault("app.database", fake_database)

from app.routers.webhooks import import_product_webhook
from app.schemas import ProductImportPayload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _set_company_margin(session: Session, margin_pct: Decimal | None) -> None:
    settings = session.exec(select(CompanySettings)).first()
    if settings is None:
        user = User(
            email="margin-test@example.com",
            hashed_password="x",
            full_name="Margin Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        settings = CompanySettings(
            company_name="Test Co",
            product_import_gross_margin_pct=margin_pct,
            updated_by_id=user.id,
        )
    else:
        settings.product_import_gross_margin_pct = margin_pct
    session.add(settings)
    session.commit()


def _base_payload(**overrides) -> ProductImportPayload:
    data = {
        "product_id": 501,
        "name": "Margin Test Product",
        "description": "",
        "price_ex_vat": Decimal("70"),
        "install_hours": Decimal("1"),
        "number_of_boxes": Decimal("1"),
        "product_type": "product",
        "category": "sheds",
    }
    data.update(overrides)
    return ProductImportPayload(**data)


def test_company_margin_applied_when_payload_omits_margin():
    with _session() as session:
        _set_company_margin(session, Decimal("30"))
        # cost 70 at 30% gross margin → RRP = 70 / 0.7 = 100
        asyncio.run(
            import_product_webhook(payload=_base_payload(), _api_key="test", session=session)
        )
        product = session.exec(select(Product).where(Product.production_product_id == 501)).first()
        assert product is not None
        assert product.base_price == Decimal("100.00")


def test_payload_margin_overrides_company_margin():
    with _session() as session:
        _set_company_margin(session, Decimal("30"))
        # cost 70 at 40% → RRP = 70 / 0.6 ≈ 116.67
        asyncio.run(
            import_product_webhook(
                payload=_base_payload(gross_margin_pct=Decimal("40"), product_id=502, name="Override"),
                _api_key="test",
                session=session,
            )
        )
        product = session.exec(select(Product).where(Product.production_product_id == 502)).first()
        assert product is not None
        assert product.base_price == Decimal("116.67")


def test_payload_margin_zero_sells_at_cost_despite_company_margin():
    with _session() as session:
        _set_company_margin(session, Decimal("30"))
        asyncio.run(
            import_product_webhook(
                payload=_base_payload(gross_margin_pct=Decimal("0"), product_id=503, name="At Cost"),
                _api_key="test",
                session=session,
            )
        )
        product = session.exec(select(Product).where(Product.production_product_id == 503)).first()
        assert product is not None
        assert product.base_price == Decimal("70")


def test_no_company_margin_and_no_payload_margin_uses_cost():
    with _session() as session:
        # No CompanySettings row → company margin is None
        asyncio.run(
            import_product_webhook(
                payload=_base_payload(product_id=504, name="No Margin"),
                _api_key="test",
                session=session,
            )
        )
        product = session.exec(select(Product).where(Product.production_product_id == 504)).first()
        assert product is not None
        assert product.base_price == Decimal("70")
