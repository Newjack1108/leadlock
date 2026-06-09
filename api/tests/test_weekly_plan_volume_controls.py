from datetime import datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    CompanySettings,
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
)
from app.weekly_planner_service import WEEKLY_PLAN_MIN_PRIORITY_SCORE, generate_weekly_plan


def _seed_director(session: Session) -> User:
    user = User(
        email="weekly-plan-volume@example.com",
        hashed_password="x",
        full_name="Weekly Planner",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_company(session: Session, user: User, *, max_items: int = 100) -> CompanySettings:
    settings = CompanySettings(
        company_name="Volume Test Co",
        weekly_plan_max_items=max_items,
        updated_by_id=user.id,
    )
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def test_low_score_lead_not_added_to_weekly_plan():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _seed_director(session)
        customer = Customer(
            customer_number="CUST-LOW-SCORE",
            name="Low Score Customer",
            email="low@example.com",
            phone="07111111111",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Low Score Lead",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=user.id,
        )
        session.add(lead)
        session.add(
            ReminderRule(
                rule_name="TEST_WP_LOW_SCORE",
                entity_type="LEAD",
                status=LeadStatus.NEW.value,
                threshold_minutes=0,
                check_type="LAST_ACTIVITY",
                is_active=True,
                priority=ReminderPriority.LOW,
                suggested_action=SuggestedAction.FOLLOW_UP,
            )
        )
        session.commit()

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()

        assert not items
        assert WEEKLY_PLAN_MIN_PRIORITY_SCORE == Decimal("50")


def test_high_score_lead_added_to_weekly_plan():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _seed_director(session)
        customer = Customer(
            customer_number="CUST-HIGH-SCORE",
            name="High Score Customer",
            email="high@example.com",
            phone="07222222222",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="High Score Lead",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=user.id,
        )
        session.add(lead)
        session.add(
            ReminderRule(
                rule_name="TEST_WP_HIGH_SCORE",
                entity_type="LEAD",
                status=LeadStatus.NEW.value,
                threshold_minutes=0,
                check_type="LAST_ACTIVITY",
                is_active=True,
                priority=ReminderPriority.URGENT,
                suggested_action=SuggestedAction.FOLLOW_UP,
            )
        )
        session.commit()
        session.refresh(lead)

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()

        assert len(items) == 1
        assert items[0].lead_id == lead.id
        assert items[0].priority_score >= WEEKLY_PLAN_MIN_PRIORITY_SCORE


def test_weekly_plan_respects_company_max_items_cap():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _seed_director(session)
        _seed_company(session, user, max_items=5)
        now = datetime.utcnow()

        session.add(
            ReminderRule(
                rule_name="TEST_WP_CAP",
                entity_type="QUOTE",
                status=QuoteStatus.SENT.value,
                threshold_minutes=0,
                check_type="SENT_DATE",
                is_active=True,
                priority=ReminderPriority.URGENT,
                suggested_action=SuggestedAction.RESEND_QUOTE,
            )
        )

        for idx in range(8):
            customer = Customer(
                customer_number=f"CUST-CAP-{idx:03d}",
                name=f"Cap Customer {idx}",
                email=f"cap{idx}@example.com",
                phone=f"0733333{idx:04d}",
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)

            quote = Quote(
                customer_id=customer.id,
                quote_number=f"QT-CAP-{idx:03d}",
                status=QuoteStatus.SENT,
                subtotal=Decimal("10000.00"),
                discount_total=Decimal("0.00"),
                total_amount=Decimal("10000.00"),
                created_by_id=user.id,
                sent_at=now - timedelta(days=14 + idx),
            )
            session.add(quote)

        session.commit()

        run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()

        assert len(items) == 5
        scores = [item.priority_score for item in items]
        assert all(score >= WEEKLY_PLAN_MIN_PRIORITY_SCORE for score in scores)
        assert scores == sorted(scores, reverse=True)
