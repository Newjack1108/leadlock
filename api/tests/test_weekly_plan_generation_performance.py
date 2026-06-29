import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import (
    Customer,
    Email,
    EmailDirection,
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
from app.weekly_planner_service import generate_weekly_plan


def _seed_director(session: Session) -> User:
    user = User(
        email="weekly-plan-perf@example.com",
        hashed_password="x",
        full_name="Weekly Planner",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _mock_ai_response(*_args, **_kwargs):
    time.sleep(0.05)
    return (
        Decimal("70"),
        Decimal("0.75"),
        ["positive_buy_intent"],
        "ai-test",
        "Likely to order soon.",
        ["Follow up by email", "Confirm timeline", "Log next action"],
    )


def test_many_stale_candidates_cap_ai_calls(monkeypatch):
    """Generation should stay fast when many candidates have inbound text (AI capped)."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("WEEKLY_PLAN_MAX_AI_CALLS", "5")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _seed_director(session)
        session.add(
            ReminderRule(
                rule_name="TEST_WP_PERF_QUOTES",
                entity_type="QUOTE",
                status=QuoteStatus.SENT.value,
                threshold_minutes=0,
                check_type="SENT_DATE",
                is_active=True,
                priority=ReminderPriority.URGENT,
                suggested_action=SuggestedAction.RESEND_QUOTE,
            )
        )
        now = datetime.utcnow()

        for idx in range(30):
            customer = Customer(
                customer_number=f"CUST-PERF-{idx:03d}",
                name=f"Perf Customer {idx}",
                email=f"perf{idx}@example.com",
                phone=f"0744444{idx:04d}",
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)

            session.add(
                Email(
                    customer_id=customer.id,
                    direction=EmailDirection.RECEIVED,
                    from_email=f"perf{idx}@example.com",
                    to_email="sales@example.com",
                    subject="Still interested",
                    body_text="ready to order when you send details",
                    received_at=now - timedelta(hours=2),
                )
            )

            quote = Quote(
                customer_id=customer.id,
                quote_number=f"QT-PERF-{idx:03d}",
                status=QuoteStatus.SENT,
                subtotal=Decimal("12000.00"),
                discount_total=Decimal("0.00"),
                total_amount=Decimal("12000.00"),
                created_by_id=user.id,
                sent_at=now - timedelta(days=10 + idx),
            )
            session.add(quote)

        session.commit()

        ai_calls = {"count": 0}

        def counting_ai(*args, **kwargs):
            ai_calls["count"] += 1
            return _mock_ai_response(*args, **kwargs)

        started = time.monotonic()
        with patch("app.weekly_planner_service._ai_order_likelihood_from_text", side_effect=counting_ai):
            run = generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)
        elapsed = time.monotonic() - started

        items = session.exec(select(WeeklyPlanItem).where(WeeklyPlanItem.plan_run_id == run.id)).all()

        assert ai_calls["count"] == 5
        assert len(items) > 0
        assert elapsed < 5.0


def test_low_score_candidates_skip_ai_without_inbound_text(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("WEEKLY_PLAN_MAX_AI_CALLS", "20")

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _seed_director(session)
        customer = Customer(
            customer_number="CUST-PERF-LOW",
            name="Low Priority Customer",
            email="lowperf@example.com",
            phone="07555555555",
        )
        session.add(customer)
        session.commit()
        session.refresh(customer)

        lead = Lead(
            name="Low Priority Lead",
            status=LeadStatus.NEW,
            customer_id=customer.id,
            assigned_to_id=user.id,
        )
        session.add(lead)
        session.add(
            ReminderRule(
                rule_name="TEST_WP_PERF_LOW",
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

        ai_calls = {"count": 0}

        def counting_ai(*args, **kwargs):
            ai_calls["count"] += 1
            return _mock_ai_response(*args, **kwargs)

        with patch("app.weekly_planner_service._ai_order_likelihood_from_text", side_effect=counting_ai):
            generate_weekly_plan(session, generated_by_id=user.id, auto_execute=False, dry_run=False)

        items = session.exec(select(WeeklyPlanItem)).all()
        assert not items
        assert ai_calls["count"] == 0
