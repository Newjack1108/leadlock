from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Customer,
    OpportunityStage,
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


def _seed_user_customer(session: Session) -> tuple[User, Customer]:
    user = User(
        email="weekly-plan-dedupe@example.com",
        hashed_password="x",
        full_name="Weekly Planner",
        role=UserRole.DIRECTOR,
    )
    customer = Customer(
        customer_number="CUST-DEDUPE-001",
        name="Dedupe Customer",
        email="dedupe@example.com",
        phone="07123456789",
    )
    session.add(user)
    session.add(customer)
    session.commit()
    session.refresh(user)
    session.refresh(customer)
    return user, customer


def test_weekly_plan_uses_latest_quote_once_per_customer():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user, customer = _seed_user_customer(session)
        now = datetime.utcnow()

        older_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-OLDER-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1000.00"),
            created_by_id=user.id,
            sent_at=now - timedelta(days=14),
        )
        latest_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-LATEST-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("2000.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("2000.00"),
            created_by_id=user.id,
            sent_at=now - timedelta(days=2),
        )
        session.add(older_quote)
        session.add(latest_quote)

        sent_rule = ReminderRule(
            rule_name="TEST_WP_SENT_STALE",
            entity_type="QUOTE",
            status=QuoteStatus.SENT.value,
            threshold_minutes=0,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.RESEND_QUOTE,
        )
        draft_rule = ReminderRule(
            rule_name="TEST_WP_DRAFT_STALE",
            entity_type="QUOTE",
            status=QuoteStatus.DRAFT.value,
            threshold_minutes=0,
            check_type="STATUS_DURATION",
            is_active=True,
            priority=ReminderPriority.LOW,
            suggested_action=SuggestedAction.CONTACT_CUSTOMER,
        )
        session.add(sent_rule)
        session.add(draft_rule)
        session.commit()
        session.refresh(older_quote)
        session.refresh(latest_quote)

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items = session.exec(
            select(WeeklyPlanItem).where(
                WeeklyPlanItem.plan_run_id == run.id,
                WeeklyPlanItem.customer_id == customer.id,
                WeeklyPlanItem.quote_id.is_not(None),
            )
        ).all()

        assert len(items) == 1
        assert items[0].quote_id == latest_quote.id


def test_weekly_plan_skips_opportunity_when_customer_already_has_quote_item():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user, customer = _seed_user_customer(session)
        now = datetime.utcnow()

        sent_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-SENT-OPP-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("1500.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("1500.00"),
            created_by_id=user.id,
            sent_at=now - timedelta(days=6),
            opportunity_stage=OpportunityStage.QUOTE_SENT,
        )
        older_opp_quote = Quote(
            customer_id=customer.id,
            quote_number="QT-OLD-OPP-001",
            status=QuoteStatus.SENT,
            subtotal=Decimal("900.00"),
            discount_total=Decimal("0.00"),
            total_amount=Decimal("900.00"),
            created_by_id=user.id,
            sent_at=now - timedelta(days=20),
            opportunity_stage=OpportunityStage.QUOTE_SENT,
        )
        session.add(sent_quote)
        session.add(older_opp_quote)

        sent_rule = ReminderRule(
            rule_name="TEST_WP_OPP_SENT_STALE",
            entity_type="QUOTE",
            status=QuoteStatus.SENT.value,
            threshold_minutes=0,
            check_type="SENT_DATE",
            is_active=True,
            priority=ReminderPriority.MEDIUM,
            suggested_action=SuggestedAction.RESEND_QUOTE,
        )
        session.add(sent_rule)
        session.commit()
        session.refresh(sent_quote)
        session.refresh(older_opp_quote)

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        quote_items = session.exec(
            select(WeeklyPlanItem).where(
                WeeklyPlanItem.plan_run_id == run.id,
                WeeklyPlanItem.customer_id == customer.id,
                WeeklyPlanItem.quote_id.is_not(None),
            )
        ).all()

        assert len(quote_items) == 1
        assert quote_items[0].quote_id == sent_quote.id
