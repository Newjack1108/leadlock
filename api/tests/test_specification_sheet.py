"""Standard specification sheet resolution, PDF inclusion, and public view."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.models import (
    CompanySettings,
    Customer,
    Quote,
    QuoteEmail,
    QuoteItem,
    QuoteStatus,
    User,
    UserRole,
)
from app.quote_pdf_service import generate_quote_pdf
from app.routers import public as public_router
from app.specification_sheet import (
    resolve_specification_sheet_text,
    should_include_specification_sheet,
)


def _pdf_text(buffer: BytesIO) -> str:
    reader = PdfReader(buffer)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _make_public_app(engine) -> FastAPI:
    def get_session_override():
        with Session(engine) as session:
            yield session

    app = FastAPI()
    app.include_router(public_router.router)
    app.dependency_overrides[get_session] = get_session_override
    return app


def _seed_quote_with_spec_sheet(
    engine,
    *,
    quote_sheet: str | None = None,
    company_default: str | None = "Company default spec content",
    include_on_quote: bool = False,
    include_on_email: bool = False,
) -> tuple[str, int]:
    with Session(engine) as session:
        user = User(
            email="spec-sheet@example.com",
            hashed_password="dummy",
            full_name="Spec Tester",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="C-SPEC-001",
            name="Spec Customer",
            email="spec@example.com",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        settings = CompanySettings(
            company_name="Spec Test Co",
            default_specification_sheet=company_default,
            updated_by_id=user.id,
        )
        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-SPEC-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            deposit_amount=Decimal("0.00"),
            balance_amount=Decimal("1000.00"),
            created_by_id=user.id,
            specification_sheet=quote_sheet,
            include_specification_sheet=include_on_quote,
        )
        session.add(settings)
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteItem(
                quote_id=quote.id,
                description="Test building",
                quantity=Decimal("1"),
                unit_price=Decimal("1000.00"),
                line_total=Decimal("1000.00"),
                final_line_total=Decimal("1000.00"),
                sort_order=0,
                is_custom=True,
            )
        )
        session.add(
            QuoteEmail(
                quote_id=quote.id,
                to_email=customer.email,
                subject="Your quote",
                body_html="<p>Quote</p>",
                tracking_id="track-spec-001",
                view_token="publicspectoken123",
                include_specification_sheet=include_on_email,
            )
        )
        session.commit()
        return "publicspectoken123", quote.id


def test_should_include_specification_sheet_prefers_quote_email_flag():
    quote = Quote(include_specification_sheet=False)
    quote_email = QuoteEmail(include_specification_sheet=True)
    assert should_include_specification_sheet(quote, quote_email) is True


def test_should_include_specification_sheet_uses_quote_flag():
    quote = Quote(include_specification_sheet=True)
    assert should_include_specification_sheet(quote) is True
    assert should_include_specification_sheet(quote, QuoteEmail(include_specification_sheet=False)) is True
    assert should_include_specification_sheet(Quote(include_specification_sheet=False)) is False


def test_resolve_specification_sheet_text_quote_override():
    quote = Quote(specification_sheet="Quote override text")
    company = CompanySettings(default_specification_sheet="Company default", updated_by_id=1)
    assert resolve_specification_sheet_text(quote, company) == "Quote override text"


def test_resolve_specification_sheet_text_falls_back_to_company_default():
    quote = Quote(specification_sheet=None)
    company = CompanySettings(default_specification_sheet="Company default", updated_by_id=1)
    assert resolve_specification_sheet_text(quote, company) == "Company default"


def test_quote_pdf_includes_specification_sheet_when_enabled():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default="Panel thickness: 18mm\nRoof: EPDM membrane",
        include_on_quote=True,
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        text = resolve_specification_sheet_text(quote, company_settings)
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=True,
            specification_sheet_text=text,
        )

    pdf_text = _pdf_text(pdf_buffer)
    assert "Specification Sheet:" in pdf_text
    assert "Panel thickness: 18mm" in pdf_text


def test_quote_pdf_excludes_specification_sheet_when_disabled():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default="Hidden spec content",
        include_on_quote=False,
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=False,
            specification_sheet_text=None,
        )

    pdf_text = _pdf_text(pdf_buffer)
    assert "Hidden spec content" not in pdf_text


def test_public_quote_view_returns_spec_sheet_when_send_flag_set():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    token, _ = _seed_quote_with_spec_sheet(
        engine,
        company_default="Public view spec text",
        include_on_email=True,
    )

    app = _make_public_app(engine)
    client = TestClient(app)
    response = client.get(f"/api/public/quotes/view/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["show_specification_sheet"] is True
    assert data["specification_sheet"] == "Public view spec text"


def test_public_quote_view_hides_spec_sheet_when_not_included():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    token, _ = _seed_quote_with_spec_sheet(
        engine,
        company_default="Should not appear",
        include_on_quote=False,
        include_on_email=False,
    )

    app = _make_public_app(engine)
    client = TestClient(app)
    response = client.get(f"/api/public/quotes/view/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["show_specification_sheet"] is False
    assert data["specification_sheet"] is None
