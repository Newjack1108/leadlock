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
    ReviewPrizeDrawEntry,
    ReviewPrizeDrawEntryStatus,
    User,
    UserRole,
)
from app.review_prize_draw_service import (
    add_manual_entries,
    approve_entry,
    build_prize_draw_celebration_banner_url,
    build_prize_draw_congratulations_context,
    delete_manual_entry,
    ensure_prize_draw_entry,
    get_winner_for_month,
    list_entries,
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


def test_list_entries_filters_by_submitted_month_not_entry_month(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)

        # Minted but not submitted — excluded from submitted_month filter
        unsubmitted = ensure_prize_draw_entry(order, session)
        session.commit()

        customer = session.get(Customer, order.customer_id)
        quote2 = Quote(
            quote_number="QT-PD-2",
            customer_id=customer.id,
            status=QuoteStatus.ACCEPTED,
            subtotal=1000,
            discount_total=0,
            total_amount=1000,
            currency="GBP",
            created_by_id=user.id,
        )
        session.add(quote2)
        session.commit()
        session.refresh(quote2)
        order2 = Order(
            quote_id=quote2.id,
            customer_id=customer.id,
            order_number="ORD-PD-2",
            subtotal=1000,
            discount_total=0,
            total_amount=1000,
            currency="GBP",
            created_by_id=user.id,
            installation_completed=True,
            installation_completed_at=datetime.utcnow() - timedelta(days=5),
        )
        session.add(order2)
        session.commit()
        session.refresh(order2)

        this_month = datetime.utcnow().strftime("%Y-%m")
        year, mon = map(int, this_month.split("-"))
        if mon == 1:
            prev_month = f"{year - 1}-12"
            prev_submitted = datetime(year - 1, 12, 15)
        else:
            prev_month = f"{year}-{mon - 1:02d}"
            prev_submitted = datetime(year, mon - 1, 15)

        # Submitted previous month, approved into this month's draw pool
        prev_entry = ensure_prize_draw_entry(order2, session)
        submit_prize_draw_entry(prev_entry.access_token, ["GOOGLE", "FACEBOOK"], session)
        session.commit()
        prev_entry = session.get(ReviewPrizeDrawEntry, prev_entry.id)
        prev_entry.submitted_at = prev_submitted
        session.add(prev_entry)
        session.commit()
        approve_entry(prev_entry.id, user, session)
        session.commit()
        prev_entry = session.get(ReviewPrizeDrawEntry, prev_entry.id)
        assert prev_entry.entry_month == this_month

        # Unsubmitted must not appear under the current month filter
        assert list_entries(session, submitted_month=this_month) == []

        # Submit the first order's entry this month (still pending)
        submit_prize_draw_entry(unsubmitted.access_token, ["GOOGLE", "TRUSTPILOT"], session)
        session.commit()
        current_entry = session.get(ReviewPrizeDrawEntry, unsubmitted.id)

        listed = list_entries(session, submitted_month=this_month)
        listed_ids = {e.id for e in listed}
        assert current_entry.id in listed_ids
        assert prev_entry.id not in listed_ids

        listed_prev = list_entries(session, submitted_month=prev_month)
        assert {e.id for e in listed_prev} == {prev_entry.id}

        pool = list_entries(
            session,
            entry_month=this_month,
            status=ReviewPrizeDrawEntryStatus.APPROVED,
        )
        assert {e.id for e in pool} == {prev_entry.id}


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


def test_congratulations_context_includes_celebration_banner_url(sqlite_engine):
    from app.models import Customer

    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        customer = session.get(Customer, order.customer_id)
        assert customer is not None
        month = "2026-06"

        ctx = build_prize_draw_congratulations_context(settings, order, customer, month)
        banner_url = ctx["prize_draw"]["celebration_banner_url"]
        assert banner_url
        assert "/email/prize-draw-celebration.png" in banner_url

        settings.review_prize_draw_congratulations_banner_url = "https://example.com/custom.gif"
        session.add(settings)
        session.commit()
        ctx_custom = build_prize_draw_congratulations_context(settings, order, customer, month)
        assert ctx_custom["prize_draw"]["celebration_banner_url"] == "https://example.com/custom.gif"


def test_build_prize_draw_celebration_banner_url_custom_override(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        settings.review_prize_draw_congratulations_banner_url = "https://cdn.example.com/banner.png"
        assert (
            build_prize_draw_celebration_banner_url(settings) == "https://cdn.example.com/banner.png"
        )


@patch("app.review_prize_draw_service.is_email_configured", return_value=True)
@patch(
    "app.review_prize_draw_service.send_email",
    return_value=(True, "msg-id", None, "<p>Banner</p>", "Banner"),
)
def test_send_congratulations_email_includes_banner_url(mock_send_email, mock_email_cfg, sqlite_engine):
    from app.models import EmailTemplate

    with Session(sqlite_engine) as session:
        settings, order, user, _winner, month = _seed_winner(session)
        email_template = session.get(
            EmailTemplate, settings.review_prize_draw_congratulations_email_template_id
        )
        assert email_template is not None
        email_template.body_template = (
            '<img src="{{ prize_draw.celebration_banner_url }}" alt="Congrats" />'
            "<p>Hi {{ customer.name }}</p>"
        )
        session.add(email_template)
        session.commit()

        send_congratulations_to_winner(month, user, session, channel="email")
        session.commit()

        body_html = mock_send_email.call_args.kwargs["body_html"]
        assert "/email/prize-draw-celebration.png" in body_html


def test_backfill_congratulations_email_adds_celebration_banner(sqlite_engine):
    from app.database import backfill_prize_draw_congratulations_templates
    from app.models import EmailTemplate

    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        stale_email = EmailTemplate(
            name="Prize Draw Winner Congratulations",
            subject_template="You won",
            body_template="<p>Hi {{ customer.name }}, you won.</p>",
            created_by_id=user.id,
        )
        session.add(stale_email)
        session.commit()
        session.refresh(stale_email)

        backfill_prize_draw_congratulations_templates(session)
        session.refresh(stale_email)

        assert "celebration_banner_url" in stale_email.body_template
        assert "🎉" in stale_email.body_template


def test_backfill_congratulations_sms_adds_celebration_emojis(sqlite_engine):
    from app.database import backfill_prize_draw_congratulations_templates
    from app.models import SmsTemplate

    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        stale_sms = SmsTemplate(
            name="Prize Draw Winner Congratulations",
            body_template="Congratulations {{ customer.name }}! You won.",
            created_by_id=user.id,
        )
        session.add(stale_sms)
        session.commit()
        session.refresh(stale_sms)

        backfill_prize_draw_congratulations_templates(session)
        session.refresh(stale_sms)

        assert "🎉" in stale_sms.body_template
        assert "🏆" in stale_sms.body_template


def test_add_manual_entries_are_approved_for_month(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        month = datetime.utcnow().strftime("%Y-%m")

        created, err = add_manual_entries(
            ["  Jane Smith  ", "Jane Smith", "Bob Jones", ""],
            month,
            user,
            session,
        )
        session.commit()

        assert err is None
        assert created is not None
        assert [e.manual_name for e in created] == ["Jane Smith", "Bob Jones"]
        assert all(e.status == ReviewPrizeDrawEntryStatus.APPROVED for e in created)
        assert all(e.entry_month == month for e in created)
        assert all(e.order_id is None for e in created)

        listed = list_entries(session, submitted_month=month)
        listed_names = {e.manual_name for e in listed}
        assert listed_names == {"Jane Smith", "Bob Jones"}

        pool = list_entries(
            session,
            entry_month=month,
            status=ReviewPrizeDrawEntryStatus.APPROVED,
        )
        assert {e.id for e in pool} == {e.id for e in created}


def test_add_manual_entries_rejects_empty_and_bad_month(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)

        created, err = add_manual_entries(["  "], "2026-09", user, session)
        assert created is None
        assert "at least one name" in (err or "").lower()

        created, err = add_manual_entries(["Ada"], "2026-13", user, session)
        assert created is None
        assert "yyyy-mm" in (err or "").lower()


def test_pick_random_winner_can_select_manual_entry(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        month = datetime.utcnow().strftime("%Y-%m")

        created, err = add_manual_entries(["Manual Winner"], month, user, session)
        session.commit()
        assert err is None
        assert created is not None

        winner, pick_err = pick_random_winner(month, user, session)
        session.commit()
        assert pick_err is None
        assert winner.entry_id == created[0].id


def test_delete_manual_entry_and_block_winner_delete(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        month = datetime.utcnow().strftime("%Y-%m")

        created, err = add_manual_entries(["Removable", "Winner Name"], month, user, session)
        session.commit()
        assert err is None
        removable, winner_entry = created

        success, delete_err = delete_manual_entry(removable.id, session)
        session.commit()
        assert success is True
        assert delete_err is None
        assert session.get(ReviewPrizeDrawEntry, removable.id) is None

        winner, pick_err = pick_random_winner(month, user, session)
        session.commit()
        assert pick_err is None
        assert winner.entry_id == winner_entry.id

        blocked, blocked_err = delete_manual_entry(winner_entry.id, session)
        assert blocked is False
        assert "winner" in (blocked_err or "").lower()

        customer_entry = ensure_prize_draw_entry(order, session)
        session.commit()
        blocked_customer, customer_err = delete_manual_entry(customer_entry.id, session)
        assert blocked_customer is False
        assert "manually added" in (customer_err or "").lower()


def test_send_congratulations_rejects_manual_winner(sqlite_engine):
    with Session(sqlite_engine) as session:
        settings, _order = _seed(session)
        user = session.get(User, settings.updated_by_id)
        month = datetime.utcnow().strftime("%Y-%m")
        add_manual_entries(["No Contact"], month, user, session)
        session.commit()
        pick_random_winner(month, user, session)
        session.commit()

        updated, err = send_congratulations_to_winner(month, user, session, channel="email")
        assert updated is None
        assert "manually added" in (err or "").lower()
