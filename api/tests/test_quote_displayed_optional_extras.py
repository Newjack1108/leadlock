"""Displayed optional extras on quotes (PDF/view only, not line items)."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine, select

from app.available_optional_extras import (
    get_available_optional_extras_for_quote,
    should_show_available_optional_extras_on_quote,
)
from app.models import Product, ProductCategory, Quote, QuoteDisplayedOptionalExtra, QuoteItem, QuoteStatus, User, UserRole
from app.quote_displayed_optional_extras import sync_quote_displayed_optional_extras


def _engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_quote_with_extra(engine):
    with Session(engine) as session:
        user = User(
            email="extras@test.com",
            hashed_password="x",
            full_name="Tester",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        main = Product(
            name="Main Building",
            category=ProductCategory.STABLES,
            base_price=Decimal("1000"),
            is_extra=False,
        )
        extra_a = Product(
            name="Extra A",
            category=ProductCategory.STABLES,
            base_price=Decimal("50"),
            is_extra=True,
        )
        extra_b = Product(
            name="Extra B",
            category=ProductCategory.STABLES,
            base_price=Decimal("75"),
            is_extra=True,
        )
        session.add(main)
        session.add(extra_a)
        session.add(extra_b)
        session.commit()
        session.refresh(main)
        session.refresh(extra_a)
        session.refresh(extra_b)

        quote = Quote(
            quote_number="QT-EXTRAS-1",
            status=QuoteStatus.DRAFT,
            subtotal=Decimal("1000"),
            discount_total=Decimal("0"),
            total_amount=Decimal("1000"),
            deposit_amount=Decimal("0"),
            balance_amount=Decimal("0"),
            created_by_id=user.id,
            include_available_optional_extras=False,
        )
        session.add(quote)
        session.commit()
        session.refresh(quote)

        line = QuoteItem(
            quote_id=quote.id,
            product_id=main.id,
            description=main.name,
            quantity=Decimal("1"),
            unit_price=Decimal("1000"),
            line_total=Decimal("1000"),
            final_line_total=Decimal("1000"),
            sort_order=0,
        )
        session.add(line)
        session.commit()

        sync_quote_displayed_optional_extras(session, quote.id, [extra_a.id, extra_b.id])
        session.commit()

        return quote.id, extra_a.id, extra_b.id


def test_manual_displayed_extras_show_without_auto_linked_flag():
    engine = _engine()
    quote_id, extra_a_id, extra_b_id = _seed_quote_with_extra(engine)

    with Session(engine) as session:
        quote = session.get(Quote, quote_id)
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())

        assert should_show_available_optional_extras_on_quote(quote, quote_id, session) is True

        extras = get_available_optional_extras_for_quote(
            items,
            session,
            quote_id=quote_id,
            include_product_linked=False,
        )
        names = {row["name"] for row in extras}
        assert "Extra A" in names
        assert "Extra B" in names

        # Already on quote as line item should be excluded
        line_extra = QuoteItem(
            quote_id=quote_id,
            product_id=extra_a_id,
            description="Extra A",
            quantity=Decimal("1"),
            unit_price=Decimal("50"),
            line_total=Decimal("50"),
            final_line_total=Decimal("50"),
            sort_order=1,
        )
        session.add(line_extra)
        session.commit()
        items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id)).all())

        extras = get_available_optional_extras_for_quote(
            items,
            session,
            quote_id=quote_id,
            include_product_linked=False,
        )
        names = {row["name"] for row in extras}
        assert "Extra A" not in names
        assert "Extra B" in names
