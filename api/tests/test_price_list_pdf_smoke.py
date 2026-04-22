import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth import get_current_user
from app.database import get_session
from app.models import CompanySettings, Product, ProductCategory, User, UserRole
from app.routers import products


def _make_app(engine, user: User):
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(products.router)
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_price_list_pdf_returns_pdf():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="price-list-test@example.com",
            hashed_password="x",
            full_name="Test User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        session.add(
            CompanySettings(
                company_name="Test Co Ltd",
                trading_name="Test Trading",
                updated_by_id=user.id,
            )
        )
        session.add(
            Product(
                name="Alpha Stable",
                category=ProductCategory.STABLES,
                subcategory="Field",
                base_price=Decimal("1234.50"),
                unit="Unit",
                sku="SKU-A",
                size="12x12",
            )
        )
        session.add(
            Product(
                name="Beta Extra",
                category=ProductCategory.STABLES,
                is_extra=True,
                base_price=Decimal("99.00"),
                unit="Per Box",
            )
        )
        session.commit()

    app = _make_app(engine, user)
    client = TestClient(app)

    r = client.get("/api/products/price-list.pdf")
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type") == "application/pdf"
    assert len(r.content) > 500
    assert r.content[:4] == b"%PDF"

    r2 = client.get(
        "/api/products/price-list.pdf",
        params={"category": "STABLES", "is_extra": True},
    )
    assert r2.status_code == 200
    assert r2.headers.get("content-type") == "application/pdf"
    assert len(r2.content) > 500
