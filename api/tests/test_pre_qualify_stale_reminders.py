"""Pre-qualify leads must not generate or keep stale lead reminders."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import (
    PRE_QUALIFY_STALE_RULE_NAMES,
    backfill_default_reminder_rules,
    cleanup_pre_qualify_stale_reminders,
)
from app.models import (
    Customer,
    DeletedReminderRuleName,
    Lead,
    LeadSource,
    LeadStatus,
    LeadType,
    Reminder,
    ReminderPriority,
    ReminderRule,
    ReminderType,
    SuggestedAction,
    User,
    UserRole,
)
from app.reminder_service import detect_stale_leads


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    return engine


def test_detect_stale_leads_skips_pre_qualify_statuses():
    engine = _engine()
    with Session(engine) as session:
        customer = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Pre-qualify Customer",
            email=f"preq-{uuid.uuid4().hex[:8]}@example.com",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        stale_time = datetime.utcnow() - timedelta(days=30)
        for status in (LeadStatus.NEW, LeadStatus.CONTACT_ATTEMPTED, LeadStatus.ENGAGED):
            session.add(
                ReminderRule(
                    rule_name=f"PREQ_{status.value}_{uuid.uuid4().hex[:6]}",
                    entity_type="LEAD",
                    status=status.value,
                    threshold_minutes=60,
                    check_type="STATUS_DURATION",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                )
            )
            session.add(
                Lead(
                    name=f"Lead {status.value}",
                    status=status,
                    customer_id=customer.id,
                    lead_type=LeadType.UNKNOWN,
                    lead_source=LeadSource.MANUAL_ENTRY,
                    updated_at=stale_time,
                )
            )

        session.add(
            ReminderRule(
                rule_name=f"QUAL_{uuid.uuid4().hex[:6]}",
                entity_type="LEAD",
                status="QUALIFIED",
                threshold_minutes=60,
                check_type="STATUS_DURATION",
                is_active=True,
                priority=ReminderPriority.MEDIUM,
                suggested_action=SuggestedAction.CONTACT_CUSTOMER,
            )
        )
        qualified = Lead(
            name="Qualified stale",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.MANUAL_ENTRY,
            updated_at=stale_time,
        )
        session.add(qualified)
        session.commit()
        session.refresh(qualified)

        stale = detect_stale_leads(session)
        lead_ids = {lead.id for lead, _, _ in stale}

    assert lead_ids == {qualified.id}


def test_backfill_default_reminder_rules_omits_pre_qualify_rules():
    engine = _engine()
    with Session(engine) as session:
        backfill_default_reminder_rules(session)
        names = set(session.exec(select(ReminderRule.rule_name)).all())

    for rule_name in PRE_QUALIFY_STALE_RULE_NAMES:
        assert rule_name not in names
    assert "QUALIFIED_STALE" in names


def test_cleanup_pre_qualify_stale_reminders_deletes_rules_and_dismisses():
    engine = _engine()
    with Session(engine) as session:
        user = User(
            email=f"u-{uuid.uuid4().hex}@example.com",
            hashed_password="x",
            full_name="Closer",
            role=UserRole.CLOSER,
        )
        customer = Customer(
            customer_number=f"CUST-{uuid.uuid4().hex[:8]}",
            name="Cleanup Customer",
            email=f"cleanup-{uuid.uuid4().hex[:8]}@example.com",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        for rule_name, status in (
            ("NEW_LEAD_STALE", LeadStatus.NEW),
            ("CONTACT_ATTEMPTED_STALE", LeadStatus.CONTACT_ATTEMPTED),
            ("ENGAGED_STALE", LeadStatus.ENGAGED),
        ):
            session.add(
                ReminderRule(
                    rule_name=rule_name,
                    entity_type="LEAD",
                    status=status.value,
                    threshold_minutes=60,
                    check_type="LAST_ACTIVITY",
                    is_active=True,
                    priority=ReminderPriority.HIGH,
                    suggested_action=SuggestedAction.FOLLOW_UP,
                )
            )

        new_lead = Lead(
            name="Unqualified open",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.MANUAL_ENTRY,
            assigned_to_id=user.id,
        )
        qualified_lead = Lead(
            name="Qualified open",
            status=LeadStatus.QUALIFIED,
            customer_id=customer.id,
            lead_type=LeadType.UNKNOWN,
            lead_source=LeadSource.MANUAL_ENTRY,
            assigned_to_id=user.id,
        )
        session.add(new_lead)
        session.add(qualified_lead)
        session.commit()
        session.refresh(new_lead)
        session.refresh(qualified_lead)

        open_preq = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=new_lead.id,
            customer_id=customer.id,
            assigned_to_id=user.id,
            priority=ReminderPriority.HIGH,
            title="Stale Lead: Unqualified open",
            message="stale",
            suggested_action=SuggestedAction.FOLLOW_UP,
            days_stale=5,
        )
        open_qualified = Reminder(
            reminder_type=ReminderType.LEAD_STALE,
            lead_id=qualified_lead.id,
            customer_id=customer.id,
            assigned_to_id=user.id,
            priority=ReminderPriority.MEDIUM,
            title="Stale Lead: Qualified open",
            message="stale",
            suggested_action=SuggestedAction.CONTACT_CUSTOMER,
            days_stale=8,
        )
        session.add(open_preq)
        session.add(open_qualified)
        session.commit()
        session.refresh(open_preq)
        session.refresh(open_qualified)
        preq_id = open_preq.id
        qualified_id = open_qualified.id

        cleanup_pre_qualify_stale_reminders(session)

        for rule_name in PRE_QUALIFY_STALE_RULE_NAMES:
            assert (
                session.exec(
                    select(ReminderRule).where(ReminderRule.rule_name == rule_name)
                ).first()
                is None
            )
            assert session.get(DeletedReminderRuleName, rule_name) is not None

        dismissed = session.get(Reminder, preq_id)
        kept = session.get(Reminder, qualified_id)
        assert dismissed is not None
        assert dismissed.dismissed_at is not None
        assert kept is not None
        assert kept.dismissed_at is None

        # Cleanup is idempotent and keeps suppression so backfill cannot reseed.
        cleanup_pre_qualify_stale_reminders(session)
        backfill_default_reminder_rules(session)
        for rule_name in PRE_QUALIFY_STALE_RULE_NAMES:
            assert (
                session.exec(
                    select(ReminderRule).where(ReminderRule.rule_name == rule_name)
                ).first()
                is None
            )
