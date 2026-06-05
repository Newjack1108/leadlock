"""Post-install review request reminders and customer outreach."""
import os
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    CompanySettings,
    Customer,
    Order,
    Quote,
    QuoteItem,
    QuoteStatus,
    Reminder,
    ReminderType,
    User,
    UserRole,
)
from app.reminder_service import generate_reminders
from app.review_request_service import (
    create_review_reminder,
    detect_due_review_requests,
    dismiss_open_review_reminders_for_order,
    generate_review_reminders,
    on_installation_completed,
    on_installation_uncompleted,
    run_review_request_cycle,
    send_review_request_to_customer,
)


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_company(session: Session, *, outreach_enabled: bool = False, delay_days: int = 3) -> CompanySettings:
    user = User(
        email="director@example.com",
        hashed_password="x",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    settings = CompanySettings(
        company_name="Test Co",
        review_request_delay_days=delay_days,
        review_google_url="https://example.com/google",
        review_facebook_url="https://example.com/facebook",
        review_trustpilot_url="https://example.com/trustpilot",
        review_request_customer_outreach_enabled=outreach_enabled,
        updated_by_id=user.id,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def _seed_completed_order(
    session: Session,
    *,
    completed_at: datetime,
    outreach_sent: bool = False,
    suffix: str = "1",
) -> Order:
    user = session.exec(select(User)).first()
    assert user is not None

    customer = Customer(
        customer_number=f"CUST-REV-{suffix}",
        name=f"Review Customer {suffix}",
        email=f"review{suffix}@example.com",
        phone=f"+44770090012{suffix[-1]}",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        quote_number=f"QT-REV-{suffix}",
        customer_id=customer.id,
        status=QuoteStatus.ACCEPTED,
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        currency="GBP",
        created_by_id=user.id,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    session.add(
        QuoteItem(
            quote_id=quote.id,
            description="Stable",
            quantity=1,
            unit_price=1000,
            line_total=1000,
            final_line_total=1000,
        )
    )

    order = Order(
        quote_id=quote.id,
        customer_id=customer.id,
        order_number=f"ORD-REV-{suffix}",
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        currency="GBP",
        created_by_id=user.id,
        installation_completed=True,
        installation_completed_at=completed_at,
        review_request_customer_sent_at=datetime.utcnow() if outreach_sent else None,
        review_request_customer_channel="SMS" if outreach_sent else None,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_installation_completed_sets_timestamp(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow())
        order.installation_completed = False
        order.installation_completed_at = None
        session.add(order)
        session.commit()

        on_installation_completed(order, session)
        session.commit()
        session.refresh(order)

        assert order.installation_completed_at is not None
        assert order.review_request_customer_sent_at is None


def test_installation_uncompleted_dismisses_reminders(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))
        create_review_reminder(order, session)
        session.commit()

        on_installation_uncompleted(order, session)
        session.commit()

        reminder = session.exec(
            select(Reminder).where(Reminder.order_id == order.id)
        ).first()
        assert reminder is not None
        assert reminder.dismissed_at is not None
        assert order.installation_completed_at is None


def test_reminder_created_only_after_delay(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session, delay_days=3)
        recent = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=1))
        due = _seed_completed_order(
            session,
            completed_at=datetime.utcnow() - timedelta(days=4),
            suffix="2",
        )

        due_orders = detect_due_review_requests(session)
        due_ids = {o.id for o in due_orders}
        assert recent.id not in due_ids
        assert due.id in due_ids


def test_no_duplicate_reminders_for_same_order(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))

        assert create_review_reminder(order, session) is not None
        assert create_review_reminder(order, session) is None
        session.commit()

        reminders = session.exec(
            select(Reminder).where(
                Reminder.order_id == order.id,
                Reminder.reminder_type == ReminderType.REQUEST_REVIEW,
            )
        ).all()
        assert len(reminders) == 1


def test_customer_send_skipped_when_outreach_disabled(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session, outreach_enabled=False)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))

        success, error = send_review_request_to_customer(order, session)
        assert success is False
        assert "disabled" in (error or "").lower()


@patch("app.review_request_service.send_sms", return_value=(True, "SM123", None))
def test_customer_send_when_enabled(mock_send_sms, sqlite_engine):
    with Session(sqlite_engine) as session:
        from app.models import SmsTemplate

        settings = _seed_company(session, outreach_enabled=True)
        user = session.exec(select(User)).first()
        assert user is not None

        template = SmsTemplate(
            name="Review SMS",
            body_template="Google: {{ review.google_url }}",
            created_by_id=user.id,
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        settings.review_request_sms_template_id = template.id
        session.add(settings)
        session.commit()

        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))
        success, error = send_review_request_to_customer(order, session)
        assert success is True
        assert error is None
        assert order.review_request_customer_sent_at is not None
        mock_send_sms.assert_called_once()


@patch("app.review_request_service._is_within_outreach_quiet_hours", return_value=True)
def test_customer_send_respects_quiet_hours(mock_quiet, sqlite_engine):
    with Session(sqlite_engine) as session:
        from app.models import SmsTemplate

        settings = _seed_company(session, outreach_enabled=True)
        user = session.exec(select(User)).first()
        assert user is not None
        template = SmsTemplate(
            name="Review SMS Quiet",
            body_template="Thanks {{ customer.name }}",
            created_by_id=user.id,
        )
        session.add(template)
        session.commit()
        session.refresh(template)
        settings.review_request_sms_template_id = template.id
        session.add(settings)
        session.commit()

        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))
        success, error = send_review_request_to_customer(order, session)
        assert success is False
        assert "quiet hours" in (error or "").lower()


def test_generate_reminders_includes_review_requests(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))

        count = generate_reminders(session)
        assert count >= 1

        reminder = session.exec(
            select(Reminder).where(Reminder.order_id == order.id)
        ).first()
        assert reminder is not None
        assert reminder.reminder_type == ReminderType.REQUEST_REVIEW


def test_run_review_request_cycle_is_idempotent(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))

        first = run_review_request_cycle(session)
        second = run_review_request_cycle(session)
        assert first == 1
        assert second == 0

        reminders = session.exec(
            select(Reminder).where(Reminder.order_id == order.id)
        ).all()
        assert len(reminders) == 1


def test_dismiss_open_review_reminders_for_order(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        order = _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))
        create_review_reminder(order, session)
        session.commit()

        n = dismiss_open_review_reminders_for_order(order, session)
        session.commit()
        assert n == 1

        reminder = session.exec(select(Reminder).where(Reminder.order_id == order.id)).first()
        assert reminder.dismissed_at is not None


def test_generate_review_reminders_count(sqlite_engine):
    with Session(sqlite_engine) as session:
        _seed_company(session)
        _seed_completed_order(session, completed_at=datetime.utcnow() - timedelta(days=5))
        count = generate_review_reminders(session)
        assert count == 1
