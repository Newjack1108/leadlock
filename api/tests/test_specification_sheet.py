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
from app.quote_pdf_service import _merge_quote_pdf_parts, generate_quote_pdf
from app.routers import public as public_router
from app.specification_sheet import (
    fetch_specification_sheet_file_bytes,
    has_specification_sheet_content,
    is_specification_sheet_pdf_url,
    resolve_specification_sheet_image_url,
    resolve_specification_sheet_text,
    should_include_specification_sheet,
    should_include_specification_sheet_for_staff_preview,
)

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _minimal_pdf_bytes() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    pdf.drawString(72, 720, "Specification sheet PDF")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


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
    company_image_url: str | None = None,
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
            default_specification_sheet_url=company_image_url,
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


def test_should_include_specification_sheet_for_staff_preview_uses_company_file():
    quote = Quote(include_specification_sheet=False)
    company = CompanySettings(
        default_specification_sheet_url="https://example.com/spec.png",
        updated_by_id=1,
    )
    assert should_include_specification_sheet_for_staff_preview(quote, company) is True
    assert should_include_specification_sheet_for_staff_preview(quote, company, False) is False
    assert should_include_specification_sheet_for_staff_preview(quote, None) is False


def test_resolve_specification_sheet_text_quote_override():
    quote = Quote(specification_sheet="Quote override text")
    company = CompanySettings(default_specification_sheet="Company default", updated_by_id=1)
    assert resolve_specification_sheet_text(quote, company) == "Quote override text"


def test_resolve_specification_sheet_text_falls_back_to_company_default():
    quote = Quote(specification_sheet=None)
    company = CompanySettings(default_specification_sheet="Company default", updated_by_id=1)
    assert resolve_specification_sheet_text(quote, company) == "Company default"


def test_resolve_specification_sheet_image_url_from_company_only():
    company = CompanySettings(
        default_specification_sheet_url="https://example.com/spec.png",
        updated_by_id=1,
    )
    assert resolve_specification_sheet_image_url(company) == "https://example.com/spec.png"
    assert resolve_specification_sheet_image_url(None) == ""


def test_is_specification_sheet_pdf_url():
    assert is_specification_sheet_pdf_url("https://example.com/spec.pdf") is True
    assert is_specification_sheet_pdf_url("https://example.com/spec.pdf?v=1") is True
    assert is_specification_sheet_pdf_url("https://res.cloudinary.com/demo/raw/upload/v1/spec") is True
    assert is_specification_sheet_pdf_url("https://example.com/spec.png") is False


def test_fetch_specification_sheet_file_bytes_ignores_non_pdf_when_url_looks_like_pdf(monkeypatch):
    monkeypatch.setattr(
        "app.specification_sheet._fetch_http_bytes",
        lambda _url: b"<html>not a pdf</html>",
    )
    assert fetch_specification_sheet_file_bytes("https://example.com/spec.pdf") is None


def test_merge_quote_pdf_parts_falls_back_when_spec_sheet_pdf_invalid():
    from app.quote_pdf_service import _merge_quote_pdf_parts

    main = BytesIO(_minimal_pdf_bytes())
    invalid_pdf = BytesIO(b"%PDF-1.4\nthis is not a valid pdf structure")
    merged = _merge_quote_pdf_parts(
        main,
        spec_sheet_pdf_buffer=invalid_pdf,
    )
    reader = PdfReader(merged)
    assert len(reader.pages) >= 1


def test_has_specification_sheet_content_true_when_only_image():
    quote = Quote(specification_sheet=None)
    company = CompanySettings(
        default_specification_sheet=None,
        default_specification_sheet_url="https://example.com/spec.png",
        updated_by_id=1,
    )
    assert has_specification_sheet_content(quote, company) is True


def test_has_specification_sheet_content_false_when_empty():
    quote = Quote(specification_sheet=None)
    company = CompanySettings(
        default_specification_sheet=None,
        default_specification_sheet_url=None,
        updated_by_id=1,
    )
    assert has_specification_sheet_content(quote, company) is False


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


def test_quote_pdf_includes_specification_sheet_image_when_enabled(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default=None,
        company_image_url="https://example.com/spec.png",
        include_on_quote=True,
    )

    def _fake_fetch(_url: str):
        return MINIMAL_PNG

    monkeypatch.setattr(
        "app.specification_sheet.fetch_specification_sheet_file_bytes",
        _fake_fetch,
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        image_url = resolve_specification_sheet_image_url(company_settings)
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=True,
            specification_sheet_text=None,
            specification_sheet_image_url=image_url,
        )

    pdf_text = _pdf_text(pdf_buffer)
    assert "Specification Sheet:" in pdf_text
    reader = PdfReader(pdf_buffer)
    assert len(reader.pages) >= 2


def test_quote_pdf_includes_company_spec_image_on_staff_preview_without_quote_flag(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default=None,
        company_image_url="https://example.com/spec.png",
        include_on_quote=False,
    )

    monkeypatch.setattr(
        "app.specification_sheet.fetch_specification_sheet_file_bytes",
        lambda _url: MINIMAL_PNG,
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        assert should_include_specification_sheet_for_staff_preview(quote, company_settings) is True
        image_url = resolve_specification_sheet_image_url(company_settings)
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=True,
            specification_sheet_text=None,
            specification_sheet_image_url=image_url,
        )

    assert "Specification Sheet:" in _pdf_text(pdf_buffer)


def test_quote_pdf_appends_specification_sheet_pdf_when_enabled(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default=None,
        company_image_url="https://example.com/spec.pdf",
        include_on_quote=True,
    )

    monkeypatch.setattr(
        "app.specification_sheet.fetch_specification_sheet_file_bytes",
        lambda _url: _minimal_pdf_bytes(),
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        file_url = resolve_specification_sheet_image_url(company_settings)
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=True,
            specification_sheet_text=None,
            specification_sheet_image_url=file_url,
        )

    reader = PdfReader(pdf_buffer)
    assert len(reader.pages) >= 2


def test_quote_pdf_survives_invalid_spec_sheet_pdf_bytes(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, quote_id = _seed_quote_with_spec_sheet(
        engine,
        company_default=None,
        company_image_url="https://example.com/spec.pdf",
        include_on_quote=True,
    )

    monkeypatch.setattr(
        "app.specification_sheet.fetch_specification_sheet_file_bytes",
        lambda _url: b"not-a-valid-pdf",
    )

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, quote.customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        company_settings = session.exec(select(CompanySettings).limit(1)).first()
        file_url = resolve_specification_sheet_image_url(company_settings)
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=company_settings,
            session=session,
            include_spec_sheets=False,
            include_specification_sheet=True,
            specification_sheet_text=None,
            specification_sheet_image_url=file_url,
        )

    reader = PdfReader(pdf_buffer)
    assert len(reader.pages) >= 1


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


def test_public_quote_view_returns_spec_sheet_image_when_send_flag_set():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    token, _ = _seed_quote_with_spec_sheet(
        engine,
        company_default=None,
        company_image_url="https://example.com/spec.png",
        include_on_email=True,
    )

    app = _make_public_app(engine)
    client = TestClient(app)
    response = client.get(f"/api/public/quotes/view/{token}")
    assert response.status_code == 200
    data = response.json()
    assert data["show_specification_sheet"] is True
    assert data["specification_sheet"] is None
    assert data["specification_sheet_image_url"] == "https://example.com/spec.png"


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
    assert data["specification_sheet_image_url"] is None
