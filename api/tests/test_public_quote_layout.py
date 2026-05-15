"""Public quote view and PDF include saved configurator layout."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.configurator_layout_public import build_layout_for_public_view, layout_to_svg
from app.database import get_session
from app.models import (
    Customer,
    Product,
    ProductCategory,
    Quote,
    QuoteConfiguration,
    QuoteEmail,
    QuoteStatus,
    User,
    UserRole,
)
from app.routers import public as public_router
from app.schemas import QuoteConfigurationPayload


def _make_public_app(engine) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(public_router.router)
    app.dependency_overrides[get_session] = get_session_override
    return app


def _seed_layout_quote(engine):
    with Session(engine) as session:
        user = User(
            email="layout-public@example.com",
            hashed_password="dummy",
            full_name="Layout Tester",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(customer_number="C-LAYOUT-001", name="Layout Customer", email="customer@example.com")
        product = Product(
            name="3m Standard Box",
            category=ProductCategory.CONFIGURATOR,
            base_price=Decimal("2500.00"),
            configurator_width=Decimal("3.00"),
            configurator_length=Decimal("4.00"),
            configurator_front_face="bottom",
        )
        quote = Quote(
            quote_number="QT-LAYOUT-001",
            status=QuoteStatus.SENT,
            customer_id=None,
            subtotal=Decimal("2500.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("2500.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("2500.00"),
            created_by_id=1,
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        quote.customer_id = customer.id
        quote.created_by_id = user.id
        session.add(product)
        session.add(quote)
        session.commit()
        session.refresh(product)
        session.refresh(quote)

        config_payload = QuoteConfigurationPayload(
            schema_version=1,
            name="Customer yard plan",
            boxes=[
                {
                    "id": "box-1",
                    "product_id": product.id,
                    "x": Decimal("0"),
                    "y": Decimal("0"),
                    "rotation": 0,
                }
            ],
            extras=[],
        )
        session.add(
            QuoteConfiguration(
                quote_id=quote.id,
                configuration_json=config_payload.model_dump(mode="json"),
                created_by_id=user.id,
            )
        )
        session.add(
            QuoteEmail(
                quote_id=quote.id,
                to_email=customer.email,
                subject="Your quote",
                body_html="<p>Quote</p>",
                tracking_id="track-layout-001",
                view_token="publiclayouttoken123",
            )
        )
        session.commit()
        return quote.id, product.id, "publiclayouttoken123"


def test_build_layout_for_public_view_resolves_footprint():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    quote_id, product_id, _ = _seed_layout_quote(engine)

    with Session(engine) as session:
        layout = build_layout_for_public_view(session, quote_id)

    assert layout is not None
    assert layout.name == "Customer yard plan"
    assert len(layout.boxes) == 1
    box = layout.boxes[0]
    assert box.id == "box-1"
    assert box.label == "3m Standard Box"
    assert Decimal(str(box.width)) == Decimal("3.00")
    assert Decimal(str(box.length)) == Decimal("4.00")
    assert box.front_face == "bottom"
    assert box.is_corner_box is False

    svg = layout_to_svg(layout)
    assert b"3m Standard Box" in svg
    assert b"<svg" in svg

    del product_id


def test_public_quote_view_includes_layout():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, _, token = _seed_layout_quote(engine)
    client = TestClient(_make_public_app(engine))

    response = client.get(f"/api/public/quotes/view/{token}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["layout"] is not None
    assert len(payload["layout"]["boxes"]) == 1
    assert payload["layout"]["name"] == "Customer yard plan"


def test_public_quote_view_omits_layout_when_not_configured():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="nolayout@example.com",
            hashed_password="dummy",
            full_name="No Layout",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="C-NO-LAYOUT",
            name="No Layout Customer",
            email="customer-nolayout@example.com",
        )
        quote = Quote(
            quote_number="QT-NO-LAYOUT",
            status=QuoteStatus.SENT,
            subtotal=Decimal("0.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("0.00"),
            created_by_id=1,
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)
        quote.customer_id = customer.id
        quote.created_by_id = user.id
        session.add(quote)
        session.commit()
        session.refresh(quote)
        session.add(
            QuoteEmail(
                quote_id=quote.id,
                to_email=customer.email or "customer-nolayout@example.com",
                subject="Quote",
                body_html="<p>Quote</p>",
                tracking_id="track-no-layout-001",
                view_token="nolayouttoken999",
            )
        )
        session.commit()

    client = TestClient(_make_public_app(engine))
    response = client.get("/api/public/quotes/view/nolayouttoken999")
    assert response.status_code == 200
    assert response.json().get("layout") is None


def test_public_quote_pdf_includes_layout_page():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    quote_id, _, token = _seed_layout_quote(engine)

    with Session(engine) as session:
        from app.models import QuoteItem

        quote = session.get(Quote, quote_id)
        product = session.exec(select(Product)).first()
        session.add(
            QuoteItem(
                quote_id=quote_id,
                description=product.name,
                quantity=Decimal("1"),
                unit_price=Decimal("2500.00"),
                line_total=Decimal("2500.00"),
                final_line_total=Decimal("2500.00"),
                sort_order=0,
                product_id=product.id,
            )
        )
        session.commit()

    client = TestClient(_make_public_app(engine))
    response = client.get(f"/api/public/quotes/view/{token}/pdf")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/pdf")

    reader = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Stable layout plan" in text
    assert "3m Standard Box" in text
