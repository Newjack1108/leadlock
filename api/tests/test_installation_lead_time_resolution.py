"""Per-type installation lead time resolution for quote PDFs and settings."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.models import (
    CompanySettings,
    InstallationLeadTime,
    Lead,
    LeadType,
    Product,
    ProductCategory,
    Quote,
    QuoteItem,
    User,
    UserRole,
)
from app.quote_pdf_service import (
    _installation_lead_time_for_settings,
    _resolve_quote_brand_lead_type,
)


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        u = User(
            email="t@example.com",
            full_name="T",
            hashed_password="x",
            role=UserRole.DIRECTOR,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        session.add(
            CompanySettings(
                company_name="Co",
                updated_by_id=u.id,
                installation_lead_time=InstallationLeadTime.FIVE_SIX_WEEKS,
                installation_lead_time_stables=InstallationLeadTime.ONE_TWO_WEEKS,
                installation_lead_time_sheds=InstallationLeadTime.TWO_THREE_WEEKS,
                installation_lead_time_cabins=InstallationLeadTime.THREE_FOUR_WEEKS,
            )
        )
        session.commit()
        yield session


def test_installation_lead_time_prefers_per_type_stables():
    cs = MagicMock(spec=CompanySettings)
    cs.installation_lead_time_stables = InstallationLeadTime.TWO_THREE_WEEKS
    cs.installation_lead_time_sheds = None
    cs.installation_lead_time_cabins = None
    cs.installation_lead_time = InstallationLeadTime.FIVE_SIX_WEEKS
    assert (
        _installation_lead_time_for_settings(cs, LeadType.STABLES)
        == InstallationLeadTime.TWO_THREE_WEEKS
    )


def test_installation_lead_time_falls_back_to_legacy_when_per_type_unset():
    cs = MagicMock(spec=CompanySettings)
    cs.installation_lead_time_stables = None
    cs.installation_lead_time_sheds = None
    cs.installation_lead_time_cabins = None
    cs.installation_lead_time = InstallationLeadTime.ONE_TWO_WEEKS
    assert (
        _installation_lead_time_for_settings(cs, LeadType.STABLES)
        == InstallationLeadTime.ONE_TWO_WEEKS
    )


def test_installation_lead_time_none_when_no_settings():
    assert _installation_lead_time_for_settings(None, LeadType.STABLES) is None


def test_resolve_quote_brand_lead_type_from_lead(session: Session):
    u = session.exec(select(User)).first()
    assert u is not None
    lead = Lead(
        name="Test Lead",
        email="a@b.c",
        phone="1",
        lead_type=LeadType.SHEDS,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    quote = Quote(
        lead_id=lead.id,
        quote_number="QT-T-1",
        subtotal=Decimal("0"),
        discount_total=Decimal("0"),
        total_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        balance_amount=Decimal("0"),
        created_by_id=u.id,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)
    assert _resolve_quote_brand_lead_type(quote, [], session) == LeadType.SHEDS


def test_resolve_quote_brand_lead_type_from_product_category(session: Session):
    u = session.exec(select(User)).first()
    assert u is not None
    quote = Quote(
        quote_number="QT-T-2",
        subtotal=Decimal("0"),
        discount_total=Decimal("0"),
        total_amount=Decimal("0"),
        deposit_amount=Decimal("0"),
        balance_amount=Decimal("0"),
        created_by_id=u.id,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)
    p = Product(
        name="Cabin X",
        description="",
        base_price=Decimal("100"),
        category=ProductCategory.CABINS,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    item = QuoteItem(
        quote_id=quote.id,
        description="Line",
        quantity=Decimal("1"),
        unit_price=Decimal("1"),
        line_total=Decimal("1"),
        final_line_total=Decimal("1"),
        product_id=p.id,
    )
    session.add(item)
    session.commit()
    items = list(session.exec(select(QuoteItem).where(QuoteItem.quote_id == quote.id)).all())
    assert _resolve_quote_brand_lead_type(quote, items, session) == LeadType.CABINS


def test_db_company_settings_has_per_type_columns(session: Session):
    cs = session.exec(select(CompanySettings)).first()
    assert cs is not None
    assert cs.installation_lead_time_stables == InstallationLeadTime.ONE_TWO_WEEKS
    assert cs.installation_lead_time_sheds == InstallationLeadTime.TWO_THREE_WEEKS
    assert cs.installation_lead_time_cabins == InstallationLeadTime.THREE_FOUR_WEEKS
