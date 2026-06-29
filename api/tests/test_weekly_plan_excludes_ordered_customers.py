from datetime import datetime
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Customer,
    Lead,
    LeadStatus,
    Order,
    Quote,
    QuoteStatus,
    ReminderPriority,
    ReminderRule,
    SuggestedAction,
    User,
    UserRole,
    WeeklyPlanItem,
)
from app.weekly_planner_service import generate_weekly_plan


def test_generate_weekly_plan_skips_customers_with_orders():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="weekly-plan-orders@example.com",
            hashed_password="x",
            full_name="Weekly Planner",
            role=UserRole.DIRECTOR,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        ordered_customer = Customer(
            customer_number="CUST-ORDERED-001",
            name="Ordered Customer",
            email="ordered@example.com",
        )
        open_customer = Customer(
            customer_number="CUST-OPEN-001",
            name="Open Customer",
            email="open@example.com",
        )
        session.add(ordered_customer)
        session.add(open_customer)
        session.commit()
        session.refresh(ordered_customer)
        session.refresh(open_customer)

        ordered_lead = Lead(
            name="Ordered Lead",
            status=LeadStatus.NEW,
            customer_id=ordered_customer.id,
            assigned_to_id=user.id,
        )
        open_lead = Lead(
            name="Open Lead",
            status=LeadStatus.NEW,
            customer_id=open_customer.id,
            assigned_to_id=user.id,
        )
        session.add(ordered_lead)
        session.add(open_lead)
        session.commit()
        session.refresh(ordered_lead)
        session.refresh(open_lead)

        accepted_quote = Quote(
            customer_id=ordered_customer.id,
            lead_id=ordered_lead.id,
            quote_number="QT-ORDERED-001",
            status=QuoteStatus.ACCEPTED,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            created_by_id=user.id,
            accepted_at=datetime.utcnow(),
        )
        session.add(accepted_quote)
        session.commit()
        session.refresh(accepted_quote)

        order = Order(
            quote_id=accepted_quote.id,
            customer_id=ordered_customer.id,
            order_number="ORD-2026-001",
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            deposit_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
            created_by_id=user.id,
        )
        session.add(order)

        rule = ReminderRule(
            rule_name="TEST_WEEKLY_PLAN_NEW_LEADS",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=0,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.URGENT,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
        session.add(rule)
        session.commit()

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)

        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()
        customer_ids = {item.customer_id for item in items}
        lead_ids = {item.lead_id for item in items}

        assert ordered_customer.id not in customer_ids
        assert ordered_lead.id not in lead_ids
        assert open_customer.id in customer_ids
        assert open_lead.id in lead_ids
