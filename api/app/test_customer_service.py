"""Ensure the canonical sandbox customer exists for staff testing."""
from datetime import datetime

from sqlmodel import Session, or_, select

from app.constants import TEST_CUSTOMER_EMAIL, TEST_CUSTOMER_NAME, TEST_CUSTOMER_NUMBER
from app.models import Customer


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
    return customer
