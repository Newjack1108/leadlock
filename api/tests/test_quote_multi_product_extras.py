"""Multi-product quote optional extras parent linking on draft save."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth import get_current_user
from app.database import get_session
from app.models import Product, ProductCategory, Quote, QuoteItem, QuoteStatus, User, UserRole
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
            email="multi-extras@example.com",
            hashed_password="dummy",
            full_name="Multi Extras Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _seed_products(engine):
    with Session(engine) as session:
        product_a = Product(
            name="Building A",
            category=ProductCategory.STABLES,
            base_price=Decimal("1000"),
            is_extra=False,
        )
        product_b = Product(
            name="Building B",
            category=ProductCategory.STABLES,
            base_price=Decimal("2000"),
            is_extra=False,
        )
        extra_a = Product(
            name="Extra for A",
            category=ProductCategory.STABLES,
            base_price=Decimal("100"),
            is_extra=True,
        )
        extra_b = Product(
            name="Extra for B",
            category=ProductCategory.STABLES,
            base_price=Decimal("150"),
            is_extra=True,
        )
        session.add(product_a)
        session.add(product_b)
        session.add(extra_a)
        session.add(extra_b)
        session.commit()
        session.refresh(product_a)
        session.refresh(product_b)
        session.refresh(extra_a)
        session.refresh(extra_b)
        return product_a, product_b, extra_a, extra_b


def _seed_draft_quote(engine, user: User) -> int:
    with Session(engine) as session:
        quote = Quote(
            quote_number="QT-MULTI-EXTRAS-001",
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


def test_multi_product_extras_link_to_correct_main_products():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    user = _seed_user(engine)
    product_a, product_b, extra_a, extra_b = _seed_products(engine)
    quote_id = _seed_draft_quote(engine, user)
    client = TestClient(_make_app(engine, user))

    response = client.put(
        f"/api/quotes/{quote_id}/draft",
        json={
            "items": [
                {
                    "product_id": product_a.id,
                    "description": product_a.name,
                    "quantity": 1,
                    "unit_price": 1000,
                    "is_custom": False,
                    "sort_order": 0,
                },
                {
                    "product_id": extra_a.id,
                    "description": extra_a.name,
                    "quantity": 1,
                    "unit_price": 100,
                    "is_custom": False,
                    "sort_order": 1,
                    "parent_index": 0,
                },
                {
                    "product_id": product_b.id,
                    "description": product_b.name,
                    "quantity": 1,
                    "unit_price": 2000,
                    "is_custom": False,
                    "sort_order": 2,
                },
                {
                    "product_id": extra_b.id,
                    "description": extra_b.name,
                    "quantity": 1,
                    "unit_price": 150,
                    "is_custom": False,
                    "sort_order": 3,
                    "parent_index": 2,
                },
            ],
        },
    )
    assert response.status_code == 200

    with Session(engine) as session:
        items = list(
            session.exec(
                select(QuoteItem)
                .where(QuoteItem.quote_id == quote_id)
                .order_by(QuoteItem.sort_order)
            ).all()
        )
        by_description = {i.description: i for i in items}
        line_a = by_description[product_a.name]
        line_b = by_description[product_b.name]
        line_extra_a = by_description[extra_a.name]
        line_extra_b = by_description[extra_b.name]

        assert line_extra_a.parent_quote_item_id == line_a.id
        assert line_extra_b.parent_quote_item_id == line_b.id
        assert line_extra_b.parent_quote_item_id != line_extra_a.id
