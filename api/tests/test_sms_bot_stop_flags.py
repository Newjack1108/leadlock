import os
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.models import CompanySettings, Customer, SmsDirection, SmsMessage, SmsBotMode, User, UserRole
from app.sms_bot_service import should_bot_reply, backfill_stop_opt_out_customers


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_user_and_settings(session: Session) -> CompanySettings:
    user = User(
        email=f"director-{datetime.utcnow().timestamp()}@example.com",
        hashed_password="dummy",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    settings = CompanySettings(
        company_name="LeadLock",
        updated_by_id=user.id,
        sms_bot_mode=SmsBotMode.ON,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def test_should_bot_reply_stop_sets_both_flags():
    engine = _engine()
    with Session(engine) as session:
        settings = _seed_user_and_settings(session)
        customer = Customer(customer_number="CUST-STOP-001", name="Stop Customer", phone="+447700900111")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        should_reply, reason = should_bot_reply(session, settings, customer, "STOP")

        assert should_reply is False
        assert reason == "opt_out_keyword"
        assert customer.sms_bot_stopped is True
        assert customer.automated_reminder_outreach_opt_out is True


def test_should_bot_reply_non_stop_does_not_force_opt_out():
    engine = _engine()
    with Session(engine) as session:
        settings = _seed_user_and_settings(session)
        customer = Customer(customer_number="CUST-STOP-002", name="Normal Customer", phone="+447700900222")
        session.add(customer)
        session.commit()
        session.refresh(customer)

        should_reply, reason = should_bot_reply(session, settings, customer, "Hello there")

        assert should_reply is True
        assert reason is None
        assert customer.sms_bot_stopped is False
        assert customer.automated_reminder_outreach_opt_out is False


def test_backfill_stop_opt_out_customers_is_idempotent():
    engine = _engine()
    with Session(engine) as session:
        customer_stop = Customer(customer_number="CUST-STOP-003", name="Has Stop", phone="+447700900333")
        customer_normal = Customer(customer_number="CUST-STOP-004", name="No Stop", phone="+447700900444")
        session.add(customer_stop)
        session.add(customer_normal)
        session.commit()
        session.refresh(customer_stop)
        session.refresh(customer_normal)

        session.add(
            SmsMessage(
                customer_id=customer_stop.id,
                direction=SmsDirection.RECEIVED,
                from_phone="+447700900333",
                to_phone="+441234567890",
                body="Please STOP now",
                received_at=datetime.utcnow(),
            )
        )
        session.add(
            SmsMessage(
                customer_id=customer_normal.id,
                direction=SmsDirection.RECEIVED,
                from_phone="+447700900444",
                to_phone="+441234567890",
                body="Just checking in",
                received_at=datetime.utcnow(),
            )
        )
        session.commit()

        updated_first = backfill_stop_opt_out_customers(session)
        updated_second = backfill_stop_opt_out_customers(session)

        stop_customer = session.get(Customer, customer_stop.id)
        normal_customer = session.get(Customer, customer_normal.id)

        assert updated_first == 1
        assert updated_second == 0
        assert stop_customer is not None
        assert stop_customer.sms_bot_stopped is True
        assert stop_customer.automated_reminder_outreach_opt_out is True
        assert normal_customer is not None
        assert normal_customer.sms_bot_stopped is False
        assert normal_customer.automated_reminder_outreach_opt_out is False
