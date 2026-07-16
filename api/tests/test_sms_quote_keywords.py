"""SMS HOLD / CLOSE exact keywords update open quotes."""
import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.models import (
    Customer,
    Lead,
    LeadStatus,
    LossCategory,
    OpportunityStage,
    Quote,
    QuoteStatus,
    User,
    UserRole,
)
from app.sms_quote_keyword_service import (
    apply_sms_quote_keyword,
    detect_quote_keyword,
)


def _engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_user(session: Session) -> User:
    user = User(
        email=f"kw-{datetime.utcnow().timestamp()}@example.com",
        hashed_password="x",
        full_name="Keyword Test",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _seed_customer(session: Session) -> Customer:
    customer = Customer(
        customer_number=f"CUST-KW-{datetime.utcnow().timestamp()}",
        name="Keyword Customer",
        phone="+447700901111",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return customer


def _seed_quote(
    session: Session,
    *,
    user_id: int,
    customer_id: int,
    status: QuoteStatus = QuoteStatus.SENT,
    quote_number: str = "QT-KW-1",
    lead_id: int | None = None,
) -> Quote:
    quote = Quote(
        quote_number=quote_number,
        status=status,
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        created_by_id=user_id,
        customer_id=customer_id,
        lead_id=lead_id,
        sent_at=datetime.utcnow() - timedelta(days=1),
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return quote


def test_detect_quote_keyword_exact_only():
    assert detect_quote_keyword("HOLD") == "hold"
    assert detect_quote_keyword("hold!") == "hold"
    assert detect_quote_keyword("  Close. ") == "close"
    assert detect_quote_keyword("please hold off") is None
    assert detect_quote_keyword("CLOSE please") is None
    assert detect_quote_keyword("hello") is None


def test_hold_sets_on_hold_at_idempotent():
    engine = _engine()
    with Session(engine) as session:
        user = _seed_user(session)
        customer = _seed_customer(session)
        quote = _seed_quote(session, user_id=user.id, customer_id=customer.id)
        other = _seed_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            status=QuoteStatus.ACCEPTED,
            quote_number="QT-KW-ACCEPTED",
        )

        result = apply_sms_quote_keyword(session, customer.id, "HOLD")
        assert result == "hold"

        session.refresh(quote)
        session.refresh(other)
        assert quote.on_hold_at is not None
        first_hold = quote.on_hold_at
        assert other.on_hold_at is None
        assert quote.status == QuoteStatus.SENT

        result2 = apply_sms_quote_keyword(session, customer.id, "hold!")
        assert result2 == "hold"
        session.refresh(quote)
        assert quote.on_hold_at == first_hold


def test_close_marks_lost_and_transitions_quoted_leads():
    engine = _engine()
    with Session(engine) as session:
        user = _seed_user(session)
        customer = _seed_customer(session)
        lead = Lead(
            name="Quoted Lead",
            phone="+447700901111",
            customer_id=customer.id,
            status=LeadStatus.QUOTED,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)

        quote = _seed_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            lead_id=lead.id,
        )
        draft = _seed_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            status=QuoteStatus.DRAFT,
            quote_number="QT-KW-DRAFT",
        )

        result = apply_sms_quote_keyword(session, customer.id, "CLOSE")
        assert result == "close"

        session.refresh(quote)
        session.refresh(draft)
        session.refresh(lead)

        assert quote.status == QuoteStatus.REJECTED
        assert quote.opportunity_stage == OpportunityStage.LOST
        assert quote.loss_reason == "Customer replied CLOSE via SMS"
        assert quote.loss_category == LossCategory.OTHER
        assert draft.status == QuoteStatus.DRAFT
        assert lead.status == LeadStatus.LOST


def test_non_keyword_leaves_quotes_unchanged():
    engine = _engine()
    with Session(engine) as session:
        user = _seed_user(session)
        customer = _seed_customer(session)
        quote = _seed_quote(session, user_id=user.id, customer_id=customer.id)

        result = apply_sms_quote_keyword(session, customer.id, "please hold off")
        assert result is None

        session.refresh(quote)
        assert quote.on_hold_at is None
        assert quote.status == QuoteStatus.SENT


def test_close_does_not_touch_already_rejected():
    engine = _engine()
    with Session(engine) as session:
        user = _seed_user(session)
        customer = _seed_customer(session)
        rejected = _seed_quote(
            session,
            user_id=user.id,
            customer_id=customer.id,
            status=QuoteStatus.REJECTED,
            quote_number="QT-KW-REJ",
        )
        rejected.loss_reason = "Already lost"
        session.add(rejected)
        session.commit()

        result = apply_sms_quote_keyword(session, customer.id, "CLOSE")
        assert result == "close"

        session.refresh(rejected)
        assert rejected.loss_reason == "Already lost"
