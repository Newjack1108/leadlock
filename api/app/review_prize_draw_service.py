"""
Monthly review prize draw: customer self-declaration with staff approval.
"""
from __future__ import annotations

import os
import random
import secrets
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlmodel import Session, select, and_

from app.email_service import send_email, is_email_configured, _html_to_plain, build_activity_email_notes
from app.email_template_service import render_email_template
from app.models import (
    Activity,
    ActivityType,
    CompanySettings,
    Customer,
    CustomerOutreachChannel,
    Email,
    EmailDirection,
    EmailTemplate,
    Order,
    Quote,
    ReviewPrizeDrawEntry,
    ReviewPrizeDrawEntryStatus,
    ReviewPrizeDrawPlatform,
    ReviewPrizeDrawWinner,
    SmsMessage,
    SmsDirection,
    SmsTemplate,
    User,
)
from app.order_audit import record_order_audit_event
from app.schemas import CustomerHistoryEventType
from app.sms_service import send_sms, normalize_phone, is_unsubscribed_recipient_error, resolve_sms_to_phone
from app.sms_template_service import render_sms_template

PLATFORM_LABELS = {
    ReviewPrizeDrawPlatform.GOOGLE.value: "Google",
    ReviewPrizeDrawPlatform.FACEBOOK.value: "Facebook",
    ReviewPrizeDrawPlatform.TRUSTPILOT.value: "Trustpilot",
}


def _get_company_settings(session: Session) -> Optional[CompanySettings]:
    return session.exec(select(CompanySettings).limit(1)).first()


def is_prize_draw_enabled(settings: Optional[CompanySettings]) -> bool:
    return bool(settings and settings.review_prize_draw_enabled)


def _frontend_base_url() -> str:
    frontend = (os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_FRONTEND_URL") or "").strip()
    if not frontend or not (frontend.startswith("http://") or frontend.startswith("https://")):
        frontend = "https://leadlock-frontend-production.up.railway.app"
    return frontend.rstrip("/")


def build_prize_draw_url(token: str) -> str:
    return f"{_frontend_base_url()}/review-prize/{token}"


def build_prize_draw_celebration_banner_url(settings: Optional[CompanySettings]) -> str:
    custom = (
        (settings.review_prize_draw_congratulations_banner_url or "").strip()
        if settings
        else ""
    )
    if custom:
        return custom
    return f"{_frontend_base_url()}/email/prize-draw-celebration.png"


def get_entry_for_order(session: Session, order_id: int) -> Optional[ReviewPrizeDrawEntry]:
    return session.exec(
        select(ReviewPrizeDrawEntry)
        .where(ReviewPrizeDrawEntry.order_id == order_id)
        .order_by(ReviewPrizeDrawEntry.created_at.desc())
        .limit(1)
    ).first()


def get_entry_by_token(session: Session, token: str) -> Optional[ReviewPrizeDrawEntry]:
    return session.exec(
        select(ReviewPrizeDrawEntry).where(ReviewPrizeDrawEntry.access_token == token)
    ).first()


def configured_platforms(settings: Optional[CompanySettings]) -> List[Tuple[str, str]]:
    """Return (code, label) for platforms with URLs configured."""
    if not settings:
        return []
    platforms: List[Tuple[str, str]] = []
    if settings.review_google_url:
        platforms.append((ReviewPrizeDrawPlatform.GOOGLE.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.GOOGLE.value]))
    if settings.review_facebook_url:
        platforms.append((ReviewPrizeDrawPlatform.FACEBOOK.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.FACEBOOK.value]))
    if settings.review_trustpilot_url:
        platforms.append(
            (ReviewPrizeDrawPlatform.TRUSTPILOT.value, PLATFORM_LABELS[ReviewPrizeDrawPlatform.TRUSTPILOT.value])
        )
    return platforms


def ensure_prize_draw_entry(order: Order, session: Session) -> Optional[ReviewPrizeDrawEntry]:
    """Mint a prize draw token for an order when prize draw is enabled."""
    if not order.id or not order.customer_id:
        return None
    settings = _get_company_settings(session)
    if not is_prize_draw_enabled(settings):
        return None

    existing = get_entry_for_order(session, order.id)
    if existing:
        return existing

    entry = ReviewPrizeDrawEntry(
        order_id=order.id,
        customer_id=order.customer_id,
        access_token=secrets.token_urlsafe(32),
        status=ReviewPrizeDrawEntryStatus.PENDING,
    )
    session.add(entry)
    session.flush()
    return entry


def _validate_platforms(
    platforms: List[str],
    settings: CompanySettings,
) -> Tuple[bool, Optional[str]]:
    allowed = {code for code, _ in configured_platforms(settings)}
    if not allowed:
        return False, "No review platforms configured"
    normalized = []
    for p in platforms:
        code = (p or "").strip().upper()
        if code not in allowed:
            return False, f"Invalid platform: {p}"
        if code not in normalized:
            normalized.append(code)
    min_required = max(1, int(settings.review_prize_draw_min_platforms or 2))
    if len(normalized) < min_required:
        return False, f"Select at least {min_required} platforms"
    return True, None


def submit_prize_draw_entry(
    token: str,
    platforms: List[str],
    session: Session,
) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = get_entry_by_token(session, token)
    if not entry:
        return None, "Prize draw entry not found"

    if entry.status == ReviewPrizeDrawEntryStatus.APPROVED:
        return None, "Entry already approved"
    if entry.status == ReviewPrizeDrawEntryStatus.PENDING and entry.submitted_at:
        return None, "Entry already submitted and awaiting approval"

    settings = _get_company_settings(session)
    if not settings or not is_prize_draw_enabled(settings):
        return None, "Prize draw is not enabled"

    ok, err = _validate_platforms(platforms, settings)
    if not ok:
        return None, err

    normalized = []
    for p in platforms:
        code = p.strip().upper()
        if code not in normalized:
            normalized.append(code)

    now = datetime.utcnow()
    entry.platforms_claimed = normalized
    entry.status = ReviewPrizeDrawEntryStatus.PENDING
    entry.submitted_at = now
    entry.reviewed_at = None
    entry.reviewed_by_id = None
    entry.rejection_note = None
    entry.entry_month = None
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_SUBMITTED.value,
            title="Review Prize Draw Submitted",
            description=f"Customer submitted prize draw entry for order {order.order_number}",
            order=order,
            metadata={"platforms": normalized},
        )
    return entry, None


def approve_entry(entry_id: int, user: User, session: Session) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = session.get(ReviewPrizeDrawEntry, entry_id)
    if not entry:
        return None, "Entry not found"
    if entry.status != ReviewPrizeDrawEntryStatus.PENDING or not entry.submitted_at:
        return None, "Only pending submitted entries can be approved"

    now = datetime.utcnow()
    entry.status = ReviewPrizeDrawEntryStatus.APPROVED
    entry.reviewed_at = now
    entry.reviewed_by_id = user.id
    entry.rejection_note = None
    entry.entry_month = now.strftime("%Y-%m")
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_APPROVED.value,
            title="Review Prize Draw Approved",
            description=f"Prize draw entry approved for order {order.order_number}",
            order=order,
            metadata={"platforms": entry.platforms_claimed, "entry_month": entry.entry_month},
            created_by_id=user.id,
        )
    return entry, None


def reject_entry(
    entry_id: int,
    user: User,
    session: Session,
    *,
    note: Optional[str] = None,
) -> Tuple[Optional[ReviewPrizeDrawEntry], Optional[str]]:
    entry = session.get(ReviewPrizeDrawEntry, entry_id)
    if not entry:
        return None, "Entry not found"
    if entry.status != ReviewPrizeDrawEntryStatus.PENDING or not entry.submitted_at:
        return None, "Only pending submitted entries can be rejected"

    now = datetime.utcnow()
    entry.status = ReviewPrizeDrawEntryStatus.REJECTED
    entry.reviewed_at = now
    entry.reviewed_by_id = user.id
    entry.rejection_note = (note or "").strip() or None
    entry.entry_month = None
    session.add(entry)

    order = session.get(Order, entry.order_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_REJECTED.value,
            title="Review Prize Draw Rejected",
            description=f"Prize draw entry rejected for order {order.order_number}",
            order=order,
            metadata={"platforms": entry.platforms_claimed, "note": entry.rejection_note},
            created_by_id=user.id,
        )
    return entry, None


def list_entries(
    session: Session,
    *,
    month: Optional[str] = None,
    status: Optional[ReviewPrizeDrawEntryStatus] = None,
) -> List[ReviewPrizeDrawEntry]:
    statement = select(ReviewPrizeDrawEntry).order_by(ReviewPrizeDrawEntry.submitted_at.desc())
    if month:
        statement = statement.where(ReviewPrizeDrawEntry.entry_month == month)
    if status:
        statement = statement.where(ReviewPrizeDrawEntry.status == status)
    return list(session.exec(statement).all())


def get_winner_for_month(session: Session, month: str) -> Optional[ReviewPrizeDrawWinner]:
    return session.exec(
        select(ReviewPrizeDrawWinner).where(ReviewPrizeDrawWinner.month == month)
    ).first()


def pick_random_winner(
    month: str,
    user: User,
    session: Session,
) -> Tuple[Optional[ReviewPrizeDrawWinner], Optional[str]]:
    existing = get_winner_for_month(session, month)
    if existing:
        return existing, None

    approved = list(
        session.exec(
            select(ReviewPrizeDrawEntry).where(
                and_(
                    ReviewPrizeDrawEntry.status == ReviewPrizeDrawEntryStatus.APPROVED,
                    ReviewPrizeDrawEntry.entry_month == month,
                )
            )
        ).all()
    )
    if not approved:
        return None, "No approved entries for this month"

    winner_entry = random.choice(approved)
    now = datetime.utcnow()
    winner = ReviewPrizeDrawWinner(
        month=month,
        entry_id=winner_entry.id,
        picked_at=now,
        picked_by_id=user.id,
    )
    session.add(winner)
    session.flush()

    order = session.get(Order, winner_entry.order_id)
    customer = session.get(Customer, winner_entry.customer_id)
    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_WINNER.value,
            title="Review Prize Draw Winner",
            description=(
                f"{customer.name if customer else 'Customer'} won the {month} review prize draw "
                f"for order {order.order_number}"
            ),
            order=order,
            metadata={"month": month, "entry_id": winner_entry.id},
            created_by_id=user.id,
        )
    return winner, None


def reset_winner_for_month(
    month: str,
    user: User,
    session: Session,
) -> Tuple[bool, Optional[str]]:
    """Clear the picked winner for a month so the draw can be run again."""
    winner = get_winner_for_month(session, month)
    if not winner:
        return False, "No winner picked for this month"

    entry = session.get(ReviewPrizeDrawEntry, winner.entry_id)
    order = session.get(Order, entry.order_id) if entry else None
    customer = session.get(Customer, entry.customer_id) if entry else None
    previous_entry_id = winner.entry_id
    session.delete(winner)

    if order:
        record_order_audit_event(
            session,
            event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_WINNER_RESET.value,
            title="Review Prize Draw Reset",
            description=(
                f"{month} review prize draw reset"
                f"{f' (previous winner: {customer.name})' if customer else ''}"
            ),
            order=order,
            metadata={"month": month, "previous_entry_id": previous_entry_id},
            created_by_id=user.id,
        )
    return True, None


def build_prize_draw_congratulations_context(
    settings: Optional[CompanySettings],
    order: Order,
    customer: Customer,
    month: str,
) -> dict:
    company_ctx = {"company_name": "", "trading_name": ""}
    if settings:
        company_ctx = {
            "company_name": settings.company_name or "",
            "trading_name": settings.trading_name or "",
        }
    prize_title = "Monthly prize draw"
    if settings and settings.review_prize_draw_title:
        prize_title = settings.review_prize_draw_title
    return {
        "order": {"order_number": order.order_number or ""},
        "company": company_ctx,
        "prize_draw": {
            "month": month,
            "title": prize_title,
            "celebration_banner_url": build_prize_draw_celebration_banner_url(settings),
        },
    }


def _normalize_congratulations_channel(channel: Optional[str]) -> Optional[str]:
    if not channel:
        return None
    normalized = channel.strip().lower()
    if normalized == "sms":
        return CustomerOutreachChannel.SMS.value
    if normalized == "email":
        return CustomerOutreachChannel.EMAIL.value
    return None


def _generate_thread_id(message_id: Optional[str]) -> str:
    if message_id:
        return message_id.split("@")[0]
    return str(uuid.uuid4())


def send_congratulations_to_winner(
    month: str,
    user: User,
    session: Session,
    *,
    channel: str,
    force: bool = False,
) -> Tuple[Optional[ReviewPrizeDrawWinner], Optional[str]]:
    """Send congratulations SMS or email to the monthly prize draw winner."""
    winner = get_winner_for_month(session, month)
    if not winner:
        return None, "No winner picked for this month"
    if winner.congratulations_sent_at and not force:
        return None, "Congratulations already sent to this winner"

    settings = _get_company_settings(session)
    if not settings:
        return None, "Company settings not found"

    resolved_channel = _normalize_congratulations_channel(channel)
    if not resolved_channel:
        return None, "channel must be 'email' or 'sms'"

    entry = session.get(ReviewPrizeDrawEntry, winner.entry_id)
    if not entry:
        return None, "Winner entry not found"
    order = session.get(Order, entry.order_id)
    if not order:
        return None, "Winner order not found"
    customer = session.get(Customer, entry.customer_id)
    if not customer:
        return None, "Winner customer not found"

    template_ctx = build_prize_draw_congratulations_context(settings, order, customer, month)
    now = datetime.utcnow()
    quote = session.exec(select(Quote).where(Quote.id == order.quote_id)).first()
    lead_id = quote.lead_id if quote else None

    if resolved_channel == CustomerOutreachChannel.SMS.value:
        template_id = settings.review_prize_draw_congratulations_sms_template_id
        if not template_id:
            return None, "Prize draw congratulations SMS template is not configured"
        template = session.get(SmsTemplate, template_id)
        if not template:
            return None, "SMS template not found"
        to_phone = (customer.phone or "").strip()
        if not to_phone and lead_id:
            to_phone = resolve_sms_to_phone(session, customer, lead_id=lead_id) or ""
        if not to_phone:
            return None, "No phone number for customer"

        body = render_sms_template(
            template,
            customer,
            user=user,
            company_settings=settings,
            extra_context=template_ctx,
        )
        success, sid, error = send_sms(to_phone, body)
        if not success:
            if is_unsubscribed_recipient_error(error):
                customer.automated_reminder_outreach_opt_out = True
                session.add(customer)
            return None, error or "Failed to send SMS"

        from_phone = (os.getenv("TWILIO_PHONE_NUMBER") or "").strip()
        session.add(
            SmsMessage(
                customer_id=customer.id,
                lead_id=lead_id,
                direction=SmsDirection.SENT,
                from_phone=from_phone,
                to_phone=normalize_phone(to_phone),
                body=body,
                twilio_sid=sid,
                sent_at=now,
                created_by_id=user.id,
            )
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.SMS_SENT,
                notes=(
                    f"Prize draw congratulations for {month} sent by SMS to {to_phone} "
                    f"(order {order.order_number})\n{body}"
                ),
                created_by_id=user.id,
            )
        )
    else:
        template_id = settings.review_prize_draw_congratulations_email_template_id
        if not template_id:
            return None, "Prize draw congratulations email template is not configured"
        template = session.get(EmailTemplate, template_id)
        if not template:
            return None, "Email template not found"
        to_email = (customer.email or "").strip()
        if not to_email:
            return None, "No email address for customer"
        if customer.wrong_email_address:
            return None, "Marked as wrong email address"
        if not is_email_configured(user.id):
            return None, "Email not configured for outreach actor"

        subject, body_html = render_email_template(template, customer, custom_variables=template_ctx)
        body_text = _html_to_plain(body_html)
        success, message_id, error, sent_html, sent_text = send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            user_id=user.id,
            customer_number=customer.customer_number,
        )
        if not success:
            return None, error or "Failed to send email"

        final_html = sent_html or body_html
        final_text = sent_text if sent_text is not None else body_text
        thread_id = _generate_thread_id(message_id)
        session.add(
            Email(
                customer_id=customer.id,
                lead_id=lead_id,
                direction=EmailDirection.SENT,
                from_email=user.email or "",
                to_email=to_email,
                subject=subject,
                body_html=final_html,
                body_text=final_text,
                message_id=message_id,
                thread_id=thread_id,
                sent_at=now,
                created_by_id=user.id,
            )
        )
        session.add(
            Activity(
                customer_id=customer.id,
                activity_type=ActivityType.EMAIL_SENT,
                notes=build_activity_email_notes(
                    f"Prize draw congratulations for {month} sent to {to_email} "
                    f"(order {order.order_number})",
                    subject,
                    final_text,
                    final_html,
                ),
                created_by_id=user.id,
            )
        )

    winner.congratulations_sent_at = now
    winner.congratulations_channel = resolved_channel
    winner.congratulations_sent_by_id = user.id
    session.add(winner)

    record_order_audit_event(
        session,
        event_type=CustomerHistoryEventType.REVIEW_PRIZE_DRAW_CONGRATULATIONS_SENT.value,
        title="Prize Draw Congratulations Sent",
        description=(
            f"Congratulations sent to {customer.name} for winning the {month} "
            f"review prize draw (order {order.order_number})"
        ),
        order=order,
        metadata={"month": month, "channel": resolved_channel},
        created_by_id=user.id,
    )
    return winner, None


def build_prize_draw_entry_response(
    entry: Optional[ReviewPrizeDrawEntry],
) -> Optional[dict]:
    if not entry:
        return None
    return {
        "id": entry.id,
        "status": entry.status.value if entry.status else None,
        "prize_draw_url": build_prize_draw_url(entry.access_token),
        "platforms_claimed": entry.platforms_claimed or [],
        "submitted_at": entry.submitted_at,
        "entry_month": entry.entry_month,
        "rejection_note": entry.rejection_note,
    }
