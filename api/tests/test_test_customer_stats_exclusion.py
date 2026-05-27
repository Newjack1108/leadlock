"""Sandbox customer is excluded from stats aggregates and automated outreach."""
import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.constants import TEST_CUSTOMER_EMAIL, TEST_CUSTOMER_NAME
from app.customer_outreach_service import try_customer_outreach_for_new_lead
from app.models import (
    Customer,
    CustomerOutreachChannel,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    Quote,
    QuoteStatus,
    ReminderPriority,
    ReminderRule,
    SmsTemplate,
    SuggestedAction,
    User,
    UserRole,
)
from app.reminder_service import detect_stale_leads
from app.routers.dashboard import get_dashboard_stats
from app.test_customer_service import ensure_test_customer


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    return engine


def test_ensure_test_customer_is_idempotent():
    engine = _engine()
    with Session(engine) as session:
        first = ensure_test_customer(session)
        second = ensure_test_customer(session)
        assert first.id == second.id
        assert first.email == TEST_CUSTOMER_EMAIL
        assert first.name == TEST_CUSTOMER_NAME
        assert first.exclude_from_stats is True
        assert first.automated_reminder_outreach_opt_out is True
        assert first.sms_bot_stopped is True
        assert first.source_system == "TEST"

        rows = session.exec(select(Customer).where(Customer.email == TEST_CUSTOMER_EMAIL)).all()
        assert len(rows) == 1


def test_dashboard_stats_excludes_test_customer_leads_and_quotes():
    engine = _engine()
    with Session(engine) as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Stats User",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        test_customer = ensure_test_customer(session)
        normal = Customer(
            customer_number="CUST-NORMAL-001",
            name="Normal Customer",
            email="normal@example.com",
        )
        session.add(normal)
        session.commit()
        session.refresh(normal)

        session.add(
            Lead(
                name="Test lead",
                status=LeadStatus.NEW,
                customer_id=test_customer.id,
                lead_type=LeadType.UNKNOWN,
                lead_source=LeadSource.MANUAL_ENTRY,
            )
        )
        session.add(
            Lead(
                name="Real lead",
                status=LeadStatus.NEW,
                customer_id=normal.id,
                lead_type=LeadType.UNKNOWN,
                lead_source=LeadSource.MANUAL_ENTRY,
            )
        )
        amount_test = Decimal("1000")
        amount_real = Decimal("2000")
        session.add(
            Quote(
                customer_id=test_customer.id,
                quote_number="Q-TEST-001",
                status=QuoteStatus.SENT,
                sent_at=datetime.utcnow(),
                subtotal=amount_test,
                total_amount=amount_test,
                created_by_id=user.id,
                version=1,
            )
        )
        session.add(
            Quote(
                customer_id=normal.id,
                quote_number="Q-REAL-001",
                status=QuoteStatus.SENT,
                sent_at=datetime.utcnow(),
                subtotal=amount_real,
                total_amount=amount_real,
                created_by_id=user.id,
                version=1,
            )
        )
        session.commit()

        stats = asyncio.run(
            get_dashboard_stats(
                session=session,
                current_user=object(),
                period=None,
                start_date=None,
                end_date=None,
            )
        )

    assert stats.total_leads == 1
    assert stats.new_count == 1
    assert stats.quotes_sent_count == 1


def test_detect_stale_leads_skips_test_customer():
    engine = _engine()
    with Session(engine) as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        test_customer = ensure_test_customer(session)
        normal = Customer(
            customer_number="CUST-NORMAL-002",
            name="Normal Customer 2",
            email="normal2@example.com",
        )
        session.add(normal)
        session.commit()
        session.refresh(normal)

        stale_time = datetime.utcnow() - timedelta(days=30)
        session.add(
            ReminderRule(
                rule_name=f"TEST_STALE_{uuid.uuid4().hex[:8]}",
                entity_type="LEAD",
                status="NEW",
                threshold_minutes=60,
                check_type="STATUS_DURATION",
                is_active=True,
                priority=ReminderPriority.HIGH,
                suggested_action=SuggestedAction.FOLLOW_UP,
            )
        )
        session.add(
            Lead(
                name="Test stale",
                status=LeadStatus.NEW,
                customer_id=test_customer.id,
                lead_type=LeadType.UNKNOWN,
                lead_source=LeadSource.MANUAL_ENTRY,
                updated_at=stale_time,
            )
        )
        session.add(
            Lead(
                name="Real stale",
                status=LeadStatus.NEW,
                customer_id=normal.id,
                lead_type=LeadType.UNKNOWN,
                lead_source=LeadSource.MANUAL_ENTRY,
                updated_at=stale_time,
            )
        )
        session.commit()

        stale = detect_stale_leads(session)
        lead_ids = {lead.id for lead, _, _ in stale}

    assert len(lead_ids) == 1
    with Session(engine) as session:
        real = session.exec(select(Lead).where(Lead.name == "Real stale")).first()
        assert real is not None
        assert real.id in lead_ids


def test_try_customer_outreach_for_new_lead_skips_test_customer(monkeypatch):
    engine = _engine()
    calls = {"n": 0}

    def fake_deliver(session, *, company, lead, rule):
        calls["n"] += 1
        return True

    monkeypatch.setattr(
        "app.customer_outreach_service._deliver_lead_customer_outreach_once",
        fake_deliver,
    )

    with Session(engine) as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Owner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        tmpl = SmsTemplate(
            name="Welcome",
            body_template="Hi",
            created_by_id=user.id,
        )
        session.add(tmpl)
        session.commit()
        session.refresh(tmpl)

        test_customer = ensure_test_customer(session)
        session.add(
            ReminderRule(
                rule_name=f"ON_CREATE_{uuid.uuid4().hex[:8]}",
                entity_type="LEAD",
                status="NEW",
                threshold_minutes=60,
                check_type="LAST_ACTIVITY",
                is_active=True,
                priority=ReminderPriority.HIGH,
                suggested_action=SuggestedAction.FOLLOW_UP,
                customer_outreach_on_lead_create=True,
                customer_outreach_channel=CustomerOutreachChannel.SMS.value,
                customer_outreach_sms_template_id=tmpl.id,
            )
        )
        session.commit()

        test_lead = Lead(
            name="Test outreach",
            status=LeadStatus.NEW,
            customer_id=test_customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.MANUAL_ENTRY,
        )
        session.add(test_lead)
        session.commit()
        session.refresh(test_lead)

        sent = try_customer_outreach_for_new_lead(session, test_lead)

    assert sent == 0
    assert calls["n"] == 0
