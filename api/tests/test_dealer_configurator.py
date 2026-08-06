import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import require_dealer_configurator_access, require_dealer_user
from app.database import get_session
from app.models import (
    Dealer,
    DealerAllowedDiscount,
    DealerDiscountMode,
    DealerDiscountPolicy,
    DiscountScope,
    DiscountTemplate,
    DiscountType,
    Product,
    ProductCategory,
    User,
    UserRole,
)
from app.routers import dealer_portal, configurator
from app.auth import require_configurator_access


def _make_dealer_app(engine, dealer_user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(dealer_portal.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[require_dealer_user] = lambda: dealer_user
    app.dependency_overrides[require_dealer_configurator_access] = lambda: dealer_user
    return app


def test_require_dealer_configurator_access_requires_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "false")
    user = User(
        id=1,
        email="dealer@example.com",
        hashed_password="dummy",
        full_name="Dealer",
        role=UserRole.DEALER_USER,
        dealer_id=1,
        dealer_commission_pct=10,
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_dealer_configurator_access(current_user=user))
    assert exc.value.status_code == 403


def test_require_dealer_configurator_access_accepts_enabled_dealer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    user = User(
        id=1,
        email="dealer@example.com",
        hashed_password="dummy",
        full_name="Dealer",
        role=UserRole.DEALER_USER,
        dealer_id=1,
        dealer_commission_pct=10,
    )
    result = asyncio.run(require_dealer_configurator_access(current_user=user))
    assert result.email == "dealer@example.com"


def test_dealer_configurator_catalog_filters_trade_sale(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Cfg Dealer", company_name="Cfg Dealer Ltd")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-cfg@example.com",
            hashed_password="dummy",
            full_name="Dealer Cfg",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        allowed = Product(
            name="Starter Allowed",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("1000.00"),
            allow_trade_dealer_sale=True,
            configurator_width=Decimal("3"),
            configurator_length=Decimal("3"),
            configurator_is_starter_box=True,
        )
        blocked = Product(
            name="Starter Blocked",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("1000.00"),
            allow_trade_dealer_sale=False,
            configurator_width=Decimal("3"),
            configurator_length=Decimal("3"),
            configurator_is_starter_box=True,
        )
        extra_allowed = Product(
            name="Extra Allowed",
            category=ProductCategory.STABLES,
            base_price=Decimal("50.00"),
            is_extra=True,
            allow_in_configurator=True,
            allow_trade_dealer_sale=True,
        )
        extra_blocked = Product(
            name="Extra Blocked",
            category=ProductCategory.STABLES,
            base_price=Decimal("50.00"),
            is_extra=True,
            allow_in_configurator=True,
            allow_trade_dealer_sale=False,
        )
        session.add(user)
        session.add(allowed)
        session.add(blocked)
        session.add(extra_allowed)
        session.add(extra_blocked)
        session.commit()
        session.refresh(user)

        dealer_user = SimpleNamespace(
            id=user.id,
            dealer_id=user.dealer_id,
            dealer_commission_pct=user.dealer_commission_pct,
            role=user.role,
            full_name=user.full_name,
        )

    app = _make_dealer_app(engine, dealer_user)
    client = TestClient(app)

    res = client.get("/api/dealer-portal/configurator/catalog")
    assert res.status_code == 200
    names = {item["name"] for item in res.json()["items"]}
    extra_names = {item["name"] for item in res.json()["extras"]}
    assert "Starter Allowed" in names
    assert "Starter Blocked" not in names
    assert "Extra Allowed" in extra_names
    assert "Extra Blocked" not in extra_names


def test_dealer_configurator_draft_save_and_isolation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer_a = Dealer(name="Dealer A", company_name="A Ltd")
        dealer_b = Dealer(name="Dealer B", company_name="B Ltd")
        session.add(dealer_a)
        session.add(dealer_b)
        session.commit()
        session.refresh(dealer_a)
        session.refresh(dealer_b)

        user_a = User(
            email="dealer-a@example.com",
            hashed_password="dummy",
            full_name="Dealer A User",
            role=UserRole.DEALER_USER,
            dealer_id=dealer_a.id,
            dealer_commission_pct=10,
        )
        user_b = User(
            email="dealer-b@example.com",
            hashed_password="dummy",
            full_name="Dealer B User",
            role=UserRole.DEALER_USER,
            dealer_id=dealer_b.id,
            dealer_commission_pct=15,
        )
        session.add(user_a)
        session.add(user_b)
        session.commit()
        session.refresh(user_a)
        session.refresh(user_b)

        ctx_a = SimpleNamespace(
            id=user_a.id,
            dealer_id=user_a.dealer_id,
            dealer_commission_pct=user_a.dealer_commission_pct,
            role=user_a.role,
            full_name=user_a.full_name,
        )
        ctx_b = SimpleNamespace(
            id=user_b.id,
            dealer_id=user_b.dealer_id,
            dealer_commission_pct=user_b.dealer_commission_pct,
            role=user_b.role,
            full_name=user_b.full_name,
        )

    app_a = _make_dealer_app(engine, ctx_a)
    client_a = TestClient(app_a)

    draft = client_a.post(
        "/api/dealer-portal/quotes/configurator-draft",
        json={"customer_name": "Alice", "customer_postcode": "CW1 1AA"},
    )
    assert draft.status_code == 200
    quote_id = draft.json()["id"]
    assert draft.json()["dealer_customer_name"] == "Alice"
    assert any(item["description"] == "Draft — in progress" for item in draft.json()["items"])

    save = client_a.put(
        f"/api/dealer-portal/quotes/{quote_id}/configuration",
        json={"schema_version": 1, "name": "Layout A", "boxes": [], "extras": []},
    )
    assert save.status_code == 200
    assert save.json()["configuration"]["name"] == "Layout A"

    get_cfg = client_a.get(f"/api/dealer-portal/quotes/{quote_id}/configuration")
    assert get_cfg.status_code == 200

    app_b = _make_dealer_app(engine, ctx_b)
    client_b = TestClient(app_b)
    blocked = client_b.get(f"/api/dealer-portal/quotes/{quote_id}/configuration")
    assert blocked.status_code == 404

    reset = client_a.post(f"/api/dealer-portal/quotes/{quote_id}/configuration/reset")
    assert reset.status_code == 200
    assert any(item["description"] == "Draft — in progress" for item in reset.json()["items"])


def test_staff_configurator_routes_still_reject_dealers(monkeypatch: pytest.MonkeyPatch):
    """Staff sales configurator must remain blocked for dealer roles."""
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    monkeypatch.setenv("CONFIGURATOR_ALLOWED_EMAILS", "dealer@example.com")

    dealer = User(
        id=9,
        email="dealer@example.com",
        hashed_password="dummy",
        full_name="Dealer",
        role=UserRole.DEALER_USER,
        dealer_id=1,
        dealer_commission_pct=10,
    )

    def get_session_override():
        yield None

    app = FastAPI()
    app.include_router(configurator.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[require_configurator_access] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=403, detail="Configurator access is not enabled for this account")
    )

    # Direct auth check remains blocked
    from app.auth import has_configurator_access

    assert has_configurator_access(dealer) is False

    client = TestClient(app)
    res = client.get("/api/configurator/catalog")
    assert res.status_code == 403


def _seed_dealer_configurator_apply_fixture(engine):
    with Session(engine) as session:
        dealer = Dealer(name="Discount Dealer", company_name="Discount Dealer Ltd")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-discount-cfg@example.com",
            hashed_password="dummy",
            full_name="Dealer Discount Cfg",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        product = Product(
            name="3m Trade Box",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("1000.00"),
            allow_trade_dealer_sale=True,
            configurator_width=Decimal("3"),
            configurator_length=Decimal("3"),
            configurator_is_starter_box=True,
        )
        session.add(user)
        session.add(product)
        session.commit()
        session.refresh(user)
        session.refresh(product)

        allowed = DiscountTemplate(
            name="10% off quote",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10"),
            scope=DiscountScope.QUOTE,
            is_active=True,
            created_by_id=user.id,
        )
        blocked = DiscountTemplate(
            name="20% not allowed",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("20"),
            scope=DiscountScope.QUOTE,
            is_active=True,
            created_by_id=user.id,
        )
        session.add(allowed)
        session.add(blocked)
        session.commit()
        session.refresh(allowed)
        session.refresh(blocked)

        session.add(
            DealerDiscountPolicy(
                dealer_id=dealer.id,
                mode=DealerDiscountMode.TEMPLATE,
                allow_fixed_amount=False,
                allow_percentage=False,
            )
        )
        session.add(DealerAllowedDiscount(dealer_id=dealer.id, discount_template_id=allowed.id))
        session.commit()

        dealer_user = SimpleNamespace(
            id=user.id,
            dealer_id=user.dealer_id,
            dealer_commission_pct=user.dealer_commission_pct,
            role=user.role,
            full_name=user.full_name,
        )
        return {
            "dealer_user": dealer_user,
            "product_id": product.id,
            "allowed_template_id": allowed.id,
            "blocked_template_id": blocked.id,
        }


def test_dealer_configurator_apply_with_allowed_discount(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    fixture = _seed_dealer_configurator_apply_fixture(engine)
    client = TestClient(_make_dealer_app(engine, fixture["dealer_user"]))

    draft = client.post(
        "/api/dealer-portal/quotes/configurator-draft",
        json={"customer_name": "Discount Customer", "customer_postcode": "CW1 1AA"},
    )
    assert draft.status_code == 200
    quote_id = draft.json()["id"]

    save = client.put(
        f"/api/dealer-portal/quotes/{quote_id}/configuration",
        json={
            "schema_version": 1,
            "name": "Discount layout",
            "boxes": [
                {
                    "id": "box-1",
                    "product_id": fixture["product_id"],
                    "x": "0",
                    "y": "0",
                    "rotation": 0,
                }
            ],
            "extras": [],
        },
    )
    assert save.status_code == 200

    apply = client.post(
        f"/api/dealer-portal/quotes/{quote_id}/configuration/apply",
        json={"discount_template_ids": [fixture["allowed_template_id"]]},
    )
    assert apply.status_code == 200
    body = apply.json()
    assert Decimal(str(body["subtotal"])) == Decimal("1000.00")
    assert Decimal(str(body["discount_total"])) == Decimal("100.00")
    assert Decimal(str(body["total_amount"])) == Decimal("900.00")
    assert any(d.get("template_id") == fixture["allowed_template_id"] for d in body.get("discounts") or [])


def test_dealer_configurator_apply_rejects_disallowed_discount(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONFIGURATOR_ENABLED", "true")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    fixture = _seed_dealer_configurator_apply_fixture(engine)
    client = TestClient(_make_dealer_app(engine, fixture["dealer_user"]))

    draft = client.post(
        "/api/dealer-portal/quotes/configurator-draft",
        json={"customer_name": "Blocked Discount Customer"},
    )
    assert draft.status_code == 200
    quote_id = draft.json()["id"]

    save = client.put(
        f"/api/dealer-portal/quotes/{quote_id}/configuration",
        json={
            "schema_version": 1,
            "name": "Blocked layout",
            "boxes": [
                {
                    "id": "box-1",
                    "product_id": fixture["product_id"],
                    "x": "0",
                    "y": "0",
                    "rotation": 0,
                }
            ],
            "extras": [],
        },
    )
    assert save.status_code == 200

    apply = client.post(
        f"/api/dealer-portal/quotes/{quote_id}/configuration/apply",
        json={"discount_template_ids": [fixture["blocked_template_id"]]},
    )
    assert apply.status_code == 403
    assert "not permitted" in apply.json()["detail"].lower()
