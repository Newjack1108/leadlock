"""Custom quote lines can store per-unit installation hours for delivery/install estimates."""
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
            email="custom-install@example.com",
            hashed_password="dummy",
            full_name="Install Hours Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_draft_custom_line_persists_installation_hours():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)

    with Session(engine) as session:
        quote = Quote(
            quote_number="QT-CUSTOM-INST-001",
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
        quote_id = quote.id

    client = TestClient(_make_app(engine, user))

    draft_response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "description": "Bespoke stable block",
                    "quantity": 2,
                    "unit_price": 5000,
                    "is_custom": True,
                    "installation_hours": 4,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert len(draft["items"]) == 1
    assert draft["items"][0]["is_custom"] is True
    assert Decimal(str(draft["items"][0]["installation_hours"])) == Decimal("4")

    get_response = client.get(f"/api/quotes/{quote_id}")
    assert get_response.status_code == 200
    loaded = get_response.json()
    assert len(loaded["items"]) == 1
    assert Decimal(str(loaded["items"][0]["installation_hours"])) == Decimal("4")


def test_catalog_line_ignores_installation_hours_in_payload():
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
            installation_hours=Decimal("6.00"),
        )
        quote = Quote(
            quote_number="QT-CATALOG-INST-001",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            created_by_id=user.id,
        )
        session.add(product)
        session.add(quote)
        session.commit()
        session.refresh(product)
        session.refresh(quote)
        quote_id = quote.id
        product_id = product.id

    client = TestClient(_make_app(engine, user))

    draft_response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "product_id": product_id,
                    "description": product.name,
                    "quantity": 1,
                    "unit_price": 3000,
                    "is_custom": False,
                    "installation_hours": 99,
                    "sort_order": 0,
                }
            ],
        },
    )
    assert draft_response.status_code == 200
    item = draft_response.json()["items"][0]
    assert item["installation_hours"] is None
