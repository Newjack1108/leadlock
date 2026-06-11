"""Ensure the canonical sandbox customer exists for staff testing."""
from datetime import datetime

from sqlmodel import Session, or_, select

from app.constants import TEST_CUSTOMER_EMAIL, TEST_CUSTOMER_NAME, TEST_CUSTOMER_NUMBER
from app.models import Customer, Lead, Quote


def _backfill_sandbox_test_records(session: Session, customer: Customer) -> None:
    """Link orphan leads/quotes so sandbox activity is consistently excluded from stats."""
    identity_match = or_(Lead.email == TEST_CUSTOMER_EMAIL)
    if customer.phone:
        identity_match = or_(Lead.email == TEST_CUSTOMER_EMAIL, Lead.phone == customer.phone)

    orphan_leads = session.exec(
        select(Lead).where(Lead.customer_id.is_(None), identity_match)
    ).all()
    for lead in orphan_leads:
        lead.customer_id = customer.id
        lead.updated_at = datetime.utcnow()
        session.add(lead)

    sandbox_lead_ids = select(Lead.id).where(Lead.customer_id == customer.id)
    orphan_quotes = session.exec(
        select(Quote).where(
            Quote.lead_id.in_(sandbox_lead_ids),
            or_(Quote.customer_id.is_(None), Quote.customer_id != customer.id),
        )
    ).all()
    for quote in orphan_quotes:
        quote.customer_id = customer.id
        quote.updated_at = datetime.utcnow()
        session.add(quote)

    if orphan_leads or orphan_quotes:
        session.commit()


def ensure_test_customer(session: Session) -> Customer:
    """Create or update the single sandbox customer excluded from stats and automation."""
    from app.routers.leads import generate_customer_number

    customer = session.exec(
        select(Customer).where(
            or_(
                Customer.email == TEST_CUSTOMER_EMAIL,
                Customer.customer_number == TEST_CUSTOMER_NUMBER,
            )
        )
    ).first()

    if not customer:
        customer = Customer(
            customer_number=generate_customer_number(session),
            name=TEST_CUSTOMER_NAME,
            email=TEST_CUSTOMER_EMAIL,
            source_system="TEST",
            exclude_from_stats=True,
            automated_reminder_outreach_opt_out=True,
            sms_bot_stopped=True,
        )
        session.add(customer)
    else:
        customer.exclude_from_stats = True
        customer.automated_reminder_outreach_opt_out = True
        customer.sms_bot_stopped = True
        if not customer.source_system:
            customer.source_system = "TEST"
        customer.updated_at = datetime.utcnow()
        session.add(customer)

    session.commit()
    session.refresh(customer)
    _backfill_sandbox_test_records(session, customer)
    session.refresh(customer)
    return customer
