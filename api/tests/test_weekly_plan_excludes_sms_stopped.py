from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Customer,
    Lead,
    LeadStatus,
    ReminderPriority,
    ReminderRule,
    SuggestedAction,
    User,
    UserRole,
    WeeklyPlanItem,
)
from app.weekly_planner_service import generate_weekly_plan


def test_generate_weekly_plan_skips_sms_stopped_customers():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="weekly-plan-sms-stop@example.com",
            hashed_password="x",
            full_name="Weekly Planner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        stopped_customer = Customer(
            customer_number="CUST-SMS-STOP-001",
            name="Stopped Customer",
            email="stopped@example.com",
            phone="+447700900001",
            sms_bot_stopped=True,
        )
        open_customer = Customer(
            customer_number="CUST-SMS-OPEN-001",
            name="Open Customer",
            email="open-sms@example.com",
            phone="+447700900002",
            sms_bot_stopped=False,
        )
        session.add(stopped_customer)
        session.add(open_customer)
        session.commit()
        session.refresh(stopped_customer)
        session.refresh(open_customer)

        stopped_lead = Lead(
            name="Stopped Lead",
            status=LeadStatus.QUALIFIED,
            customer_id=stopped_customer.id,
            assigned_to_id=user.id,
        )
        open_lead = Lead(
            name="Open Lead",
            status=LeadStatus.QUALIFIED,
            customer_id=open_customer.id,
            assigned_to_id=user.id,
        )
        session.add(stopped_lead)
        session.add(open_lead)

        rule = ReminderRule(
            rule_name="TEST_WEEKLY_PLAN_SMS_STOP",
            entity_type="LEAD",
            status=LeadStatus.QUALIFIED.value,
            threshold_minutes=0,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.URGENT,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()
        session.refresh(stopped_lead)
        session.refresh(open_lead)

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)

        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()
        customer_ids = {item.customer_id for item in items}
        lead_ids = {item.lead_id for item in items}

        assert stopped_customer.id not in customer_ids
        assert stopped_lead.id not in lead_ids
        assert open_customer.id in customer_ids
        assert open_lead.id in lead_ids
