"""Quote and order invoice PDFs wrap long line-item descriptions within the description column."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.invoice_pdf_service import generate_deposit_paid_invoice_pdf
from app.models import Customer, Order, OrderItem, Quote, QuoteItem, User, UserRole
from app.quote_pdf_service import generate_quote_pdf

LONG_DESCRIPTION = (
    "Premium heavy-duty timber garden building with reinforced framing, "
    "double-glazed windows, insulated roof panels, and extended weatherproof "
    "cladding suitable for year-round use in exposed locations"
)
UNIT_PRICE = Decimal("1234.56")


def _seed_quote_and_order(engine):
    with Session(engine) as session:
        user = User(
            email="pdf-wrap@example.com",
            hashed_password="dummy",
            full_name="PDF Tester",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="C-PDF-WRAP",
            name="PDF Wrap Customer",
            email="wrap@example.com",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-PDF-WRAP-001",
            subtotal=UNIT_PRICE,
            discount_total=Decimal("0.00"),
            total_amount=UNIT_PRICE,
            deposit_amount=Decimal("0.00"),
            balance_amount=UNIT_PRICE,
            created_by_id=user.id,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        session.add(
            QuoteItem(
                quote_id=quote.id,
                description=LONG_DESCRIPTION,
                quantity=Decimal("1"),
                unit_price=UNIT_PRICE,
                line_total=UNIT_PRICE,
                final_line_total=UNIT_PRICE,
                sort_order=0,
                is_custom=True,
            )
        )

        order = Order(
            quote_id=quote.id,
            customer_id=customer.id,
            order_number="ORD-PDF-WRAP-001",
            subtotal=UNIT_PRICE,
            discount_total=Decimal("0.00"),
            total_amount=UNIT_PRICE,
            deposit_amount=Decimal("0.00"),
            balance_amount=UNIT_PRICE,
            created_by_id=user.id,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        session.add(
            OrderItem(
                order_id=order.id,
                description=LONG_DESCRIPTION,
                quantity=Decimal("1"),
                unit_price=UNIT_PRICE,
                line_total=UNIT_PRICE,
                final_line_total=UNIT_PRICE,
                sort_order=0,
                is_custom=True,
            )
        )
        session.commit()

        return quote.id, order.id, customer.id


def _pdf_text(buffer: BytesIO) -> str:
    reader = PdfReader(buffer)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_quote_pdf_includes_long_description_and_price():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    quote_id, _, customer_id = _seed_quote_and_order(engine)

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        customer = session.get(Customer, customer_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())
        pdf_buffer = generate_quote_pdf(
            quote,
            customer,
            items,
            company_settings=None,
            session=session,
            include_spec_sheets=False,
        )

    text = _pdf_text(pdf_buffer)
    assert LONG_DESCRIPTION[:40] in text
    assert "£1,234.56" in text


def test_order_invoice_pdf_includes_long_description_and_price():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    _, order_id, customer_id = _seed_quote_and_order(engine)

    with Session(engine) as session:
        order = session.get(Order, order_id)
        customer = session.get(Customer, customer_id)
        items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order_id)).all())
        pdf_buffer = generate_deposit_paid_invoice_pdf(
            order,
            customer,
            items,
            company_settings=None,
            session=session,
        )

    text = _pdf_text(pdf_buffer)
    assert LONG_DESCRIPTION[:40] in text
    assert "£1,234.56" in text
