"""Monthly review prize draw entry and winner selection."""
import os
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from unittest.mock import patch
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import (
    CompanySettings,
    Customer,
    Order,
    Quote,
    QuoteStatus,
    ReviewPrizeDrawEntryStatus,
    User,
    UserRole,
)
from app.review_prize_draw_service import (
    approve_entry,
    ensure_prize_draw_entry,
    get_winner_for_month,
    pick_random_winner,
    reject_entry,
    reset_winner_for_month,
    send_congratulations_to_winner,
    submit_prize_draw_entry,
)
from app.review_request_service import build_review_template_context


@pytest.fixture()
def sqlite_engine():
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session, *, prize_enabled: bool = True) -> tuple[CompanySettings, Order]:
    user = User(
        email="director@example.com",
        hashed_password="x",
        full_name="Director",
        role=UserRole.DIRECTOR,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    settings = CompanySettings(
        company_name="Test Co",
        review_google_url="https://example.com/google",
        review_facebook_url="https://example.com/facebook",
        review_trustpilot_url="https://example.com/trustpilot",
        review_prize_draw_enabled=prize_enabled,
        review_prize_draw_title="Monthly voucher",
        review_prize_draw_min_platforms=2,
        updated_by_id=user.id,
    )
    session.add(settings)

    customer = Customer(
        customer_number="CUST-PD-1",
        name="Prize Customer",
        email="prize@example.com",
    )
    session.add(customer)
    session.commit()
    session.refresh(customer)

    quote = Quote(
        quote_number="QT-PD-1",
        customer_id=customer.id,
        status=QuoteStatus.ACCEPTED,
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        currency="GBP",
        created_by_id=user.id,
    )
    session.add(quote)
    session.commit()
    session.refresh(quote)

    order = Order(
        quote_id=quote.id,
        customer_id=customer.id,
        order_number="ORD-PD-1",
        subtotal=1000,
        discount_total=0,
        total_amount=1000,
        currency="GBP",
        created_by_id=user.id,
        installation_completed=True,
        installation_completed_at=datetime.utcnow() - timedelta(days=5),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return settings, order


def test_ensure_prize_draw_entry_mints_token(sqlite_engine):
    with Session(sqlite_engine) as session:
        _, order = _seed(session)
        entry = ensure_prize_draw_entry(order, session)
        session.commit()
        assert entry is not None
        assert entry.access_token
        again = ensure_prize_draw_entry(order, session)
        assert again.id == entry.id


def test_submit_requires_two_platforms(sqlite_engine):
    with Session(sqlite_engine) as session:
        _, order = _seed(session)
        entry = ensure_prize_draw_entry(order, session)
        session.commit()

        _, err = submit_prize_draw_entry(entry.access_token, ["GOOGLE"], session)
        assert err is not None

        updated, err = submit_prize_draw_entry(
            entry.access_token, ["GOOGLE", "FACEBOOK"], session
        )
        session.commit()
        assert err is None
        assert updated.status == ReviewPrizeDrawEntryStatus.PENDING
        assert updated.submitted_at is not None


def test_approve_sets_entry_month(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        entry = ensure_prize_draw_entry(order, session)
        submit_prize_draw_entry(entry.access_token, ["GOOGLE", "TRUSTPILOT"], session)
        session.commit()

        approved, err = approve_entry(entry.id, user, session)
        session.commit()
        assert err is None
        assert approved.status == ReviewPrizeDrawEntryStatus.APPROVED
        assert approved.entry_month == datetime.utcnow().strftime("%Y-%m")


def test_reject_allows_resubmit(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        entry = ensure_prize_draw_entry(order, session)
        submit_prize_draw_entry(entry.access_token, ["GOOGLE", "FACEBOOK"], session)
        session.commit()

        reject_entry(entry.id, user, session, note="Not verified")
        session.commit()

        updated, err = submit_prize_draw_entry(
            entry.access_token, ["GOOGLE", "TRUSTPILOT"], session
        )
        session.commit()
        assert err is None
        assert updated.status == ReviewPrizeDrawEntryStatus.PENDING


def test_reset_winner_for_month_clears_and_allows_repick(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        entry = ensure_prize_draw_entry(order, session)
        submit_prize_draw_entry(entry.access_token, ["GOOGLE", "FACEBOOK"], session)
        approve_entry(entry.id, user, session)
        session.commit()

        month = datetime.utcnow().strftime("%Y-%m")
        first, err = pick_random_winner(month, user, session)
        session.commit()
        assert err is None
        assert first is not None

        success, reset_err = reset_winner_for_month(month, user, session)
        session.commit()
        assert success is True
        assert reset_err is None
        assert get_winner_for_month(session, month) is None

        second, err2 = pick_random_winner(month, user, session)
        session.commit()
        assert err2 is None
        assert second is not None
        assert second.entry_id == entry.id
        assert get_winner_for_month(session, month) is not None


def test_reset_winner_for_month_without_winner_returns_error(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        month = datetime.utcnow().strftime("%Y-%m")

        success, err = reset_winner_for_month(month, user, session)
        assert success is False
        assert "no winner" in (err or "").lower()


def _seed_winner(session: Session):
    from app.models import EmailTemplate

    settings, order = _seed(session)
    user = session.get(User, settings.updated_by_id)
    email_template = EmailTemplate(
        name="Congrats Email",
        subject_template="You won {{ prize_draw.title }}",
        body_template="<p>Hi {{ customer.name }}, you won {{ prize_draw.title }} for {{ prize_draw.month }}.</p>",
        created_by_id=user.id,
    )
    session.add(email_template)
    session.commit()
    session.refresh(email_template)
    settings.review_prize_draw_congratulations_email_template_id = email_template.id
    session.add(settings)

    entry = ensure_prize_draw_entry(order, session)
    submit_prize_draw_entry(entry.access_token, ["GOOGLE", "FACEBOOK"], session)
    approve_entry(entry.id, user, session)
    session.commit()

    month = datetime.utcnow().strftime("%Y-%m")
    winner, err = pick_random_winner(month, user, session)
    session.commit()
    assert err is None
    return settings, order, user, winner, month


@patch("app.review_prize_draw_service.is_email_configured", return_value=True)
@patch(
    "app.review_prize_draw_service.send_email",
    return_value=(True, "msg-id", None, "<p>You won</p>", "You won"),
)
def test_send_congratulations_sets_sent_timestamp(mock_send_email, mock_email_cfg, sqlite_engine):
    with Session(sqlite_engine) as session:
        _settings, _order, user, winner, month = _seed_winner(session)

        updated, err = send_congratulations_to_winner(month, user, session, channel="email")
        session.commit()
        session.refresh(updated)

        assert err is None
        assert updated.congratulations_sent_at is not None
        assert updated.congratulations_channel == "EMAIL"
        mock_send_email.assert_called_once()


@patch("app.review_prize_draw_service.is_email_configured", return_value=True)
@patch(
    "app.review_prize_draw_service.send_email",
    return_value=(True, "msg-id", None, "<p>You won</p>", "You won"),
)
def test_send_congratulations_blocks_duplicate_without_force(
    mock_send_email, mock_email_cfg, sqlite_engine
):
    with Session(sqlite_engine) as session:
        _settings, _order, user, _winner, month = _seed_winner(session)

        send_congratulations_to_winner(month, user, session, channel="email")
        session.commit()
        mock_send_email.reset_mock()

        updated, err = send_congratulations_to_winner(month, user, session, channel="email")
        assert updated is None
        assert "already sent" in (err or "").lower()
        mock_send_email.assert_not_called()


@patch("app.review_prize_draw_service.is_email_configured", return_value=True)
@patch(
    "app.review_prize_draw_service.send_email",
    side_effect=[
        (True, "msg-id-1", None, "<p>You won</p>", "You won"),
        (True, "msg-id-2", None, "<p>You won again</p>", "You won again"),
    ],
)
def test_send_congratulations_force_resend(mock_send_email, mock_email_cfg, sqlite_engine):
    with Session(sqlite_engine) as session:
        _settings, _order, user, _winner, month = _seed_winner(session)

        send_congratulations_to_winner(month, user, session, channel="email")
        session.commit()
        mock_send_email.reset_mock()

        updated, err = send_congratulations_to_winner(
            month, user, session, channel="email", force=True
        )
        session.commit()
        assert err is None
        assert updated.congratulations_sent_at is not None
        mock_send_email.assert_called_once()


def test_send_congratulations_missing_template_returns_error(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        entry = ensure_prize_draw_entry(order, session)
        submit_prize_draw_entry(entry.access_token, ["GOOGLE", "FACEBOOK"], session)
        approve_entry(entry.id, user, session)
        session.commit()

        month = datetime.utcnow().strftime("%Y-%m")
        pick_random_winner(month, user, session)
        session.commit()

        updated, err = send_congratulations_to_winner(month, user, session, channel="email")
        assert updated is None
        assert "email template" in (err or "").lower()


def test_pick_random_winner_idempotent(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        entry = ensure_prize_draw_entry(order, session)
        submit_prize_draw_entry(entry.access_token, ["GOOGLE", "FACEBOOK"], session)
        approve_entry(entry.id, user, session)
        session.commit()

        month = datetime.utcnow().strftime("%Y-%m")
        first, err = pick_random_winner(month, user, session)
        session.commit()
        assert err is None
        assert first.entry_id == entry.id

        second, err2 = pick_random_winner(month, user, session)
        assert err2 is None
        assert second.id == first.id
        assert get_winner_for_month(session, month).entry_id == entry.id


def test_backfill_updates_stale_review_templates(sqlite_engine):
    from app.database import backfill_review_request_templates
    from app.models import EmailTemplate, SmsTemplate

    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        stale_sms = SmsTemplate(
            name="Post-Install Review Request",
            body_template="Google: {{ review.google_url }}",
            created_by_id=user.id,
        )
        stale_email = EmailTemplate(
            name="Post-Install Review Request",
            subject_template="Feedback",
            body_template="<p>{{ review.google_url }}</p>",
            created_by_id=user.id,
        )
        session.add(stale_sms)
        session.add(stale_email)
        settings.review_request_sms_template_id = None
        settings.review_request_email_template_id = None
        session.add(settings)
        session.commit()

        backfill_review_request_templates(session)
        session.refresh(stale_sms)
        session.refresh(stale_email)

        assert "hub_url" in stale_sms.body_template
        assert "hub_url" in stale_email.body_template


def test_template_context_includes_prize_draw_url(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        ensure_prize_draw_entry(order, session)
        session.commit()
        ctx = build_review_template_context(settings, order, session)
        assert ctx["review"]["prize_draw_url"]
        assert ctx["review"]["prize_draw_title"] == "Monthly voucher"
