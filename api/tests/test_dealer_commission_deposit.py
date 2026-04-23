import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import require_dealer_user
from app.constants import VAT_RATE_DECIMAL
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


def _expected_deposit_balance(ex_vat_net: Decimal, commission_pct: int) -> tuple[Decimal, Decimal]:
    total_inc_vat = (ex_vat_net * (Decimal("1") + VAT_RATE_DECIMAL)).quantize(Decimal("0.01"))
    dep = (total_inc_vat * Decimal(commission_pct) / Decimal(100)).quantize(Decimal("0.01"))
    if dep > total_inc_vat:
        dep = total_inc_vat
    bal = total_inc_vat - dep
    return dep, bal


def test_dealer_quote_deposit_matches_commission_on_inc_vat_without_discount():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Comm Dealer")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-comm@example.com",
            hashed_password="dummy",
            full_name="Dealer Comm",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        product = Product(
            name="Pavilion",
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
        product_id = product.id
        user_id = user.id
        dealer_id = user.dealer_id

    dealer_user_ctx = SimpleNamespace(
        id=user_id,
        dealer_id=dealer_id,
        dealer_commission_pct=10,
        role=UserRole.DEALER_USER,
        full_name="Dealer Comm",
    )
    app = _make_app(engine, dealer_user_ctx)
    client = TestClient(app)

    res = client.post(
        "/api/dealer-portal/quotes",
        json={
            "customer_name": "Test Customer",
            "product_items": [{"product_id": product_id, "quantity": 1}],
            "discount_template_ids": [],
        },
    )
    assert res.status_code == 200
    body = res.json()
    exp_dep, exp_bal = _expected_deposit_balance(Decimal("1000.00"), 10)
    assert Decimal(str(body["deposit_amount"])) == exp_dep
    assert Decimal(str(body["balance_amount"])) == exp_bal


def test_dealer_quote_deposit_uses_post_discount_inc_vat_total():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Comm Dealer 2")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-comm2@example.com",
            hashed_password="dummy",
            full_name="Dealer Comm 2",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=10,
        )
        product = Product(
            name="Barn",
            category=ProductCategory.STABLES,
            base_price=Decimal("1000.00"),
            allow_trade_dealer_sale=True,
        )
        session.add(user)
        session.add(product)
        session.commit()
        session.refresh(user)
        session.refresh(product)

        template = DiscountTemplate(
            name="10% off quote",
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10"),
            scope=DiscountScope.QUOTE,
            is_active=True,
            created_by_id=user.id,
        )
        session.add(template)
        session.commit()
        session.refresh(template)

        session.add(
            DealerDiscountPolicy(
                dealer_id=dealer.id,
                mode=DealerDiscountMode.TEMPLATE,
                allow_fixed_amount=False,
                allow_percentage=False,
            )
        )
        session.add(
            DealerAllowedDiscount(dealer_id=dealer.id, discount_template_id=template.id),
        )
        session.commit()
        product_id = product.id
        template_id = template.id
        user_id = user.id
        dealer_id = user.dealer_id

    dealer_user_ctx = SimpleNamespace(
        id=user_id,
        dealer_id=dealer_id,
        dealer_commission_pct=10,
        role=UserRole.DEALER_USER,
        full_name="Dealer Comm 2",
    )
    app = _make_app(engine, dealer_user_ctx)
    client = TestClient(app)

    res = client.post(
        "/api/dealer-portal/quotes",
        json={
            "customer_name": "Discount Customer",
            "product_items": [{"product_id": product_id, "quantity": 1}],
            "discount_template_ids": [template_id],
        },
    )
    assert res.status_code == 200
    body = res.json()
    # 10% quote discount on £1000 ex-VAT -> £900 ex-VAT net
    exp_dep, exp_bal = _expected_deposit_balance(Decimal("900.00"), 10)
    assert Decimal(str(body["deposit_amount"])) == exp_dep
    assert Decimal(str(body["balance_amount"])) == exp_bal


def test_dealer_quote_deposit_15_percent_commission():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        dealer = Dealer(name="Comm Dealer 15")
        session.add(dealer)
        session.commit()
        session.refresh(dealer)

        user = User(
            email="dealer-15@example.com",
            hashed_password="dummy",
            full_name="Dealer 15",
            role=UserRole.DEALER_USER,
            dealer_id=dealer.id,
            dealer_commission_pct=15,
        )
        product = Product(
            name="Shed",
            category=ProductCategory.STABLES,
            base_price=Decimal("500.00"),
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
        product_id = product.id
        user_id = user.id
        dealer_id = user.dealer_id

    dealer_user_ctx = SimpleNamespace(
        id=user_id,
        dealer_id=dealer_id,
        dealer_commission_pct=15,
        role=UserRole.DEALER_USER,
        full_name="Dealer 15",
    )
    app = _make_app(engine, dealer_user_ctx)
    client = TestClient(app)

    res = client.post(
        "/api/dealer-portal/quotes",
        json={
            "customer_name": "Fifteen",
            "product_items": [{"product_id": product_id, "quantity": 1}],
            "discount_template_ids": [],
        },
    )
    assert res.status_code == 200
    body = res.json()
    exp_dep, exp_bal = _expected_deposit_balance(Decimal("500.00"), 15)
    assert Decimal(str(body["deposit_amount"])) == exp_dep
    assert Decimal(str(body["balance_amount"])) == exp_bal
