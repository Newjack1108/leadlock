"""Custom quote lines may use negative unit_price for credits that reduce totals."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import Product, ProductCategory, Quote, QuoteStatus, User, UserRole
from app.routers import quotes as quotes_router


def _make_app(engine, user: User) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(quotes_router.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _seed_user(engine) -> User:
    with Session(engine) as session:
        user = User(
            email="negative-custom@example.com",
            hashed_password="dummy",
            full_name="Negative Custom Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _seed_draft_quote(engine, user: User, quote_number: str) -> int:
    with Session(engine) as session:
        quote = Quote(
            quote_number=quote_number,
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)
        return quote.id


def test_custom_credit_line_reduces_subtotal():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    quote_id = _seed_draft_quote(engine, user, "QT-NEG-CUSTOM-001")
    client = TestClient(_make_app(engine, user))

    response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "description": "Main building",
                    "quantity": 1,
                    "unit_price": 500,
                    "is_custom": True,
                    "sort_order": 0,
                },
                {
                    "description": "Trade-in credit",
                    "quantity": 1,
                    "unit_price": -100,
                    "is_custom": True,
                    "sort_order": 1,
                },
            ],
        },
    )
    assert response.status_code == 200
    quote = response.json()
    assert Decimal(str(quote["subtotal"])) == Decimal("400.00")
    assert Decimal(str(quote["total_amount"])) == Decimal("400.00")
    credit = next(i for i in quote["items"] if i["description"] == "Trade-in credit")
    assert Decimal(str(credit["unit_price"])) == Decimal("-100.00")
    assert Decimal(str(credit["line_total"])) == Decimal("-100.00")


def test_catalog_line_rejects_negative_unit_price():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        product = Product(
            name="Standard Shed",
            category=ProductCategory.SHEDS,
            base_price=Decimal("3000.00"),
        )
        session.add(product)
        session.commit()
        session.refresh(product)
        product_id = product.id

    quote_id = _seed_draft_quote(engine, user, "QT-NEG-CATALOG-001")
    client = TestClient(_make_app(engine, user))

    response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "product_id": product_id,
                    "description": product.name,
                    "quantity": 1,
                    "unit_price": -50,
                    "is_custom": False,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert response.status_code == 422


def test_credits_exceeding_charges_yield_negative_total():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    quote_id = _seed_draft_quote(engine, user, "QT-NEG-TOTAL-001")
    client = TestClient(_make_app(engine, user))

    response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "description": "Small item",
                    "quantity": 1,
                    "unit_price": 200,
                    "is_custom": True,
                    "sort_order": 0,
                },
                {
                    "description": "Large credit",
                    "quantity": 1,
                    "unit_price": -500,
                    "is_custom": True,
                    "sort_order": 1,
                },
            ],
        },
    )
    assert response.status_code == 200
    quote = response.json()
    assert Decimal(str(quote["subtotal"])) == Decimal("-300.00")
    assert Decimal(str(quote["total_amount"])) == Decimal("-300.00")
