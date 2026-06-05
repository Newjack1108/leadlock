from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Customer,
    Lead,
    LeadStatus,
    Quote,
    QuoteStatus,
    ReminderPriority,
    ReminderRule,
    SuggestedAction,
    User,
    UserRole,
    WeeklyPlanItem,
    WeeklyPlanItemStatus,
    WeeklyPlanRun,
    WeeklyPlanScope,
)
from app.weekly_planner_service import _week_start_utc, generate_weekly_plan


def _seed_lead_plan_fixture(session: Session) -> tuple[User, Customer, Lead]:
    user = User(
        email="weekly-plan-regen@example.com",
        hashed_password="x",
        full_name="Weekly Planner",
        role=UserRole.DIRECTOR,
    )
    customer = Customer(
        customer_number="CUST-REGEN-001",
        name="Regen Customer",
        email="regen@example.com",
        phone="07111222333",
    )
    session.add(user)
    session.add(customer)
    session.commit()
    session.refresh(user)
    session.refresh(customer)

    lead = Lead(
        name="Regen Lead",
        status=LeadStatus.NEW,
        customer_id=customer.id,
        assigned_to_id=user.id,
    )
    session.add(lead)
    session.add(
        ReminderRule(
            rule_name="TEST_WP_REGEN_LEADS",
            entity_type="LEAD",
            status=LeadStatus.NEW.value,
            threshold_minutes=0,
            check_type="LAST_ACTIVITY",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.FOLLOW_UP,
        )
    )
    session.commit()
    session.refresh(lead)
    return user, customer, lead


def test_regenerate_same_week_excludes_completed_lead():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user, customer, lead = _seed_lead_plan_fixture(session)

        run1 = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        item = session.exec(
            select(WeeklyPlanItem).where(
                WeeklyPlanItem.plan_run_id == run1.id,
                WeeklyPlanItem.lead_id == lead.id,
            )
        ).first()
        assert item is not None
        item.status = WeeklyPlanItemStatus.COMPLETED
        session.add(item)
        session.commit()

        run2 = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items2 = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run2.id)).all()

        assert lead.id not in {it.lead_id for it in items2}
        assert customer.id not in {it.customer_id for it in items2}


def test_regenerate_same_week_excludes_rejected_quote():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(
            email="weekly-plan-regen-quote@example.com",
            hashed_password="x",
            full_name="Weekly Planner",
            role=UserRole.DIRECTOR,
        )
        customer = Customer(
            customer_number="CUST-REGEN-QUOTE-001",
            name="Quote Regen Customer",
            email="quote-regen@example.com",
            phone="07999888777",
        )
        session.add(user)
        session.add(customer)
        session.commit()
        session.refresh(user)
        session.refresh(customer)

        quote = Quote(
            customer_id=customer.id,
            quote_number="QT-REGEN-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("1200.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1200.00"),
            created_by_id=user.id,
            sent_at=datetime.utcnow() - timedelta(days=5),
        )
        session.add(quote)
        session.add(
            ReminderRule(
                rule_name="TEST_WP_REGEN_QUOTES",
                entity_type="QUOTE",
                status=QuoteStatus.SENT.value,
                threshold_minutes=0,
                check_type="SENT_DATE",
                is_active=True,
                priority=ReminderPriority.MEDIUM,
                suggested_action=SuggestedAction.RESEND_QUOTE,
            )
        )
        session.commit()
        session.refresh(quote)

        run1 = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        item = session.exec(
            select(WeeklyPlanItem).where(
                WeeklyPlanItem.plan_run_id == run1.id,
                WeeklyPlanItem.quote_id == quote.id,
            )
        ).first()
        assert item is not None
        item.status = WeeklyPlanItemStatus.REJECTED
        session.add(item)
        session.commit()

        run2 = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items2 = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run2.id)).all()

        assert quote.id not in {it.quote_id for it in items2}
        assert customer.id not in {it.customer_id for it in items2}


def test_completed_item_from_prior_week_can_reappear():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user, customer, lead = _seed_lead_plan_fixture(session)
        current_week = _week_start_utc()
        prior_week = current_week - timedelta(days=7)

        old_run = WeeklyPlanRun(
            week_start=prior_week,
            generated_by_id=user.id,
            scope=WeeklyPlanScope.FULL_PIPELINE,
            model_version="test",
            total_items=1,
        )
        session.add(old_run)
        session.commit()
        session.refresh(old_run)

        session.add(
            WeeklyPlanItem(
                plan_run_id=old_run.id,
                lead_id=lead.id,
                customer_id=customer.id,
                assigned_to_id=user.id,
                recommended_action=SuggestedAction.FOLLOW_UP,
                channel="EMAIL",
                status=WeeklyPlanItemStatus.COMPLETED,
                priority_score=Decimal("10"),
            )
        )
        session.commit()

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()

        assert lead.id in {it.lead_id for it in items}
