import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import require_dealer_user
from app.database import get_session
from app.models import (
    Dealer,
    DealerDiscountMode,
    DealerDiscountPolicy,
    Product,
    ProductCategory,
    User,
    UserRole,
)
from app.routers import dealer_portal


def _make_app(engine, dealer_user):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(dealer_portal.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[require_dealer_user] = lambda: dealer_user
    return app


def test_dealer_portal_profile_quote_pdf_smoke(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Smoke Dealer", company_name="Smoke Dealer Ltd")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-smoke@example.com",
            hashed_password="dummy",
            full_name="Dealer Smoke",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        product = Product(
            name="Stable A",
            category=ProductCategory.STABLES,
            base_price=Decimal("1000.00"),
            allow_trade_dealer_sale=True,
        )
        session.add(user)
        session.add(product)
        session.commit()
        session.refresh(user)
        session.refresh(product)

        session.add(
            DealerDiscountPolicy(
                dealer_id=dealer.id,
                mode=DealerDiscountMode.TEMPLATE,
                allow_fixed_amount=False,
                allow_percentage=False,
            )
        )
        session.commit()
        user_ctx_data = {
            "id": user.id,
            "dealer_id": user.dealer_id,
            "dealer_commission_pct": user.dealer_commission_pct,
            "role": user.role,
            "full_name": user.full_name,
        }
        product_id = product.id

    async def _fake_upload(_):
        return "/static/products/dealer-smoke.png"

    monkeypatch.setattr("app.routers.dealer_portal.upload_product_image", _fake_upload)

    captured = {}

    def _fake_pdf(**kwargs):
        captured.update(kwargs)
        return (b"%PDF-1.4 smoke", False)

    monkeypatch.setattr("app.routers.dealer_portal.generate_quote_pdf_cached", _fake_pdf)

    dealer_user_ctx = SimpleNamespace(
        id=user_ctx_data["id"],
        dealer_id=user_ctx_data["dealer_id"],
        dealer_commission_pct=user_ctx_data["dealer_commission_pct"],
        role=user_ctx_data["role"],
        full_name=user_ctx_data["full_name"],
    )
    app = _make_app(engine, dealer_user_ctx)
    client = TestClient(app)

    get_profile = client.get("/api/dealer-portal/profile")
    assert get_profile.status_code == 200

    save_profile = client.put(
        "/api/dealer-portal/profile",
        json={
            "company_name": "Smoke Trading",
            "contact_name": "Kelly Smoke",
            "email": "trade@example.com",
            "phone": "01234567890",
            "address": "1 Smoke Road",
            "vat_number": "VAT-123",
            "registration_number": "REG-123",
            "website": "https://trade.example.com",
        },
    )
    assert save_profile.status_code == 200
    assert save_profile.json()["company_name"] == "Smoke Trading"

    logo = client.post(
        "/api/dealer-portal/profile/logo",
        files={"logo": ("logo.png", b"pngdata", "image/png")},
    )
    assert logo.status_code == 200
    assert logo.json()["logo_url"] == "/static/products/dealer-smoke.png"

    quote = client.post(
        "/api/dealer-portal/quotes",
        json={
            "customer_name": "Manual Customer",
            "customer_email": "manual@example.com",
            "customer_phone": "07000 111222",
            "customer_address": "2 Manual Street",
                "product_items": [{"product_id": product_id, "quantity": 1}],
            "discount_template_ids": [],
        },
    )
    assert quote.status_code == 200
    quote_id = quote.json()["id"]
    assert quote.json()["dealer_customer_name"] == "Manual Customer"

    pdf = client.get(f"/api/dealer-portal/quotes/{quote_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-1.4")
    assert captured["trader_logo_url"] == "/static/products/dealer-smoke.png"
    assert captured["dealer_profile"]["company_name"] == "Smoke Trading"
    assert "profile:" in captured["cache_key"]


def test_dealer_products_and_quote_respect_trade_toggle():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Toggle Dealer")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-toggle@example.com",
            hashed_password="dummy",
            full_name="Dealer Toggle",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        allowed_product = Product(
            name="Trade Enabled Product",
            category=ProductCategory.STABLES,
            base_price=Decimal("1500.00"),
            allow_trade_dealer_sale=True,
        )
        blocked_product = Product(
            name="Trade Disabled Product",
            category=ProductCategory.STABLES,
            base_price=Decimal("900.00"),
            allow_trade_dealer_sale=False,
        )
        extra_only = Product(
            name="Optional Extra Only",
            category=ProductCategory.STABLES,
            base_price=Decimal("50.00"),
            is_extra=True,
            allow_trade_dealer_sale=True,
        )
        session.add(user)
        session.add(allowed_product)
        session.add(blocked_product)
        session.add(extra_only)
        session.commit()
        session.refresh(user)
        session.refresh(allowed_product)
        session.refresh(blocked_product)
        session.refresh(extra_only)

        session.add(
            DealerDiscountPolicy(
                dealer_id=dealer.id,
                mode=DealerDiscountMode.TEMPLATE,
                allow_fixed_amount=False,
                allow_percentage=False,
            )
        )
        session.commit()

        user_ctx_data = {
            "id": user.id,
            "dealer_id": user.dealer_id,
            "dealer_commission_pct": user.dealer_commission_pct,
            "role": user.role,
            "full_name": user.full_name,
        }
        allowed_id = allowed_product.id
        blocked_id = blocked_product.id
        extra_only_id = extra_only.id

    dealer_user_ctx = SimpleNamespace(
        id=user_ctx_data["id"],
        dealer_id=user_ctx_data["dealer_id"],
        dealer_commission_pct=user_ctx_data["dealer_commission_pct"],
        role=user_ctx_data["role"],
        full_name=user_ctx_data["full_name"],
    )
    app = _make_app(engine, dealer_user_ctx)
    client = TestClient(app)

    products_res = client.get("/api/dealer-portal/products")
    assert products_res.status_code == 200
    returned_ids = {item["id"] for item in products_res.json()}
    assert allowed_id in returned_ids
    assert blocked_id not in returned_ids
    assert extra_only_id not in returned_ids

    blocked_quote = client.post(
        "/api/dealer-portal/quotes",
        json={
            "customer_name": "Blocked Customer",
            "product_items": [{"product_id": blocked_id, "quantity": 1}],
            "discount_template_ids": [],
        },
    )
    assert blocked_quote.status_code == 403
    assert blocked_quote.json()["detail"] == "Product not available for trade dealer sale"
